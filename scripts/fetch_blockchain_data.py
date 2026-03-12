"""
Fetch blockchain transaction data from various blockchain APIs.
Supports BTC (via Blockchain.com), ETH and USDT-ERC20 (via Etherscan).
"""

import os
import requests
import time
import threading
from datetime import datetime
from typing import Optional


class BlockchainAPIError(Exception):
    """Custom exception for blockchain API errors"""
    pass


# Cache block number -> timestamp to avoid repeated eth_getBlockByNumber calls
# (many transactions often share the same block)
_block_cache: dict = {}
_block_cache_lock = threading.Lock()

# Rate limiter for Etherscan free tier: max 4 req/s (limit is 5, we keep margin)
_etherscan_lock = threading.Lock()
_etherscan_last_call: float = 0.0
_ETHERSCAN_MIN_INTERVAL = 0.25  # seconds between calls = 4 req/s


def _etherscan_get(url: str, params: dict, timeout: int = 10) -> requests.Response:
    """Make a rate-limited GET request to Etherscan (safe for free tier)."""
    global _etherscan_last_call
    with _etherscan_lock:
        now = time.monotonic()
        wait = _ETHERSCAN_MIN_INTERVAL - (now - _etherscan_last_call)
        if wait > 0:
            time.sleep(wait)
        _etherscan_last_call = time.monotonic()
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response


def identify_blockchain(tx_hash: str) -> str:
    """
    Identify the blockchain type based on transaction hash format.

    Args:
        tx_hash: Transaction hash string

    Returns:
        Blockchain type: 'BTC', 'ETH', or 'USDT-ERC20'
    """
    tx_hash = tx_hash.strip()

    # Ethereum and USDT-ERC20 hashes start with 0x and are 66 characters
    if tx_hash.startswith('0x') and len(tx_hash) == 66:
        return 'ETH'  # Will check if it's USDT later

    # Bitcoin hashes are 64 characters (hex)
    if len(tx_hash) == 64 and all(c in '0123456789abcdefABCDEF' for c in tx_hash):
        return 'BTC'

    raise BlockchainAPIError(f"Unable to identify blockchain type for hash: {tx_hash}")


def get_btc_transaction(tx_hash: str) -> dict:
    """
    Fetch Bitcoin transaction details from Blockchain.com API.

    Args:
        tx_hash: Bitcoin transaction hash

    Returns:
        Dictionary containing transaction details
    """
    url = f"https://blockchain.info/rawtx/{tx_hash}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Extract transaction details
        timestamp = data.get('time', 0)
        date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

        # Calculate fee (in satoshis, convert to BTC)
        fee_satoshi = sum(inp.get('prev_out', {}).get('value', 0) for inp in data.get('inputs', [])) - \
                      sum(out.get('value', 0) for out in data.get('out', []))
        fee_btc = fee_satoshi / 100000000  # Convert satoshi to BTC

        # Get first output address as destination
        outputs = data.get('out', [])
        to_address = outputs[0].get('addr', 'N/A') if outputs else 'N/A'

        # Calculate total amount sent (sum of outputs)
        amount_sent = sum(out.get('value', 0) for out in outputs) / 100000000

        return {
            'hash': tx_hash,
            'blockchain': 'BTC',
            'transaction_type': 'send',
            'amount': amount_sent,
            'wallet_address': to_address,
            'date': date,
            'timestamp': timestamp,
            'fee_crypto': fee_btc,
            'fee_crypto_symbol': 'BTC',
            'error': None
        }

    except requests.exceptions.RequestException as e:
        raise BlockchainAPIError(f"Error fetching BTC transaction: {str(e)}")


def get_eth_transaction(tx_hash: str, api_key: str) -> dict:
    """
    Fetch Ethereum transaction details from Etherscan API V2.

    Args:
        tx_hash: Ethereum transaction hash
        api_key: Etherscan API key

    Returns:
        Dictionary containing transaction details
    """
    base_url = "https://api.etherscan.io/v2/api"

    params = {
        'module': 'proxy',
        'action': 'eth_getTransactionByHash',
        'txhash': tx_hash,
        'apikey': api_key,
        'chainid': '1'  # Ethereum Mainnet
    }

    try:
        data = _etherscan_get(base_url, params).json()

        if data.get('result') is None:
            raise BlockchainAPIError(f"Transaction not found: {tx_hash}")

        tx_data = data['result']

        # Get transaction receipt for gas used
        receipt_params = {
            'module': 'proxy',
            'action': 'eth_getTransactionReceipt',
            'txhash': tx_hash,
            'apikey': api_key,
            'chainid': '1'
        }

        receipt_data = _etherscan_get(base_url, receipt_params).json()

        if receipt_data.get('result') is None:
            raise BlockchainAPIError(f"Transaction receipt not found: {tx_hash}")

        receipt = receipt_data['result']

        # Calculate fee
        gas_used = int(receipt.get('gasUsed', '0x0'), 16)
        gas_price = int(tx_data.get('gasPrice', '0x0'), 16)
        fee_wei = gas_used * gas_price
        fee_eth = fee_wei / 1e18  # Convert wei to ETH

        # Get block timestamp (cached to avoid repeated calls for transactions in the same block)
        block_number = tx_data.get('blockNumber', '0x0')
        with _block_cache_lock:
            cached_ts = _block_cache.get(block_number)

        if cached_ts is not None:
            timestamp = cached_ts
        else:
            block_params = {
                'module': 'proxy',
                'action': 'eth_getBlockByNumber',
                'tag': block_number,
                'boolean': 'false',
                'apikey': api_key,
                'chainid': '1'
            }
            block_data = _etherscan_get(base_url, block_params).json()
            timestamp = int(block_data.get('result', {}).get('timestamp', '0x0'), 16)
            with _block_cache_lock:
                _block_cache[block_number] = timestamp
        date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

        # Get amount sent (convert from wei to ETH)
        amount_wei = int(tx_data.get('value', '0x0'), 16)
        amount_eth = amount_wei / 1e18

        # Check if this is a USDT transaction
        to_address = tx_data.get('to', '').lower()
        usdt_contract = '0xdac17f958d2ee523a2206206994597c13d831ec7'  # USDT ERC20 contract

        is_usdt = to_address == usdt_contract

        if is_usdt:
            # For USDT, decode the input data to get actual amount
            input_data = tx_data.get('input', '0x')
            if len(input_data) >= 74:
                # Extract recipient and amount from input data
                # Method ID: 0xa9059cbb (transfer)
                recipient = '0x' + input_data[34:74]
                amount_hex = input_data[74:138] if len(input_data) >= 138 else '0'
                usdt_amount = int(amount_hex, 16) / 1e6  # USDT has 6 decimals

                return {
                    'hash': tx_hash,
                    'blockchain': 'USDT-ERC20',
                    'transaction_type': 'send',
                    'amount': usdt_amount,
                    'wallet_address': recipient,
                    'date': date,
                    'timestamp': timestamp,
                    'fee_crypto': fee_eth,
                    'fee_crypto_symbol': 'ETH',
                    'error': None
                }

        return {
            'hash': tx_hash,
            'blockchain': 'ETH',
            'transaction_type': 'send',
            'amount': amount_eth,
            'wallet_address': tx_data.get('to', 'N/A'),
            'date': date,
            'timestamp': timestamp,
            'fee_crypto': fee_eth,
            'fee_crypto_symbol': 'ETH',
            'error': None
        }

    except requests.exceptions.RequestException as e:
        raise BlockchainAPIError(f"Error fetching ETH transaction: {str(e)}")


def get_transaction_details(tx_hash: str, etherscan_api_key: Optional[str] = None) -> dict:
    """
    Fetch transaction details for any supported blockchain.

    Args:
        tx_hash: Transaction hash
        etherscan_api_key: Etherscan API key (required for ETH/USDT)

    Returns:
        Dictionary containing transaction details
    """
    try:
        blockchain = identify_blockchain(tx_hash)

        if blockchain == 'BTC':
            return get_btc_transaction(tx_hash)
        elif blockchain == 'ETH':
            if not etherscan_api_key:
                raise BlockchainAPIError("Etherscan API key is required for ETH/USDT transactions")
            return get_eth_transaction(tx_hash, etherscan_api_key)
        else:
            raise BlockchainAPIError(f"Unsupported blockchain type: {blockchain}")

    except BlockchainAPIError as e:
        return {
            'hash': tx_hash,
            'blockchain': 'Unknown',
            'transaction_type': None,
            'amount': None,
            'wallet_address': None,
            'date': None,
            'timestamp': None,
            'fee_crypto': None,
            'fee_crypto_symbol': None,
            'error': str(e)
        }
    except Exception as e:
        return {
            'hash': tx_hash,
            'blockchain': 'Unknown',
            'transaction_type': None,
            'amount': None,
            'wallet_address': None,
            'date': None,
            'timestamp': None,
            'fee_crypto': None,
            'fee_crypto_symbol': None,
            'error': f"Unexpected error: {str(e)}"
        }


if __name__ == "__main__":
    # Test the functions
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fetch_blockchain_data.py <transaction_hash>")
        sys.exit(1)

    tx_hash = sys.argv[1]
    api_key = os.getenv('ETHERSCAN_API_KEY')

    print(f"Fetching transaction details for: {tx_hash}")
    result = get_transaction_details(tx_hash, api_key)

    print("\nTransaction Details:")
    for key, value in result.items():
        print(f"  {key}: {value}")
