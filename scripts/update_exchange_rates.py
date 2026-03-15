"""
Update assets/usd_ils_rates.csv with missing USD/ILS rates from the Bank of Israel API.

Finds the last date in the CSV, fetches all missing business days up to today,
and prepends the new rows to the file (newest first, matching existing format).

Usage:
    python scripts/update_exchange_rates.py

Schedule with cron (run every weekday at 09:00):
    0 9 * * 1-5 cd /path/to/project && python scripts/update_exchange_rates.py
"""

import os
import csv
import sys
import time
import requests
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional


_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
CSV_PATH = os.path.join(_project_root, 'assets', 'usd_ils_rates.csv')

BOI_API_URL = "https://www.boi.org.il/PublicApi/GetExchangeRates"


# ---------------------------------------------------------------------------
# Read existing CSV
# ---------------------------------------------------------------------------

def read_existing_rates() -> Dict[date, float]:
    """Load all existing rates from the CSV into {date: rate}."""
    rates: Dict[date, float] = {}

    if not os.path.exists(CSV_PATH):
        print(f"CSV not found at {CSV_PATH} — will create a new file.")
        return rates

    with open(CSV_PATH, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                d = datetime.strptime(row['date'].strip(), '%d.%m.%Y').date()
                rate = float(row['rate'].strip().replace(',', '.'))
                rates[d] = rate
            except (ValueError, KeyError):
                continue

    return rates


def get_last_date_in_csv(rates: Dict[date, float]) -> Optional[date]:
    """Return the most recent date in the existing rates dict, or None if empty."""
    return max(rates.keys()) if rates else None


# ---------------------------------------------------------------------------
# Fetch from Bank of Israel
# ---------------------------------------------------------------------------

def fetch_rate_for_date(target_date: date) -> Optional[float]:
    """
    Fetch USD/ILS rate for a specific date from Bank of Israel API.
    Returns None if not available (e.g. weekend/holiday or future date).
    """
    try:
        params = {
            'currencyCode': 'USD',
            'startDate': target_date.strftime('%Y-%m-%d'),
            'endDate': target_date.strftime('%Y-%m-%d'),
        }
        response = requests.get(BOI_API_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            return None

        exchange_rates = data.get('exchangeRates', [])
        if not exchange_rates:
            return None

        for entry in exchange_rates:
            # The API returns the current rate keyed under 'currentExchangeRate'
            rate = entry.get('currentExchangeRate') or entry.get('rate')
            if rate:
                return float(rate)

    except Exception as e:
        print(f"  Warning: Could not fetch rate for {target_date}: {e}")

    return None


def fetch_missing_rates(missing_dates: List[date]) -> Dict[date, float]:
    """
    Fetch rates for a list of dates from the Bank of Israel API.
    Skips dates where the API returns no data (weekends/holidays).
    Adds a short sleep between requests to avoid rate limiting.
    """
    fetched: Dict[date, float] = {}

    for i, d in enumerate(missing_dates):
        print(f"  Fetching {d.strftime('%d.%m.%Y')}... ", end='', flush=True)
        rate = fetch_rate_for_date(d)

        if rate is not None and rate > 0:
            fetched[d] = rate
            print(f"{rate:.4f}")
        else:
            print("no data (weekend/holiday — skipped)")

        if i < len(missing_dates) - 1:
            time.sleep(0.5)  # Polite rate limiting

    return fetched


# ---------------------------------------------------------------------------
# Write updated CSV
# ---------------------------------------------------------------------------

def write_csv(rates: Dict[date, float]) -> None:
    """
    Write all rates to CSV, sorted by date descending (newest first).
    Format: DD.MM.YYYY,\t{rate}  (matches existing file format)
    """
    sorted_dates = sorted(rates.keys(), reverse=True)

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'rate'])
        for d in sorted_dates:
            rate = rates[d]
            writer.writerow([d.strftime('%d.%m.%Y'), f'\t{rate:.4f}'])

    print(f"CSV written: {len(sorted_dates)} total entries.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    today = date.today()
    print(f"Updating USD/ILS exchange rates — {today.strftime('%d.%m.%Y')}")
    print(f"CSV path: {CSV_PATH}")
    print()

    # Load existing rates
    existing_rates = read_existing_rates()
    last_date = get_last_date_in_csv(existing_rates)

    if last_date:
        print(f"Last date in CSV: {last_date.strftime('%d.%m.%Y')}")
    else:
        print("CSV is empty — will fetch from 2021-01-01 to today.")
        last_date = date(2021, 1, 1) - timedelta(days=1)

    if last_date >= today:
        print("CSV is already up to date.")
        return

    # Build list of missing calendar days (BOI will skip weekends/holidays)
    missing_dates: List[date] = []
    current = last_date + timedelta(days=1)
    while current <= today:
        if current not in existing_rates:
            missing_dates.append(current)
        current += timedelta(days=1)

    print(f"Fetching {len(missing_dates)} missing dates ({missing_dates[0].strftime('%d.%m.%Y')} to {missing_dates[-1].strftime('%d.%m.%Y')})...")
    print()

    new_rates = fetch_missing_rates(missing_dates)

    if not new_rates:
        print("\nNo new rates fetched.")
        return

    # Merge and write
    all_rates = {**existing_rates, **new_rates}
    print()
    write_csv(all_rates)

    print(f"\nDone: added {len(new_rates)} new rate(s).")


if __name__ == "__main__":
    main()
