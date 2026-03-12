"""
hendels cash out transactions brings fees that are related to accoubt 0x0Ab3FbC9025EcE0EA4e0f9D29fbAa94B70923e37 spesific transactions
"""


import os
import sys
import csv
import time
import requests
from datetime import datetime
from dotenv import load_dotenv


current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from fetch_exchange_rates import get_historical_rate, ExchangeRateAPIError
    from process_transactions import get_crypto_usd_price
except ImportError:
    print("Error: Could not import helper modules. Make sure you are in the correct directory.")
    sys.exit(1)


# Load environment variables
load_dotenv()

TARGET_ADDRESS = "0x0Ab3FbC9025EcE0EA4e0f9D29fbAa94B70923e37"
ETHERSCAN_API_URL = "https://api.etherscan.io/v2/api"

class TransactionValidationError(Exception):
    """Custom exception for transaction validation errors"""
    def __init__(self, message, error_code= None, api_message= None):
        super().__init__(message)
        self.error_code = error_code
        self.api_message = api_message

def get_transactions_from_address(address: str, api_key: str, max_retries: int = 3):
    """
    Fetch normal transactions for an address and filter for those sent to TARGET_ADDRESS.
    Implements retry logic with exponential backoff for network errors.

    Args:
        address: Ethereum address to query
        api_key: Etherscan API key
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        List of matching transactions
    """
    params = {
        'module': 'account',
        'action': 'txlist',
        'address': address,
        'startblock': 0,
        'endblock': 99999999,
        'sort': 'desc', # Get most recent first
        'apikey': api_key,
        'chainid': '1'
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(ETHERSCAN_API_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            # Etherscan returns "0" for status 0 (error) and "1" for status 1 (ok)
            # But for 'No transactions found', it might return status 0 with message 'No transactions found'
            if data['status'] == '0' and data['message'] != 'No transactions found':
                 raise TransactionValidationError(f"Etherscan API error: {data['message']}")

            transactions = data.get('result', [])
            if not isinstance(transactions, list):
                return []

            matching_txs = []
            for tx in transactions:
                # Check if sent to TARGET_ADDRESS
                # 'to' can be None for contract creation
                if tx.get('to') and tx['to'].lower() == TARGET_ADDRESS.lower():
                    matching_txs.append(tx)

            return matching_txs

        except requests.Timeout as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"  ⏱️  Timeout on attempt {attempt + 1}/{max_retries}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise TransactionValidationError(f"Network timeout after {max_retries} attempts: {e}")

        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"  🔄 Network error on attempt {attempt + 1}/{max_retries}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise TransactionValidationError(f"Network error after {max_retries} attempts: {e}")

def process_transaction_data(tx_data: dict, price_cache: dict, rate_cache: dict):
    """
    Process a single transaction dictionary returned from txlist.
    """
    try:
        tx_hash = tx_data['hash']
        
        # Data Extraction from txlist object
        # txlist provides gasUsed, gasPrice, timeStamp, value directly
        gas_used = int(tx_data['gasUsed'])
        gas_price = int(tx_data['gasPrice'])
        value_wei = int(tx_data['value'])
        timestamp = int(tx_data['timeStamp'])
        from_address = tx_data['from']
        
        fee_wei = gas_used * gas_price
        fee_eth = fee_wei / 1e18
        amount_eth = value_wei / 1e18
        
        date_obj = datetime.fromtimestamp(timestamp)
        date_str = date_obj.strftime('%Y-%m-%d')
        
        # 1. Get ETH Price in USD
        eth_price_usd = get_crypto_usd_price('ETH', date_str, price_cache)
        
        if eth_price_usd is None:
             print(f"Error: Could not fetch ETH price for {date_str}")
             return None

        fee_usd = fee_eth * eth_price_usd
        
        # 2. Get ILS Exchange Rate
        try:
            usd_ils_rate = get_historical_rate(date_str, rate_cache)
        except ExchangeRateAPIError as e:
             print(f"Warning: Exchange rate error for {date_str}: {e}")
             print("Could not retrieve exchange rate.")
             return None
        
        # 3. Calculate Final Fees
        fee_ils_standard = fee_usd * usd_ils_rate
        fee_ils_markup = fee_ils_standard * 1.06 # 6% markup
        
        return {
            'hash': tx_hash,
            'blockchain': 'ETH',
            'transaction_type': 'Cash Out',
            'amount': amount_eth,
            'wallet_addr': from_address,
            'date': date_str,
            'fee_crypto': fee_eth,
            'fee_crypto_ticker': 'ETH',
            'fee_usd': fee_usd,
            'usd_ils_rate': usd_ils_rate,
            'fee_ils_standard': fee_ils_standard,
            'fee_ils_markup_6pct': fee_ils_markup
        }

    except Exception as e:
        print(f"Unexpected error processing tx {tx_data.get('hash')}: {e}")
        return None

def load_processed_transactions(output_file: str):
    """
    Load already processed transaction hashes from existing output file.
    Returns a set of transaction hashes that have already been processed.
    """
    processed_hashes = set()

    if not os.path.exists(output_file):
        return processed_hashes

    try:
        with open(output_file, mode='r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if 'hash' in row and row['hash']:
                    processed_hashes.add(row['hash'].lower())

        if processed_hashes:
            print(f"📊 Resume mode: Found {len(processed_hashes)} already processed transactions")
    except Exception as e:
        print(f"Warning: Could not read existing output file: {e}")

    return processed_hashes

def write_transaction_to_csv(result: dict, output_file: str, fieldnames: list, write_header: bool = False):
    """
    Write a single transaction result to CSV file immediately (incremental write).

    Args:
        result: Transaction data dictionary
        output_file: Path to output CSV file
        fieldnames: List of CSV column names
        write_header: Whether to write the CSV header (for new files)
    """
    try:
        mode = 'w' if write_header else 'a'
        with open(output_file, mode=mode, newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if write_header:
                writer.writeheader()

            # Format the row
            formatted_row = result.copy()
            formatted_row['amount'] = f"{result['amount']:.8f}"
            formatted_row['fee_crypto'] = f"{result['fee_crypto']:.8f}"
            formatted_row['fee_usd'] = f"{result['fee_usd']:.2f}"
            formatted_row['usd_ils_rate'] = f"{result['usd_ils_rate']:.4f}"
            formatted_row['fee_ils_standard'] = f"{result['fee_ils_standard']:.2f}"
            formatted_row['fee_ils_markup_6pct'] = f"{result['fee_ils_markup_6pct']:.2f}"

            writer.writerow(formatted_row)
            csvfile.flush()  # Force write to disk immediately
            os.fsync(csvfile.fileno())  # Ensure OS writes to disk

        return True
    except PermissionError:
        print(f"  ❌ Error: Permission denied writing to {output_file}. Please close the file if it is open.")
        return False
    except Exception as e:
        print(f"  ❌ Error writing to CSV: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python eth_chash_out_exchange.py <address_or_csv_file>")
        sys.exit(1)

    arg = sys.argv[1]
    input_addresses = []

    # Determine input source
    if arg.endswith('.csv'):
        if not os.path.exists(arg):
            print(f"Error: File {arg} not found.")
            sys.exit(1)

        print(f"Reading addresses from {arg}...")
        try:
            with open(arg, mode='r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                if not reader.fieldnames:
                     print("Error: CSV file is empty or missing headers.")
                     sys.exit(1)

                # Find column for address or hash (relaxed matching)
                target_col = None
                for col in reader.fieldnames:
                    if col.lower() in ['hash', 'address', 'wallet', 'from']:
                        target_col = col
                        break

                if not target_col:
                     print("Error: Input CSV must have a column named 'hash', 'address', 'wallet', or 'from'.")
                     sys.exit(1)

                for row in reader:
                    val = row[target_col].strip()
                    if val:
                        input_addresses.append(val)

        except Exception as e:
            print(f"Error reading CSV: {e}")
            sys.exit(1)
    else:
        # Single address
        input_addresses.append(arg)

    api_key = os.getenv('ETHERSCAN_API_KEY')
    if not api_key:
        print("Error: ETHERSCAN_API_KEY not found in environment variables.")
        sys.exit(1)

    # Setup output file
    output_file = 'output_fees.csv'
    fieldnames = [
        'hash', 'blockchain', 'transaction_type', 'amount', 'wallet_addr',
        'date', 'fee_crypto', 'fee_crypto_ticker', 'fee_usd',
        'usd_ils_rate', 'fee_ils_standard', 'fee_ils_markup_6pct'
    ]

    # Load already processed transactions for resume capability
    processed_hashes = load_processed_transactions(output_file)
    file_exists = os.path.exists(output_file)

    # Tracking
    price_cache = {}
    rate_cache = {}
    new_transactions_count = 0
    skipped_count = 0

    print(f"Target Address for Cash Out: {TARGET_ADDRESS}")
    print(f"Output file: {output_file}")
    print(f"Mode: {'RESUME (appending to existing file)' if file_exists else 'NEW FILE'}\n")

    total_addresses = len(input_addresses)
    for idx, addr in enumerate(input_addresses, 1):
        print(f"\n[{idx}/{total_addresses}] Scanning address: {addr}")

        # Skip Bitcoin addresses (bc1... format) - send only non-Bitcoin addresses to Etherscan
        if addr.lower().startswith('bc'):
            print(f"  ⏭️  Skipped: Bitcoin address (bc format)")
            continue

        try:
            # Find matching transactions
            matching_txs = get_transactions_from_address(addr, api_key)
            time.sleep(2) # Rate limiting check - Increased to 2s

            if not matching_txs:
                print("  ℹ️  No matching cash-out transactions found.")
                continue

            print(f"  Found {len(matching_txs)} matching transaction(s).")

            for tx_data in matching_txs:
                tx_hash = tx_data['hash']

                # Check if already processed (resume logic)
                if tx_hash.lower() in processed_hashes:
                    print(f"  ⏭️  Skipping {tx_hash[:10]}... (already processed)")
                    skipped_count += 1
                    continue

                print(f"  🔄 Processing {tx_hash[:10]}...")
                result = process_transaction_data(tx_data, price_cache, rate_cache)

                if result:
                    # Write immediately to CSV (incremental write)
                    write_header = (new_transactions_count == 0 and not file_exists)
                    if write_transaction_to_csv(result, output_file, fieldnames, write_header):
                        processed_hashes.add(tx_hash.lower())
                        new_transactions_count += 1
                        print(f"  ✅ Success (saved to disk)")
                    else:
                        print(f"  ⚠️  Processed but failed to write to disk")
                else:
                    print(f"  ❌ Failed to process")

        except TransactionValidationError as e:
            print(f"❌ Error scanning {addr}: {e}")
        except Exception as e:
            print(f"❌ Unexpected error scanning {addr}: {e}")

        # Additional sleep to be safe between addresses
        time.sleep(1)

    # Final summary
    print(f"\n{'='*60}")
    print(f"✅ Processing complete!")
    print(f"📊 Summary:")
    print(f"   - New transactions processed: {new_transactions_count}")
    print(f"   - Skipped (already processed): {skipped_count}")
    print(f"   - Total in output file: {len(processed_hashes)}")
    print(f"   - Output: {output_file}")
    print(f"{'='*60}")
