"""
Main script to process cryptocurrency transaction hashes and calculate fees.

This script:
1. Reads transaction hashes from input CSV
2. Fetches transaction data from blockchain APIs
3. Retrieves historical exchange rates
4. Calculates fees in USD and ILS (with standard and 6% markup)
5. Generates output CSV with detailed report
"""

import os
import sys
import csv
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import our custom modules
from fetch_blockchain_data import get_transaction_details
from fetch_exchange_rates import get_historical_rate, ExchangeRateAPIError, preload_all_rates


def read_input_csv(file_path: str) -> List[str]:
    """
    Read transaction hashes from input CSV file.

    Args:
        file_path: Path to input CSV file

    Returns:
        List of transaction hashes
    """
    hashes = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            # Check for hash column (accept different naming variations)
            hash_column = None
            if not reader.fieldnames:
                print(f"Error: CSV file is empty or has no header row")
                sys.exit(1)

            for col in reader.fieldnames:
                if col.lower() in ['hash', 'transaction_hash', 'tx_hash', 'txhash']:
                    hash_column = col
                    break

            if not hash_column:
                print(f"Error: CSV file must contain a column named 'hash', 'transaction_hash', or similar")
                sys.exit(1)

            for row in reader:
                tx_hash = row.get(hash_column, '').strip()
                if tx_hash:
                    hashes.append(tx_hash)

        print(f"Loaded {len(hashes)} transaction hashes from {file_path}")
        return hashes

    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        sys.exit(1)


def get_crypto_usd_price(crypto_symbol: str, date: str, cache: Dict) -> float:
    """
    Get historical cryptocurrency price in USD.

    Args:
        crypto_symbol: Cryptocurrency symbol (BTC, ETH, USDT)
        date: Date string in format 'YYYY-MM-DD'
        cache: Cache dictionary to store prices

    Returns:
        Price in USD
    """
    cache_key = f"{crypto_symbol}_{date}"

    if cache_key in cache:
        return cache[cache_key]

    try:
        # Convert date to timestamp
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        timestamp = int(date_obj.timestamp())

        # Use CoinGecko API for historical prices (no API key required)
        # Format date as DD-MM-YYYY for CoinGecko
        date_formatted = date_obj.strftime('%d-%m-%Y')

        coin_ids = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'USDT': 'tether'
        }

        coin_id = coin_ids.get(crypto_symbol)
        if not coin_id:
            raise ValueError(f"Unsupported cryptocurrency: {crypto_symbol}")

        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/history"
        params = {
            'date': date_formatted,
            'localization': 'false'
        }

        import requests
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()

        data = response.json()
        price = data.get('market_data', {}).get('current_price', {}).get('usd')

        if price is None:
            raise ValueError(f"Could not fetch price for {crypto_symbol} on {date}")

        cache[cache_key] = float(price)
        return float(price)

    except Exception as e:
        raise RuntimeError(f"Could not fetch {crypto_symbol} price for {date}: {e}") from e


def process_transaction(tx_hash: str, etherscan_api_key: str, rate_cache: Dict, price_cache: Dict, max_retries: int = 3) -> Dict:
    """
    Process a single transaction hash and calculate all fees.
    Implements retry logic with exponential backoff for network errors.

    Args:
        tx_hash: Transaction hash
        etherscan_api_key: Etherscan API key
        rate_cache: Cache for exchange rates
        price_cache: Cache for crypto prices
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        Dictionary with processed transaction data
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            # Fetch transaction details
            tx_data = get_transaction_details(tx_hash, etherscan_api_key)

            # If there was an error, return early with error info
            if tx_data.get('error'):
                return {
                    'hash': tx_hash,
                    'transaction_type': None,
                    'amount': None,
                    'wallet_address': None,
                    'date': None,
                    'fee_usd': None,
                    'fee_ils_standard': None,
                    'fee_ils_markup_6pct': None,
                    'crypto_amount_sent': None,
                    'error': tx_data['error']
                }

            # Calculate fee in USD
            fee_crypto = tx_data['fee_crypto']
            fee_symbol = tx_data['fee_crypto_symbol']
            date = tx_data['date']

            # Get crypto price in USD
            crypto_price_usd = get_crypto_usd_price(fee_symbol, date, price_cache)
            fee_usd = fee_crypto * crypto_price_usd

            # Get USD/ILS exchange rate
            try:
                usd_ils_rate = get_historical_rate(date, rate_cache)
            except ExchangeRateAPIError as e:
                raise RuntimeError(f"Could not get exchange rate for {date}: {e}") from e


            # Calculate fees in ILS
            fee_ils_standard = fee_usd * usd_ils_rate
            fee_ils_markup = fee_usd * usd_ils_rate * 1.06

            return {
                'hash': tx_hash,
                'blockchain': tx_data['blockchain'],
                'transaction_type': tx_data['transaction_type'],
                'amount': round(tx_data['amount'], 8) if tx_data['amount'] else None,
                'wallet_address': tx_data['wallet_address'],
                'date': date,
                'fee_crypto': round(fee_crypto, 8),
                'fee_crypto_symbol': fee_symbol,
                'fee_usd': round(fee_usd, 2),
                'fee_ils_standard': round(fee_ils_standard, 2),
                'fee_ils_markup_6pct': round(fee_ils_markup, 2),
                'crypto_amount_sent': round(tx_data['amount'], 8) if tx_data['amount'] else None,
                'usd_ils_rate': round(usd_ils_rate, 4),
                'error': None
            }

        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"  🔄 Error on attempt {attempt + 1}/{max_retries}. Retrying in {wait_time}s... ({e})")
                time.sleep(wait_time)
            else:
                print(f"  ❌ Failed after {max_retries} attempts: {e}")

    # If all retries failed, return error result
    return {
        'hash': tx_hash,
        'transaction_type': None,
        'amount': None,
        'wallet_address': None,
        'date': None,
        'fee_usd': None,
        'fee_ils_standard': None,
        'fee_ils_markup_6pct': None,
        'crypto_amount_sent': None,
        'error': f"Failed after {max_retries} retries: {last_error}"
    }


def load_processed_transactions(output_file: str) -> set:
    """
    Load successfully processed transaction hashes from existing output file.
    Rows with errors are excluded so they will be retried on the next run.
    Also rewrites the file without failed rows so new results can be appended cleanly.

    Args:
        output_file: Path to output CSV file

    Returns:
        Set of successfully processed transaction hashes (lowercase)
    """
    processed_hashes = set()

    if not os.path.exists(output_file):
        return processed_hashes

    try:
        with open(output_file, mode='r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            fieldnames = reader.fieldnames or []
            rows = list(reader)

        successful_rows = [r for r in rows if not r.get('error')]
        failed_count = len(rows) - len(successful_rows)

        # Rewrite file with only successful rows so failed ones can be retried
        if failed_count > 0:
            with open(output_file, mode='w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(successful_rows)

        for row in successful_rows:
            if row.get('hash'):
                processed_hashes.add(row['hash'].lower())

        print(f"Resume mode: {len(processed_hashes)} successful transactions found")
        if failed_count > 0:
            print(f"Resume mode: {failed_count} failed transactions will be retried")
    except Exception as e:
        print(f"Warning: Could not read existing output file: {e}")

    return processed_hashes


def write_transaction_to_csv(result: Dict, output_file: str, columns: List[str], write_header: bool = False, lock: Optional[threading.Lock] = None) -> bool:
    """
    Write a single transaction result to CSV file immediately (incremental write).

    Args:
        result: Transaction data dictionary
        output_file: Path to output CSV file
        columns: List of CSV column names
        write_header: Whether to write the CSV header (for new files)
        lock: Optional threading.Lock for thread-safe writes

    Returns:
        True if write was successful, False otherwise
    """
    def _do_write():
        try:
            mode = 'w' if write_header else 'a'
            with open(output_file, mode=mode, newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=columns)
                if write_header:
                    writer.writeheader()
                row = {col: result.get(col) for col in columns}
                writer.writerow(row)
            return True
        except PermissionError:
            print(f"  Error: Permission denied writing to {output_file}. Please close the file if it is open.")
            return False
        except Exception as e:
            print(f"  Error writing to CSV: {e}")
            return False

    if lock is not None:
        with lock:
            return _do_write()
    return _do_write()


def write_output_csv(output_path: str, results: List[Dict]):
    """
    Write processed results to output CSV file.

    DEPRECATED: This function is kept for backwards compatibility.
    New code should use write_transaction_to_csv for incremental writes.

    Args:
        output_path: Path to output CSV file
        results: List of processed transaction dictionaries
    """
    if not results:
        print("No results to write")
        return

    # Define CSV columns
    columns = [
        'hash',
        'blockchain',
        'transaction_type',
        'amount',
        'wallet_address',
        'date',
        'fee_crypto',
        'fee_crypto_symbol',
        'fee_usd',
        'usd_ils_rate',
        'fee_ils_standard',
        'fee_ils_markup_6pct',
        'crypto_amount_sent',
        'error'
    ]

    try:
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()

            for result in results:
                # Ensure all columns are present
                row = {col: result.get(col) for col in columns}
                writer.writerow(row)

        print(f"\nOutput written to: {output_path}")

    except Exception as e:
        print(f"Error writing output CSV: {e}")
        sys.exit(1)


def print_summary(results: List[Dict]):
    """
    Print summary statistics of processed transactions.

    Args:
        results: List of processed transaction dictionaries
    """
    total = len(results)
    successful = sum(1 for r in results if not r.get('error'))
    failed = total - successful

    total_fees_usd = sum(r.get('fee_usd', 0) or 0 for r in results if not r.get('error'))
    total_fees_ils_standard = sum(r.get('fee_ils_standard', 0) or 0 for r in results if not r.get('error'))
    total_fees_ils_markup = sum(r.get('fee_ils_markup_6pct', 0) or 0 for r in results if not r.get('error'))

    print("\n" + "="*60)
    print("PROCESSING SUMMARY")
    print("="*60)
    print(f"Total transactions processed: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"\nTotal fees (USD): ${total_fees_usd:.2f}")
    print(f"Total fees (ILS standard): ILS {total_fees_ils_standard:.2f}")
    print(f"Total fees (ILS with 6% markup): ILS {total_fees_ils_markup:.2f}")

    if failed > 0:
        print(f"\nFailed transaction hashes:")
        for r in results:
            if r.get('error'):
                print(f"  - {r['hash']}: {r['error']}")

    print("="*60 + "\n")


def main():
    """Main execution function"""
    if len(sys.argv) < 3:
        print("Usage: python process_transactions.py <input_csv> <output_csv> [workers]")
        print("\nExample:")
        print("  python process_transactions.py transactions.csv output_report.csv")
        print("  python process_transactions.py transactions.csv output_report.csv 10")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    # Optional 3rd argument: number of parallel workers
    # Default 2 is safe for Etherscan free tier (rate limiter in fetch_blockchain_data ensures 4 req/s max)
    max_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    # Get API key from environment
    etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
    if not etherscan_api_key:
        print("Warning: ETHERSCAN_API_KEY environment variable not set")
        print("ETH and USDT transactions may fail without API key")

    # Read input hashes
    hashes = read_input_csv(input_file)

    if not hashes:
        print("No transaction hashes found in input file")
        sys.exit(1)

    # Load already processed transactions for resume capability
    processed_hashes = load_processed_transactions(output_file)
    file_exists = os.path.exists(output_file)

    # Pre-load exchange rates from CSV once (avoids re-reading the file for each date)
    print("Pre-loading exchange rates...")
    rate_cache = preload_all_rates()
    price_cache: Dict = {}
    cache_lock = threading.Lock()  # Protects price_cache across threads

    # Define CSV columns
    columns = [
        'hash',
        'blockchain',
        'transaction_type',
        'amount',
        'wallet_address',
        'date',
        'fee_crypto',
        'fee_crypto_symbol',
        'fee_usd',
        'usd_ils_rate',
        'fee_ils_standard',
        'fee_ils_markup_6pct',
        'crypto_amount_sent',
        'error'
    ]

    # Tracking (protected by csv_lock since multiple threads write)
    csv_lock = threading.Lock()
    counters = {'new': 0, 'skipped': 0, 'failed': 0}
    counters_lock = threading.Lock()
    results_for_summary: List[Dict] = []

    # Filter to only unprocessed hashes
    pending_hashes = [(i, h) for i, h in enumerate(hashes, 1) if h.lower() not in processed_hashes]
    skipped_count = len(hashes) - len(pending_hashes)

    print(f"\nOutput file: {output_file}")
    print(f"Mode: {'RESUME (appending to existing file)' if file_exists else 'NEW FILE'}")
    print(f"Workers: {max_workers}")
    print(f"Skipping {skipped_count} already-processed transactions")
    print(f"Processing {len(pending_hashes)} remaining transactions...")
    print("-" * 60)

    total = len(hashes)

    def process_one(item: tuple) -> None:
        i, tx_hash = item
        print(f"[{i}/{total}] Processing: {tx_hash[:16]}...")

        # Each thread gets its own local price cache view, merged under lock
        with cache_lock:
            local_price_cache = dict(price_cache)

        assert etherscan_api_key is not None, "API key must be set"
        result = process_transaction(tx_hash, etherscan_api_key, rate_cache, local_price_cache)

        # Merge any newly fetched prices back into the shared cache
        with cache_lock:
            price_cache.update(local_price_cache)

        with counters_lock:
            is_first_new = (counters['new'] == 0 and not file_exists)

        if result.get('error'):
            with counters_lock:
                counters['failed'] += 1
            print(f"  [{tx_hash[:16]}] Failed: {result['error']}")
        else:
            print(f"  [{tx_hash[:16]}] OK")

        write_header = is_first_new
        if write_transaction_to_csv(result, output_file, columns, write_header, csv_lock):
            with counters_lock:
                counters['new'] += 1
            with cache_lock:
                processed_hashes.add(tx_hash.lower())
            results_for_summary.append(result)
        else:
            print(f"  [{tx_hash[:16]}] Processed but failed to write to disk")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_one, item) for item in pending_hashes]
        for future in as_completed(futures):
            # Propagate any unexpected exceptions from threads
            future.result()

    # Print summary
    print("\n" + "="*60)
    print("Processing complete!")
    print("="*60)
    print(f"Summary:")
    print(f"   - New transactions processed: {counters['new']}")
    print(f"   - Skipped (already processed): {skipped_count}")
    print(f"   - Failed: {counters['failed']}")
    print(f"   - Total in output file: {len(processed_hashes)}")
    print(f"   - Output: {output_file}")

    if results_for_summary:
        successful_results = [r for r in results_for_summary if not r.get('error')]
        if successful_results:
            total_fees_usd = sum(r.get('fee_usd', 0) or 0 for r in successful_results)
            total_fees_ils_standard = sum(r.get('fee_ils_standard', 0) or 0 for r in successful_results)
            total_fees_ils_markup = sum(r.get('fee_ils_markup_6pct', 0) or 0 for r in successful_results)

            print(f"\nNew transactions totals:")
            print(f"   - Total fees (USD): ${total_fees_usd:.2f}")
            print(f"   - Total fees (ILS standard): ₪{total_fees_ils_standard:.2f}")
            print(f"   - Total fees (ILS with 6% markup): ₪{total_fees_ils_markup:.2f}")

    if counters['failed'] > 0:
        print(f"\n{counters['failed']} transaction(s) failed - check the output CSV for error details")

    print("="*60 + "\n")


if __name__ == "__main__":
    main()
