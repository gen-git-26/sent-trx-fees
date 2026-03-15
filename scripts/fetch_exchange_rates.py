"""
Fetch historical USD/ILS exchange rates.
Uses Bank of Israel API for current date, local CSV file for historical dates.
"""

import requests
import csv
import os
import threading
from datetime import datetime
from typing import Optional, Dict

_csv_write_lock = threading.Lock()


class ExchangeRateAPIError(Exception):
    """Custom exception for exchange rate API errors"""
    pass


def _get_csv_path() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(script_dir), 'assets', 'usd_ils_rates.csv')


def _fetch_boi_rate(date_str: str) -> Optional[float]:
    """Fetch a single date's USD/ILS rate from Bank of Israel API."""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        params = {
            'currencyCode': 'USD',
            'startDate': date_obj.strftime('%Y-%m-%d'),
            'endDate': date_obj.strftime('%Y-%m-%d'),
        }
        response = requests.get(
            "https://www.boi.org.il/PublicApi/GetExchangeRates",
            params=params, timeout=15
        )
        response.raise_for_status()
        for entry in response.json().get('exchangeRates', []):
            rate = entry.get('currentExchangeRate') or entry.get('rate')
            if rate:
                return float(rate)
    except Exception:
        pass
    return None


def _save_rate_to_csv(date_str: str, rate: float) -> None:
    """Add a new rate to the CSV file, keeping it sorted descending by date (thread-safe)."""
    csv_path = _get_csv_path()
    date_formatted = datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y')

    with _csv_write_lock:
        existing: Dict[str, float] = {}
        if os.path.exists(csv_path):
            with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
                for row in csv.DictReader(f):
                    try:
                        d = datetime.strptime(row['date'].strip(), '%d.%m.%Y').strftime('%Y-%m-%d')
                        existing[d] = float(row['rate'].strip().replace(',', '.'))
                    except (ValueError, KeyError):
                        continue
        existing[date_str] = rate
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'rate'])
            for d in sorted(existing.keys(), reverse=True):
                d_fmt = datetime.strptime(d, '%Y-%m-%d').strftime('%d.%m.%Y')
                writer.writerow([d_fmt, f'\t{existing[d]:.4f}'])


def get_historical_rate(date: str, cache: Optional[Dict] = None) -> float:
    """
    Fetch historical USD/ILS exchange rate for a specific date.

    Strategy:
    - If date is today: use Bank of Israel API (fastest, most current)
    - If date is historical: use Investing.com (supports any past date)

    Args:
        date: Date string in format 'YYYY-MM-DD'
        cache: Optional dictionary to cache exchange rates and reduce API calls

    Returns:
        USD/ILS exchange rate as float

    Raises:
        ExchangeRateAPIError: If unable to fetch exchange rate
    """
    if cache is not None and date in cache:
        return cache[date]

    try:
        # Check if the date is today
        today = datetime.now().strftime('%Y-%m-%d')

        if date == today:
            # For current date, use Bank of Israel API (faster and real-time)
            return get_rate_from_bank_of_israel(date, cache)
        else:
            # For historical dates, use local CSV file (2021-today)
            return get_rate_from_csv(date, cache)

    except Exception as e:
        raise ExchangeRateAPIError(f"Error fetching exchange rate for {date}: {str(e)}")


def get_rate_from_bank_of_israel(date: str, cache: Optional[Dict] = None) -> float:
    """
    Fetch USD/ILS exchange rate from Bank of Israel API (for current date).

    Args:
        date: Date string in format 'YYYY-MM-DD'
        cache: Optional dictionary to cache exchange rates

    Returns:
        USD/ILS exchange rate as float
    """
    if cache is not None and date in cache:
        return cache[date]

    try:
        url = "https://www.boi.org.il/PublicApi/GetExchangeRates"
        params = {
            'currencyCode': 'USD'
        }

        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Parse the response
        if isinstance(data, dict) and 'exchangeRates' in data:
            rates = data['exchangeRates']
            if rates and len(rates) > 0:
                for rate_data in rates:
                    if rate_data.get('key') == 'USD' or rate_data.get('currencyCode') == 'USD':
                        rate = float(rate_data.get('currentExchangeRate', 0))
                        if rate > 0:
                            if cache is not None:
                                cache[date] = rate
                            return rate

        raise ExchangeRateAPIError("Could not parse Bank of Israel response")

    except Exception as e:
        raise ExchangeRateAPIError(f"Error fetching from Bank of Israel: {str(e)}")


def get_rate_from_csv(date: str, cache: Optional[Dict] = None) -> float:
    """
    Fetch USD/ILS exchange rate from local CSV file.

    Args:
        date: Date string in format 'YYYY-MM-DD'
        cache: Optional dictionary to cache exchange rates

    Returns:
        USD/ILS exchange rate as float
    """
    if cache is not None and date in cache:
        return cache[date]

    try:
        csv_path = _get_csv_path()

        if not os.path.exists(csv_path):
            raise ExchangeRateAPIError(
                f"Exchange rate CSV file not found at: {csv_path}. "
                f"Please ensure assets/usd_ils_rates.csv exists."
            )

        # Read the CSV file and build a dictionary of rates
        rates_dict = {}

        with open(csv_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig to handle BOM
            reader = csv.DictReader(f)

            for row in reader:
                # Date format in CSV: DD.MM.YYYY
                csv_date_str = row['date'].strip()
                csv_rate_str = row['rate'].strip()

                try:
                    # Parse date and rate
                    row_date = datetime.strptime(csv_date_str, '%d.%m.%Y')
                    rate = float(csv_rate_str.replace(',', '.'))

                    # Store in our format (YYYY-MM-DD)
                    date_key = row_date.strftime('%Y-%m-%d')
                    rates_dict[date_key] = rate

                except (ValueError, KeyError):
                    continue

        # Look for exact date match
        if date in rates_dict:
            rate = rates_dict[date]
            if cache is not None:
                cache[date] = rate
            return rate

        # Not in CSV — try fetching from Bank of Israel and save for future runs
        fetched = _fetch_boi_rate(date)
        if fetched:
            _save_rate_to_csv(date, fetched)
            if cache is not None:
                cache[date] = fetched
            return fetched

        # Weekend/holiday — use closest previous business day rate
        rate = get_closest_rate_from_dict(date, rates_dict, cache)
        if rate is not None:
            return rate

        # If we couldn't find any rate in the data, raise an error
        raise ExchangeRateAPIError(
            f"No exchange rate data found for {date} in the CSV file. "
            f"The CSV contains rates from 2021 to present. "
            f"Please add the rate manually or update the CSV file at: {csv_path}"
        )

    except ExchangeRateAPIError:
        # Re-raise our custom errors
        raise
    except Exception as e:
        raise ExchangeRateAPIError(f"Error reading exchange rates from CSV: {str(e)}")


def get_closest_rate_from_dict(target_date: str, rates_dict: Dict[str, float], cache: Optional[Dict] = None) -> Optional[float]:
    """
    Find the closest available rate from a dictionary of rates.

    Args:
        target_date: Date string in format 'YYYY-MM-DD'
        rates_dict: Dictionary mapping dates to exchange rates
        cache: Optional cache dictionary

    Returns:
        USD/ILS exchange rate as float, or None if no suitable rate found
    """
    target_dt = datetime.strptime(target_date, '%Y-%m-%d')

    # Look for the most recent date before or on target date
    best_date = None
    best_rate = None

    for date_str, rate in rates_dict.items():
        date_dt = datetime.strptime(date_str, '%Y-%m-%d')

        # Only consider dates on or before target
        if date_dt <= target_dt:
            if best_date is None or date_dt > best_date:
                best_date = date_dt
                best_rate = rate

    if best_rate is not None:
        if cache is not None:
            cache[target_date] = best_rate
        return best_rate

    # If no rate found, return None (don't use fallback)
    return None




def preload_all_rates() -> Dict[str, float]:
    """
    Load all USD/ILS rates from the local CSV file into a dict at startup.
    Returns a cache dict ready to pass to get_historical_rate().
    This avoids re-reading the CSV file once per unique date during processing.
    """
    cache: Dict[str, float] = {}
    csv_path = _get_csv_path()

    if not os.path.exists(csv_path):
        print(f"Warning: Exchange rate CSV not found at {csv_path}. Will use fallback rate.")
        return cache

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    row_date = datetime.strptime(row['date'].strip(), '%d.%m.%Y')
                    rate = float(row['rate'].strip().replace(',', '.'))
                    cache[row_date.strftime('%Y-%m-%d')] = rate
                except (ValueError, KeyError):
                    continue
        print(f"Loaded {len(cache)} exchange rate entries from CSV.")
    except Exception as e:
        print(f"Warning: Could not preload exchange rates: {e}")

    return cache


def get_current_rate(cache: Optional[Dict] = None) -> float:
    """
    Get current USD/ILS exchange rate.

    Args:
        cache: Optional dictionary to cache the rate

    Returns:
        Current USD/ILS exchange rate as float
    """
    today = datetime.now().strftime('%Y-%m-%d')
    return get_historical_rate(today, cache)


if __name__ == "__main__":
    # Test the functions
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fetch_exchange_rates.py <date>")
        print("Date format: YYYY-MM-DD")
        sys.exit(1)

    date = sys.argv[1]
    cache = {}

    print(f"Fetching USD/ILS exchange rate for: {date}")

    try:
        rate = get_historical_rate(date, cache)
        print(f"USD/ILS rate on {date}: {rate:.4f}")

        # Calculate with 6% markup
        rate_with_markup = rate * 1.06
        print(f"USD/ILS rate with 6% markup: {rate_with_markup:.4f}")

    except ExchangeRateAPIError as e:
        print(f"Error: {e}")
        sys.exit(1)
