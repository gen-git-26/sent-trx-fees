"""
Tests for fetch_exchange_rates.py — yfinance-based implementation.
Uses unittest.mock to avoid real network calls.
"""
import math
import pytest
from unittest.mock import patch
import pandas as pd
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from fetch_exchange_rates import get_historical_rate, preload_all_rates, ExchangeRateAPIError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(close_value: float, idx_date: str) -> pd.DataFrame:
    """Build a minimal yfinance-style DataFrame with proper MultiIndex columns."""
    idx = pd.DatetimeIndex([idx_date], name="Date")
    cols = pd.MultiIndex.from_tuples([("Close", "ILS=X")], names=["Price", "Ticker"])
    return pd.DataFrame([[close_value]], index=idx, columns=cols)


def _make_window_df(rows: list) -> pd.DataFrame:
    """Build a multi-row yfinance DataFrame for fallback window tests.
    rows: list of (date_str, close_value)
    """
    idx = pd.DatetimeIndex([r[0] for r in rows], name="Date")
    cols = pd.MultiIndex.from_tuples([("Close", "ILS=X")], names=["Price", "Ticker"])
    return pd.DataFrame([[r[1]] for r in rows], index=idx, columns=cols)


def _make_empty_df() -> pd.DataFrame:
    """Empty DataFrame — yfinance returns this for weekends / market holidays."""
    cols = pd.MultiIndex.from_tuples([("Close", "ILS=X")], names=["Price", "Ticker"])
    return pd.DataFrame(columns=cols)


# ---------------------------------------------------------------------------
# preload_all_rates
# ---------------------------------------------------------------------------

def test_preload_all_rates_returns_empty_dict():
    """preload_all_rates() must return an empty dict (no CSV read, no network)."""
    result = preload_all_rates()
    assert result == {}


# ---------------------------------------------------------------------------
# Cache hit
# ---------------------------------------------------------------------------

def test_get_historical_rate_returns_cached_value():
    """If the date is already in the cache, no network call is made."""
    cache = {"2026-03-04": 3.073}
    with patch("fetch_exchange_rates.yf.download") as mock_dl:
        rate = get_historical_rate("2026-03-04", cache)
    assert rate == 3.073
    mock_dl.assert_not_called()


# ---------------------------------------------------------------------------
# Normal trading day
# ---------------------------------------------------------------------------

def test_get_historical_rate_fetches_and_caches():
    """Fetches the Close price for a normal trading day and stores it in cache."""
    df = _make_df(3.073, "2026-03-04")
    cache = {}
    with patch("fetch_exchange_rates.yf.download", return_value=df) as mock_dl:
        rate = get_historical_rate("2026-03-04", cache)

    assert rate == pytest.approx(3.073)
    assert cache["2026-03-04"] == pytest.approx(3.073)
    mock_dl.assert_called_once_with(
        "ILS=X",
        start="2026-03-04",
        end="2026-03-05",
        auto_adjust=True,
        progress=False,
    )


# ---------------------------------------------------------------------------
# Weekend / holiday fallback — data exists in window
# ---------------------------------------------------------------------------

def test_get_historical_rate_weekend_falls_back_to_prior_day():
    """On weekend (empty single-day df), uses last Close from 7-day window."""
    empty_df = _make_empty_df()
    # Friday data returned when querying the 7-day window ending on Saturday
    window_df = _make_window_df([("2026-03-04", 3.055), ("2026-03-06", 3.061)])

    call_count = {"n": 0}

    def fake_download(ticker, start, end, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return empty_df   # single-day query → empty
        return window_df      # 7-day window → has data

    cache = {}
    with patch("fetch_exchange_rates.yf.download", side_effect=fake_download):
        rate = get_historical_rate("2026-03-07", cache)  # Saturday

    assert rate == pytest.approx(3.061)           # last row of window
    assert cache["2026-03-07"] == pytest.approx(3.061)


# ---------------------------------------------------------------------------
# Weekend / holiday fallback — entire 7-day window is also empty
# ---------------------------------------------------------------------------

def test_get_historical_rate_raises_when_fallback_window_empty():
    """Raises ExchangeRateAPIError when both the single-day AND the 7-day window return no data."""
    empty_df = _make_empty_df()
    with patch("fetch_exchange_rates.yf.download", return_value=empty_df):
        with pytest.raises(ExchangeRateAPIError):
            get_historical_rate("2026-03-07", {})


# ---------------------------------------------------------------------------
# Network error
# ---------------------------------------------------------------------------

def test_get_historical_rate_raises_on_network_error():
    """Raises ExchangeRateAPIError when yfinance.download throws."""
    with patch("fetch_exchange_rates.yf.download", side_effect=Exception("timeout")):
        with pytest.raises(ExchangeRateAPIError):
            get_historical_rate("2026-03-04", {})


# ---------------------------------------------------------------------------
# cache=None
# ---------------------------------------------------------------------------

def test_get_historical_rate_works_without_cache():
    """cache=None is valid — returns a float and makes no attempt to store."""
    df = _make_df(3.073, "2026-03-04")
    with patch("fetch_exchange_rates.yf.download", return_value=df) as mock_dl:
        rate = get_historical_rate("2026-03-04")   # no cache arg
    assert isinstance(rate, float)
    assert rate == pytest.approx(3.073)
    # Second call with None still hits network (no hidden shared state)
    with patch("fetch_exchange_rates.yf.download", return_value=df) as mock_dl2:
        get_historical_rate("2026-03-04")
    mock_dl2.assert_called_once()
