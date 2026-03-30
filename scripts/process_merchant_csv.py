"""
Orchestrator: reads a merchant (ATM) CSV export, filters valid cashin/cashout
transactions, calculates blockchain fees for each, and writes a unified output CSV.

Cashin:  txHash column (BC) → transaction hash → fees via process_transactions logic
Cashout: toAddress column (D) → ETH wallet address → fees via eth_chash_out_exchange logic

Usage:
    python scripts/process_merchant_csv.py <merchant_csv> <output_csv> [workers]

Example:
    python scripts/process_merchant_csv.py 2026-03-01_transactions.csv output_march.csv
"""

import os
import sys
import csv
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Tuple
from dotenv import load_dotenv

# Ensure the scripts/ directory is on the path for sibling imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

load_dotenv()

from fetch_exchange_rates import preload_all_rates, get_historical_rate, ExchangeRateAPIError
from fetch_blockchain_data import get_btc_transactions_by_address, BlockchainAPIError
from process_transactions import (
    process_transaction,
    write_transaction_to_csv,
    load_processed_transactions,
    get_crypto_usd_price,
)
from eth_chash_out_exchange import (
    get_transactions_from_address,
    process_transaction_data,
    TransactionValidationError,
)

# ---------------------------------------------------------------------------
# Unified output columns (superset of both cashin and cashout scripts)
# ---------------------------------------------------------------------------
OUTPUT_COLUMNS = [
    'source',            # 'cashin' | 'cashout'
    'hash',
    'blockchain',
    'transaction_type',
    'amount',
    'wallet_address',    # normalized (cashout used 'wallet_addr')
    'date',
    'fee_crypto',
    'fee_crypto_symbol', # normalized (cashout used 'fee_crypto_ticker')
    'fee_usd',
    'usd_ils_rate',
    'fee_ils_standard',
    'fee_ils_markup_6pct',
    'crypto_amount_sent',
    'error',
]

# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def read_and_filter_merchant_csv(file_path: str) -> Tuple[List[str], List[str]]:
    """
    Read the merchant ATM CSV and extract:
    - cashin_hashes: txHash values where txClass='cashIn', status='Sent', txHash not empty
    - cashout_addresses: toAddress values where txClass='cashOut', status='Success',
                         cryptoCode='ETH', toAddress not empty

    Deduplicates both lists while preserving order.
    Returns (cashin_hashes, cashout_addresses).
    """
    cashin_hashes: List[str] = []
    cashout_addresses: List[str] = []
    seen_hashes: set = set()
    seen_addresses: set = set()

    skipped_rows = 0

    try:
        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)

            if not reader.fieldnames:
                print("Error: Merchant CSV is empty or has no headers.")
                sys.exit(1)

            # Validate required columns exist
            required = {'txClass', 'status', 'txHash', 'toAddress', 'cryptoCode'}
            missing = required - set(reader.fieldnames)
            if missing:
                print(f"Error: Missing required columns in merchant CSV: {missing}")
                sys.exit(1)

            for row_num, row in enumerate(reader, start=2):
                tx_class = row.get('txClass', '').strip()
                status = row.get('status', '').strip()
                tx_hash = row.get('txHash', '').strip()
                to_address = row.get('toAddress', '').strip()
                crypto_code = row.get('cryptoCode', '').strip()

                if tx_class == 'cashIn':
                    if status == 'Sent' and tx_hash:
                        key = tx_hash.lower()
                        if key not in seen_hashes:
                            seen_hashes.add(key)
                            cashin_hashes.append(tx_hash)
                    else:
                        skipped_rows += 1

                elif tx_class == 'cashOut':
                    if status == 'Success' and crypto_code == 'ETH' and to_address:
                        key = to_address.lower()
                        if key not in seen_addresses:
                            seen_addresses.add(key)
                            cashout_addresses.append(to_address)
                    else:
                        skipped_rows += 1

    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading merchant CSV: {e}")
        sys.exit(1)

    print(f"Merchant CSV parsed:")
    print(f"  Cashin hashes (unique, status=Sent):         {len(cashin_hashes)}")
    print(f"  Cashout addresses (unique, ETH, status=Success): {len(cashout_addresses)}")
    print(f"  Skipped rows (wrong status/type/empty):       {skipped_rows}")

    return cashin_hashes, cashout_addresses


# ---------------------------------------------------------------------------
# Row normalization
# ---------------------------------------------------------------------------

def normalize_cashin_row(result: Dict) -> Dict:
    """Add source='cashin' to a result dict from process_transaction()."""
    result['source'] = 'cashin'
    return result


def normalize_cashout_row(result: Dict) -> Dict:
    """
    Normalize a result dict from process_transaction_data() (eth_chash_out_exchange)
    to match OUTPUT_COLUMNS:
      - wallet_addr  → wallet_address
      - fee_crypto_ticker → fee_crypto_symbol
      - add source, crypto_amount_sent, error
    """
    normalized = {
        'source': 'cashout',
        'hash': result.get('hash'),
        'blockchain': result.get('blockchain'),
        'transaction_type': result.get('transaction_type'),
        'amount': result.get('amount'),
        'wallet_address': result.get('wallet_addr'),          
        'date': result.get('date'),
        'fee_crypto': result.get('fee_crypto'),
        'fee_crypto_symbol': result.get('fee_crypto_ticker'), 
        'fee_usd': result.get('fee_usd'),
        'usd_ils_rate': result.get('usd_ils_rate'),
        'fee_ils_standard': result.get('fee_ils_standard'),
        'fee_ils_markup_6pct': result.get('fee_ils_markup_6pct'),
        'crypto_amount_sent': result.get('amount'),           # ETH sent = amount
        'error': None,
    }
    return normalized


# ---------------------------------------------------------------------------
# BTC cashout processing (mirrors process_transaction_data for ETH)
# ---------------------------------------------------------------------------

def process_btc_cashout_tx(raw_tx: dict, price_cache: dict, rate_cache: dict) -> Dict | None:
    """
    Convert a raw BTC address transaction (from get_btc_transactions_by_address)
    into the unified output row format.
    """
    try:
        tx_hash = raw_tx['hash']
        fee_btc = raw_tx['fee_satoshi'] / 1e8
        amount_btc = raw_tx['out_total_satoshi'] / 1e8
        date_str = datetime.fromtimestamp(raw_tx['time']).strftime('%Y-%m-%d')

        btc_price_usd = get_crypto_usd_price('BTC', date_str, price_cache)
        if btc_price_usd is None:
            print(f"  Error: Could not fetch BTC price for {date_str}")
            return None

        fee_usd = fee_btc * btc_price_usd

        try:
            usd_ils_rate = get_historical_rate(date_str, rate_cache)
        except ExchangeRateAPIError as e:
            print(f"  Warning: Exchange rate error for {date_str}: {e}")
            return None

        fee_ils_standard = fee_usd * usd_ils_rate
        fee_ils_markup = fee_ils_standard * 1.06

        return {
            'source': 'cashout',
            'hash': tx_hash,
            'blockchain': 'BTC',
            'transaction_type': 'Cash Out',
            'amount': amount_btc,
            'wallet_address': raw_tx['from_address'],
            'date': date_str,
            'fee_crypto': fee_btc,
            'fee_crypto_symbol': 'BTC',
            'fee_usd': fee_usd,
            'usd_ils_rate': usd_ils_rate,
            'fee_ils_standard': fee_ils_standard,
            'fee_ils_markup_6pct': fee_ils_markup,
            'error': None,
        }
    except Exception as e:
        print(f"  Unexpected error processing BTC cashout tx {raw_tx.get('hash')}: {e}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/process_merchant_csv.py <merchant_csv> <output_csv> [workers]")
        print()
        print("Example:")
        print("  python scripts/process_merchant_csv.py 2026-03-01_transactions.csv output_march.csv")
        sys.exit(1)

    merchant_csv = sys.argv[1]
    output_csv = sys.argv[2]
    max_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
    if not etherscan_api_key:
        print("Warning: ETHERSCAN_API_KEY not set. ETH/USDT cashin and ETH cashout will fail.")

    # --- Parse and filter merchant CSV ---
    cashin_hashes, cashout_addresses = read_and_filter_merchant_csv(merchant_csv)

    if not cashin_hashes and not cashout_addresses:
        print("No transactions to process after filtering.")
        sys.exit(0)

    # --- Pre-load exchange rates ---
    print("\nPre-loading exchange rates...")
    rate_cache: Dict = preload_all_rates()

    # --- Resume: skip already-processed hashes ---
    processed_hashes = load_processed_transactions(output_csv)
    file_exists = os.path.exists(output_csv)

    # --- Shared state ---
    price_cache: Dict = {}
    cache_lock = threading.Lock()
    csv_lock = threading.Lock()
    counters = {'new': 0, 'skipped': 0, 'failed': 0}
    counters_lock = threading.Lock()

    # Filter pending cashin
    pending_cashin = [(i, h) for i, h in enumerate(cashin_hashes, 1)
                      if h.lower() not in processed_hashes]
    skipped_cashin = len(cashin_hashes) - len(pending_cashin)

    print(f"\nOutput file:  {output_csv}")
    print(f"Mode:         {'RESUME (append)' if file_exists else 'NEW FILE'}")
    print(f"Workers:      {max_workers}")
    print(f"Cashin:       {len(pending_cashin)} to process, {skipped_cashin} already done")
    print(f"Cashout:      {len(cashout_addresses)} addresses to scan")
    print("-" * 60)

    total_cashin = len(cashin_hashes)

    # -----------------------------------------------------------------------
    # Process cashin (threaded)
    # -----------------------------------------------------------------------
    def process_cashin_one(item: tuple) -> None:
        i, tx_hash = item
        print(f"[cashin {i}/{total_cashin}] {tx_hash[:20]}...")

        with cache_lock:
            local_price_cache = dict(price_cache)

        result = process_transaction(tx_hash, etherscan_api_key, rate_cache, local_price_cache)

        with cache_lock:
            price_cache.update(local_price_cache)

        result = normalize_cashin_row(result)

        with counters_lock:
            is_first_new = (counters['new'] == 0 and not file_exists)

        if result.get('error'):
            with counters_lock:
                counters['failed'] += 1
            print(f"  Failed: {result['error']}")
        else:
            print(f"  OK")

        if write_transaction_to_csv(result, output_csv, OUTPUT_COLUMNS, is_first_new, csv_lock):
            with counters_lock:
                counters['new'] += 1
            with cache_lock:
                processed_hashes.add(tx_hash.lower())

    if pending_cashin:
        print(f"\n--- Processing {len(pending_cashin)} cashin transactions ---")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_cashin_one, item) for item in pending_cashin]
            for future in as_completed(futures):
                future.result()

    # -----------------------------------------------------------------------
    # Process cashout ETH addresses (threaded - rate limiting via _etherscan_get)
    # -----------------------------------------------------------------------
    total_cashout = len(cashout_addresses)

    def process_cashout_one(item: tuple) -> None:
        idx, address = item
        print(f"[cashout {idx}/{total_cashout}] Scanning: {address}")

        if not etherscan_api_key:
            print(f"  [{address[:12]}] Skipped: ETHERSCAN_API_KEY not set")
            return

        try:
            matching_txs = get_transactions_from_address(address, etherscan_api_key)

            if not matching_txs:
                print(f"  [{address[:12]}] No matching transactions found.")
                return

            print(f"  [{address[:12]}] Found {len(matching_txs)} transaction(s).")

            for tx_data in matching_txs:
                tx_hash = tx_data['hash']

                with cache_lock:
                    if tx_hash.lower() in processed_hashes:
                        with counters_lock:
                            counters['skipped'] += 1
                        print(f"  Skipping {tx_hash[:12]}... (already processed)")
                        continue
                    local_price_cache = dict(price_cache)

                result = process_transaction_data(tx_data, local_price_cache, rate_cache)

                with cache_lock:
                    price_cache.update(local_price_cache)

                if result:
                    result = normalize_cashout_row(result)

                    with counters_lock:
                        is_first_new = (counters['new'] == 0 and not file_exists)

                    if write_transaction_to_csv(
                        result, output_csv, OUTPUT_COLUMNS, is_first_new, csv_lock
                    ):
                        with cache_lock:
                            processed_hashes.add(tx_hash.lower())
                        with counters_lock:
                            counters['new'] += 1
                        print(f"  [{tx_hash[:12]}] OK")
                    else:
                        print(f"  [{tx_hash[:12]}] Processed but failed to write")
                else:
                    with counters_lock:
                        counters['failed'] += 1
                    print(f"  [{tx_hash[:12]}] Failed to process")

        except TransactionValidationError as e:
            print(f"  Error scanning {address}: {e}")
        except Exception as e:
            print(f"  Unexpected error scanning {address}: {e}")

    if cashout_addresses:
        print(f"\n--- Processing {total_cashout} cashout ETH addresses ---")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_cashout_one, item)
                       for item in enumerate(cashout_addresses, 1)]
            for future in as_completed(futures):
                future.result()

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"Processing complete!")
    print(f"{'='*60}")
    print(f"  New transactions written:   {counters['new']}")
    print(f"  Skipped (already done):     {counters['skipped'] + skipped_cashin}")
    print(f"  Failed:                     {counters['failed']}")
    print(f"  Total in output file:       {len(processed_hashes)}")
    print(f"  Output: {output_csv}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
