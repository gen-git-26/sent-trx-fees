"""
Fetch historical USD/ILS exchange rates from Yahoo Finance.
Rates are fetched on demand and cached in memory for the duration of a run.
"""

import math
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, Dict


class ExchangeRateAPIError(Exception):
    """Raised when a USD/ILS exchange rate cannot be fetched."""
    pass


def get_historical_rate(date: str, cache: Optional[Dict] = None) -> float:
    """
    Return the USD/ILS exchange rate for *date* (format: 'YYYY-MM-DD').

    Strategy:
      1. Return from cache if present.
      2. Fetch the single day's Close from Yahoo Finance (ILS=X).
      3. If empty (weekend / holiday), fetch the previous 7 calendar days
         and use the most recent available Close.

    Args:
        date: Date string 'YYYY-MM-DD'
        cache: Optional dict for in-process caching (shared across calls).
               If None, no caching is performed.

    Returns:
        USD/ILS rate as float

    Raises:
        ExchangeRateAPIError: if no rate can be found
    """
    if cache is not None and date in cache:
        return cache[date]

    # --- single-day fetch ---
    next_day = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        df = yf.download("ILS=X", start=date, end=next_day, auto_adjust=True, progress=False)
    except Exception as exc:
        raise ExchangeRateAPIError(f"yfinance error for {date}: {exc}") from exc

    rate = _extract_close(df)
    if rate is not None:
        if cache is not None:
            cache[date] = rate
        return rate

    # --- fallback: 7-day window (weekends / holidays) ---
    window_start = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        df_window = yf.download("ILS=X", start=window_start, end=next_day, auto_adjust=True, progress=False)
    except Exception as exc:
        raise ExchangeRateAPIError(f"yfinance fallback error for {date}: {exc}") from exc

    rate = _extract_last_close(df_window)
    if rate is not None:
        if cache is not None:
            cache[date] = rate
        return rate

    raise ExchangeRateAPIError(
        f"No USD/ILS rate available for {date} or the 7 preceding calendar days."
    )


def _extract_close(df: "pd.DataFrame") -> Optional[float]:
    """Return the Close value from a single-row yfinance DataFrame, or None."""
    if df is None or df.empty:
        return None
    try:
        value = df["Close"]["ILS=X"].iloc[0]
        if value is None or math.isnan(float(value)):
            return None
        return float(value)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _extract_last_close(df: "pd.DataFrame") -> Optional[float]:
    """Return the last non-NaN Close value from a multi-row yfinance DataFrame, or None."""
    if df is None or df.empty:
        return None
    try:
        series = df["Close"]["ILS=X"].dropna()
        if series.empty:
            return None
        return float(series.iloc[-1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def preload_all_rates() -> Dict[str, float]:
    """
    No-op stub kept for API compatibility with process_transactions.py.
    Rates are now fetched lazily on demand from Yahoo Finance.
    Returns an empty dict.
    """
    return {}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fetch_exchange_rates.py <YYYY-MM-DD>")
        sys.exit(1)

    date_arg = sys.argv[1]
    print(f"Fetching USD/ILS rate for: {date_arg}")
    try:
        r = get_historical_rate(date_arg)
        print(f"USD/ILS on {date_arg}: {r:.4f}")
        print(f"With 6% markup:        {r * 1.06:.4f}")
    except ExchangeRateAPIError as e:
        print(f"Error: {e}")
        sys.exit(1)
