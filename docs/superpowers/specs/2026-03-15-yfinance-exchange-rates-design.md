# Design: Replace CSV/BoI Exchange Rate Lookup with Yahoo Finance

**Date:** 2026-03-15
**Status:** Approved

---

## Problem

The current exchange rate system has two critical failures:

1. The Bank of Israel API (`/PublicApi/GetExchangeRates`) was **empirically observed** to ignore `startDate`/`endDate` parameters — it always returns the current rate in `currentExchangeRate` regardless of the queried date range. This was confirmed by calling the API with `startDate=2026-03-04&endDate=2026-03-06` and receiving `lastUpdate: 2026-03-13` in the response.
2. `fetch_exchange_rates.py` falls back to a local CSV file that can contain incorrect data (historical dates saved via the broken BoI API call contain today's rate, not the historical one).

The result: transactions processed after their transaction date receive the wrong exchange rate.

---

## Goal

Replace all exchange rate lookups with real-time fetching from Yahoo Finance (`yfinance`) using the `ILS=X` ticker, with in-memory caching per run. No CSV file required.

---

## Architecture

### Files changed: `scripts/fetch_exchange_rates.py` (rewrite), `scripts/update_exchange_rates.py` (delete)

**Public interface** (signatures unchanged — no breaking changes for callers):

```python
get_historical_rate(date: str, cache: Optional[Dict] = None) -> float
preload_all_rates() -> Dict   # now returns {} — see note below
ExchangeRateAPIError          # kept
```

**New internal flow for `get_historical_rate`:**

```
get_historical_rate(date, cache)
  1. Check cache[date] → return if hit
  2. yf.download("ILS=X", start=date, end=(date + timedelta(days=1)).strftime('%Y-%m-%d'),
                 auto_adjust=True, progress=False)
     e.g. for date="2026-03-04": start="2026-03-04", end="2026-03-05"
     The `end` parameter is exclusive in yfinance.
  3. Access Close price: df["Close"]["ILS=X"].iloc[0]
     (yfinance returns a MultiIndex DataFrame; top level is ticker name)
     If value is NaN or DataFrame is empty → go to step 4
  4. If empty/NaN (weekend/holiday): fetch a 7-day window ending on date,
     take the last non-NaN Close row
     → cache under original date → return
  5. If nothing found → raise ExchangeRateAPIError
```

**`preload_all_rates()` semantic change:**
- Signature unchanged, returns `{}` instead of a populated dict
- Rates are now fetched lazily on first access per unique date
- **Caller impact:** `process_transactions.py` line 435 prints `"Pre-loading exchange rates..."` — this log message should be updated to `"Exchange rates will be fetched on demand from Yahoo Finance"` as part of this change

---

## Thread Safety

`process_transactions.py` shares `rate_cache` across `ThreadPoolExecutor` threads. Previously, threads only read a pre-populated dict (safe). After this change, threads will also write lazily-fetched rates into the cache.

Plain `dict` key assignment is atomic in CPython (GIL), so concurrent writes of the same key are safe in practice. However, two threads may both fetch the same date simultaneously before either has cached it (duplicate network calls). This is acceptable — the result is correct and the duplicate calls are bounded by the number of unique dates, not total transactions. No lock is required.

---

## What Gets Removed

| Symbol | Reason |
|--------|--------|
| `get_rate_from_csv` | CSV no longer used |
| `get_rate_from_bank_of_israel` | BoI API broken for historical dates |
| `_save_rate_to_csv` | No writes to CSV |
| `_fetch_boi_rate` | BoI API broken for historical dates |
| `get_closest_rate_from_dict` | Replaced by inline fallback in `get_historical_rate` |
| `get_current_rate` | Not imported by any script (`process_transactions.py`, `eth_chash_out_exchange.py` verified) |
| `_csv_write_lock` | No CSV writes |
| `scripts/update_exchange_rates.py` | Fully obsolete |

**`ExchangeRateAPIError`** is kept — raised on total failure, imported by callers.

---

## CSV File

`assets/usd_ils_rates.csv` is no longer read or written by the pipeline. It can be kept for reference or deleted.

---

## Weekend / Holiday Handling

`yfinance` returns an empty DataFrame for dates with no market data (weekends, Israeli holidays). The fallback fetches a 7-day window ending on the target date and uses the most recent available Close value.

---

## Dependencies

Add `yfinance` to `requirements.txt`. No API key required.

---

## Impact on All Scripts

| Script | Change |
|--------|--------|
| `process_transactions.py` | Update log message at line 435; no logic change |
| `fetch_exchange_rates.py` | Rewritten |
| `update_exchange_rates.py` | Deleted |
| `eth_chash_out_exchange.py` | No change — imports only `get_historical_rate` and `ExchangeRateAPIError`, both kept |

---

## Error Handling

- Network failure on `yf.download` → raises `ExchangeRateAPIError` with message
- No data found within 7-day fallback window → raises `ExchangeRateAPIError`
- `process_transaction` in `process_transactions.py` already catches these and marks the transaction as failed for retry

---

## Testing

After implementation, verify:

1. `python fetch_exchange_rates.py 2026-03-04` returns a plausible USD/ILS rate (expected ~3.07–3.10 range based on surrounding dates in the CSV)
2. `python fetch_exchange_rates.py 2026-03-07` (Saturday) returns the Friday 06.03 rate
3. Running `process_transactions.py` on a small batch completes without exchange rate errors
