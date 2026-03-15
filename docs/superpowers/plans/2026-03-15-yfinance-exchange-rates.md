# yfinance Exchange Rates Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace broken Bank of Israel / CSV exchange rate lookup with Yahoo Finance (`yfinance`) real-time fetching, with in-memory caching per run.

**Architecture:** `get_historical_rate()` fetches `ILS=X` from yfinance for a given date; on empty result (weekend/holiday) it falls back to the closest prior business day within a 7-day window. `preload_all_rates()` returns an empty dict — rates are fetched lazily and cached in memory during a run.

**Tech Stack:** Python 3.12, `yfinance>=0.2`, `pandas` (already in requirements), `pytest`

---

## Chunk 1: Dependency + Failing Tests

### Task 1: Add yfinance to requirements and install

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add yfinance to requirements.txt**

  Open `requirements.txt` and add:
  ```
  yfinance>=0.2.0
  ```

- [ ] **Step 2: Install the dependency**

  ```bash
  cd /workspaces/sent-trx-fees && pip install yfinance>=0.2.0
  ```
  Expected: Successfully installed yfinance (no errors)

- [ ] **Step 3: Commit**

  ```bash
  git add requirements.txt
  git commit -m "chore: add yfinance dependency for exchange rate fetching"
  ```

---

### Task 2: Write failing tests for the new fetch_exchange_rates module

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_fetch_exchange_rates.py`

Notes on the mock fixture: `yfinance.download` returns a DataFrame with a two-level `pd.MultiIndex` on columns — level 0 is the field name (`"Close"`, `"Open"`, …), level 1 is the ticker (`"ILS=X"`). The `_make_df` helper below must use `pd.MultiIndex.from_tuples([("Close", "ILS=X")])` to match real yfinance output exactly.

- [ ] **Step 1: Create the tests directory and write failing tests**

  Create `tests/__init__.py` (empty file), then create `tests/test_fetch_exchange_rates.py`:

  ```python
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
  ```

- [ ] **Step 2: Run tests to verify they FAIL (module not yet rewritten)**

  ```bash
  cd /workspaces/sent-trx-fees && python -m pytest tests/test_fetch_exchange_rates.py -v 2>&1 | head -40
  ```
  Expected: tests FAIL (ImportError or AttributeError — `yf` not in current module)

- [ ] **Step 3: Commit the failing tests**

  ```bash
  git add tests/
  git commit -m "test: add failing tests for yfinance-based exchange rate fetching"
  ```

---

## Chunk 2: Implementation

### Task 3: Rewrite fetch_exchange_rates.py

**Files:**
- Modify: `scripts/fetch_exchange_rates.py` (full rewrite)

- [ ] **Step 1: Replace the file contents**

  Rewrite `scripts/fetch_exchange_rates.py` to contain exactly:

  ```python
  """
  Fetch historical USD/ILS exchange rates from Yahoo Finance.
  Rates are fetched on demand and cached in memory for the duration of a run.
  """

  import math
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


  def _extract_close(df) -> Optional[float]:
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


  def _extract_last_close(df) -> Optional[float]:
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
  ```

- [ ] **Step 2: Run the tests — all must pass**

  ```bash
  cd /workspaces/sent-trx-fees && python -m pytest tests/test_fetch_exchange_rates.py -v
  ```
  Expected: ALL 8 tests PASS, 0 failures

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/fetch_exchange_rates.py
  git commit -m "feat: replace CSV/BoI exchange rates with yfinance real-time fetching"
  ```

---

### Task 4: Update process_transactions.py log message + delete update_exchange_rates.py

**Files:**
- Modify: `scripts/process_transactions.py` (line ~435)
- Delete: `scripts/update_exchange_rates.py`

- [ ] **Step 1: Confirm update_exchange_rates.py is not imported anywhere**

  ```bash
  grep -r "update_exchange_rates" /workspaces/sent-trx-fees/scripts/
  ```
  Expected: no output (no imports)

- [ ] **Step 2: Update the stale log message in process_transactions.py**

  Find:
  ```python
  # Pre-load exchange rates from CSV once (avoids re-reading the file for each date)
  print("Pre-loading exchange rates...")
  rate_cache = preload_all_rates()
  ```
  Replace with:
  ```python
  # Exchange rates are fetched on demand from Yahoo Finance and cached in memory
  print("Exchange rates will be fetched on demand from Yahoo Finance...")
  rate_cache = preload_all_rates()
  ```

- [ ] **Step 3: Delete the obsolete script**

  ```bash
  rm /workspaces/sent-trx-fees/scripts/update_exchange_rates.py
  ```

- [ ] **Step 4: Commit both changes together**

  ```bash
  git add scripts/process_transactions.py
  git add -u scripts/update_exchange_rates.py
  git commit -m "chore: remove CSV rate update script and update log messages"
  ```

---

## Chunk 3: Verification

### Task 5: End-to-end verification

**Files:** none (read-only verification)

- [ ] **Step 1: Run full test suite**

  ```bash
  cd /workspaces/sent-trx-fees && python -m pytest tests/ -v
  ```
  Expected: All tests pass, no import errors

- [ ] **Step 2: Optional smoke test against real network**

  ```bash
  cd /workspaces/sent-trx-fees/scripts && python fetch_exchange_rates.py 2026-03-04
  ```
  Expected: prints a USD/ILS rate in the range 3.05–3.15 (not today's rate ~3.147)

  ```bash
  python fetch_exchange_rates.py 2026-03-07
  ```
  Expected: prints the same rate as 2026-03-06 (Friday, since Saturday has no market data)

- [ ] **Step 3: Verify the dual-rate bug is fixed**

  Run process_transactions on a small test (1 worker to keep it quiet):
  ```bash
  cd /workspaces/sent-trx-fees/scripts
  python process_transactions.py ../input.csv ../output_test.csv 1
  ```

  Then assert exactly one unique rate per date:
  ```bash
  python3 -c "
  import csv
  from collections import defaultdict
  rows = list(csv.DictReader(open('../output_test.csv')))
  by_date = defaultdict(set)
  for r in rows:
      if r.get('date') and r.get('usd_ils_rate'):
          by_date[r['date']].add(r['usd_ils_rate'])
  problems = {d: rates for d, rates in by_date.items() if len(rates) > 1}
  if problems:
      print('FAIL - multiple rates for same date:', problems)
  else:
      print('PASS - each date has exactly one unique usd_ils_rate')
  "
  ```
  Expected output: `PASS - each date has exactly one unique usd_ils_rate`

- [ ] **Step 4: Clean up test output**

  ```bash
  rm -f /workspaces/sent-trx-fees/output_test.csv
  ```
