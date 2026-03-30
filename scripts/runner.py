"""
runner.py — callable processing pipeline for the Streamlit UI.

Exports:
    validate_csv_columns(file_path)  — raises MissingColumnsError if invalid
    run_pipeline(file_path)          — generator that yields progress dicts,
                                       final item has key 'rows' with all results
"""

import os
import sys
import csv
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Generator

from dotenv import load_dotenv

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

load_dotenv()

from fetch_exchange_rates import preload_all_rates, get_historical_rate, ExchangeRateAPIError
from process_transactions import process_transaction, get_crypto_usd_price, load_processed_transactions
from eth_chash_out_exchange import get_transactions_from_address, process_transaction_data, TransactionValidationError
from process_merchant_csv import (
    read_and_filter_merchant_csv,
    normalize_cashin_row,
    normalize_cashout_row,
    OUTPUT_COLUMNS,
)

REQUIRED_COLUMNS = {'txClass', 'status', 'txHash', 'toAddress', 'cryptoCode'}


class MissingColumnsError(Exception):
    pass


def validate_csv_columns(file_path: str) -> None:
    """Raise MissingColumnsError if required columns are absent or file is empty."""
    try:
        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
    except Exception as e:
        raise MissingColumnsError(f"Cannot read file: {e}")

    if not fieldnames:
        raise MissingColumnsError("File is empty or has no header row.")

    missing = REQUIRED_COLUMNS - set(fieldnames)
    if missing:
        raise MissingColumnsError(f"Missing required columns: {', '.join(sorted(missing))}")


def run_pipeline(file_path: str, max_workers: int = 2) -> Generator[Dict, None, None]:
    """
    Run the full processing pipeline.

    Yields dicts:
        {'type': 'status', 'message': str}
        {'type': 'progress', 'current': int, 'total': int, 'hash': str}
        {'type': 'error', 'hash': str, 'reason': str}
        {'type': 'done', 'rows': List[Dict], 'new': int, 'failed': int, 'skipped': int}
        {'type': 'fatal', 'message': str}   — if pipeline cannot proceed
    """
    etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')

    try:
        cashin_hashes, cashout_addresses = read_and_filter_merchant_csv(file_path)
    except SystemExit:
        yield {'type': 'fatal', 'message': 'Failed to parse the uploaded CSV.'}
        return

    if not cashin_hashes and not cashout_addresses:
        yield {'type': 'fatal', 'message': 'No valid transactions found after filtering (check txClass/status columns).'}
        return

    yield {'type': 'status', 'message': f'Found {len(cashin_hashes)} cashin and {len(cashout_addresses)} cashout transactions. Pre-loading exchange rates...'}

    try:
        rate_cache: Dict = preload_all_rates()
    except Exception as e:
        yield {'type': 'fatal', 'message': f'Failed to load exchange rates: {e}'}
        return

    price_cache: Dict = {}
    cache_lock = threading.Lock()
    counters = {'new': 0, 'failed': 0, 'skipped': 0}
    counters_lock = threading.Lock()
    rows: List[Dict] = []
    rows_lock = threading.Lock()
    errors: List[Dict] = []

    total = len(cashin_hashes) + len(cashout_addresses)
    processed_count = [0]

    # --- Cashin ---
    def process_one_cashin(item):
        i, tx_hash = item
        with cache_lock:
            local_price_cache = dict(price_cache)

        result = process_transaction(tx_hash, etherscan_api_key, rate_cache, local_price_cache)

        with cache_lock:
            price_cache.update(local_price_cache)

        result = normalize_cashin_row(result)

        with rows_lock:
            rows.append(result)

        with counters_lock:
            processed_count[0] += 1
            if result.get('error'):
                counters['failed'] += 1
                errors.append({'hash': tx_hash, 'reason': result['error']})
            else:
                counters['new'] += 1

        return {'type': 'progress', 'current': processed_count[0], 'total': total, 'hash': tx_hash}

    # --- Cashout ETH ---
    def process_one_cashout(item):
        idx, address = item
        updates = []

        if not etherscan_api_key:
            with counters_lock:
                processed_count[0] += 1
                counters['skipped'] += 1
            return updates

        try:
            matching_txs = get_transactions_from_address(address, etherscan_api_key)
            if not matching_txs:
                with counters_lock:
                    processed_count[0] += 1
                    counters['skipped'] += 1
                return updates

            for tx_data in matching_txs:
                tx_hash = tx_data['hash']
                with cache_lock:
                    local_price_cache = dict(price_cache)

                result = process_transaction_data(tx_data, local_price_cache, rate_cache)

                with cache_lock:
                    price_cache.update(local_price_cache)

                if result:
                    result = normalize_cashout_row(result)
                    with rows_lock:
                        rows.append(result)
                    with counters_lock:
                        counters['new'] += 1
                else:
                    with counters_lock:
                        counters['failed'] += 1
                    errors.append({'hash': tx_hash, 'reason': 'process_transaction_data returned None'})

            with counters_lock:
                processed_count[0] += 1
            updates.append({'type': 'progress', 'current': processed_count[0], 'total': total, 'hash': address})

        except (TransactionValidationError, Exception) as e:
            with counters_lock:
                processed_count[0] += 1
                counters['failed'] += 1
            errors.append({'hash': address, 'reason': str(e)})
            updates.append({'type': 'progress', 'current': processed_count[0], 'total': total, 'hash': address})

        return updates

    yield {'type': 'status', 'message': f'Processing {len(cashin_hashes)} cashin transactions...'}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one_cashin, item): item
                   for item in enumerate(cashin_hashes, 1)}
        for future in as_completed(futures):
            update = future.result()
            yield update

    if cashout_addresses:
        yield {'type': 'status', 'message': f'Processing {len(cashout_addresses)} cashout ETH addresses...'}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_one_cashout, item): item
                       for item in enumerate(cashout_addresses, 1)}
            for future in as_completed(futures):
                updates = future.result()
                for update in updates:
                    yield update

    for err in errors:
        yield {'type': 'error', 'hash': err['hash'], 'reason': err['reason']}

    yield {
        'type': 'done',
        'rows': rows,
        'new': counters['new'],
        'failed': counters['failed'],
        'skipped': counters['skipped'],
    }
