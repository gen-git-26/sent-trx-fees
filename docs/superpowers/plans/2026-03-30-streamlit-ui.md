# Streamlit UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing `process_merchant_csv.py` logic in a local Streamlit web app that a non-technical Windows user can run by double-clicking `run.bat`.

**Architecture:** A single `app.py` at the repo root imports and calls the same functions used by `process_merchant_csv.py`. A helper module `scripts/runner.py` extracts the processing logic from `main()` into a callable function that accepts a file path and yields progress updates. The Streamlit app streams progress to the UI, then offers a download button on completion.

**Tech Stack:** Python 3.12, Streamlit, existing scripts (unchanged), `.streamlit/config.toml` for branding.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/runner.py` | **Create** | Callable processing logic extracted from `process_merchant_csv.py` — returns a generator of progress updates |
| `app.py` | **Create** | Streamlit UI: upload → run → download |
| `.streamlit/config.toml` | **Create** | Bitcoin Change color theme |
| `requirements.txt` | **Modify** | Add `streamlit>=1.32.0` |
| `run.bat` | **Create** | Windows double-click launcher |

`scripts/process_merchant_csv.py` and all other `scripts/` files are **not modified**.

---

## Task 1: Add streamlit to requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add streamlit dependency**

Edit `requirements.txt` to add at the end:
```
streamlit>=1.32.0
```

- [ ] **Step 2: Install it**

```bash
pip install streamlit>=1.32.0
```

Expected: installs without error, `streamlit --version` prints a version.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add streamlit dependency"
```

---

## Task 2: Streamlit theme (.streamlit/config.toml)

**Files:**
- Create: `.streamlit/config.toml`

- [ ] **Step 1: Create the config directory and file**

Create `.streamlit/config.toml` with this exact content:

```toml
[theme]
base = "dark"
primaryColor = "#f7a51e"
backgroundColor = "#0d0d0d"
secondaryBackgroundColor = "#1a1a1a"
textColor = "#ffffff"
```

- [ ] **Step 2: Verify it parses correctly**

```bash
python -c "import tomllib; tomllib.load(open('.streamlit/config.toml','rb'))"
```

Expected: no output (no error).

- [ ] **Step 3: Commit**

```bash
git add .streamlit/config.toml
git commit -m "feat: add Bitcoin Change Streamlit theme"
```

---

## Task 3: Extract runner function (scripts/runner.py)

**Files:**
- Create: `scripts/runner.py`

This module takes a CSV file path and runs the full processing pipeline, yielding progress dicts so the UI can stream updates. It does **not** write to a temp file — it collects all rows in memory and returns them as a list.

- [ ] **Step 1: Write a test for the runner's CSV validation**

Create `tests/test_runner.py`:

```python
import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from runner import validate_csv_columns, MissingColumnsError

def test_validate_csv_columns_passes_with_all_required(tmp_path):
    f = tmp_path / "ok.csv"
    f.write_text("txClass,status,txHash,toAddress,cryptoCode\n")
    validate_csv_columns(str(f))  # should not raise

def test_validate_csv_columns_raises_on_missing(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("txClass,status\n")
    with pytest.raises(MissingColumnsError) as exc_info:
        validate_csv_columns(str(f))
    assert "txHash" in str(exc_info.value)
    assert "toAddress" in str(exc_info.value)
    assert "cryptoCode" in str(exc_info.value)

def test_validate_csv_columns_raises_on_empty_file(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("")
    with pytest.raises(MissingColumnsError):
        validate_csv_columns(str(f))
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/test_runner.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `runner.py` doesn't exist yet.

- [ ] **Step 3: Create scripts/runner.py**

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_runner.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/runner.py tests/test_runner.py
git commit -m "feat: extract pipeline into callable runner with progress yields"
```

---

## Task 4: Build app.py (Streamlit UI)

**Files:**
- Create: `app.py`

- [ ] **Step 1: Create app.py**

```python
"""
app.py — Bitcoin Change Fee Calculator (Streamlit UI)
"""

import io
import csv
import sys
import os
import tempfile

import streamlit as st

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from runner import validate_csv_columns, run_pipeline, MissingColumnsError

# ---- Page config ----
st.set_page_config(
    page_title="Bitcoin Change — Fee Calculator",
    page_icon="logo_bit.jpg",
    layout="centered",
)

# ---- Logo ----
st.image("logo_bit.jpg", width=280)
st.title("Blockchain Fee Calculator")
st.markdown("---")

# ---- Step 1: Upload ----
st.subheader("Step 1 — Upload CSV")
uploaded_file = st.file_uploader("Upload the ATM transactions CSV", type=["csv"])

if uploaded_file is not None:
    # Save to a temp file so existing scripts can read it from disk
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='wb') as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    # Validate columns immediately
    try:
        validate_csv_columns(tmp_path)
        st.success("File looks good. Ready to process.")
    except MissingColumnsError as e:
        st.error(f"Invalid file: {e}")
        os.unlink(tmp_path)
        st.stop()

    # ---- Step 2: Run ----
    st.markdown("---")
    st.subheader("Step 2 — Calculate Fees")

    if st.button("Calculate Fees", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        rows = []
        errors = []
        fatal = False
        summary = {}

        try:
            for update in run_pipeline(tmp_path):
                utype = update.get('type')

                if utype == 'status':
                    status_text.info(update['message'])

                elif utype == 'progress':
                    pct = update['current'] / max(update['total'], 1)
                    progress_bar.progress(pct)
                    status_text.info(f"[{update['current']}/{update['total']}] Processing: {update['hash'][:20]}...")

                elif utype == 'error':
                    errors.append(update)

                elif utype == 'fatal':
                    st.error(f"Process did not complete successfully: {update['message']}")
                    fatal = True
                    break

                elif utype == 'done':
                    rows = update['rows']
                    summary = update
                    progress_bar.progress(1.0)

        except Exception as e:
            st.error(f"Process did not complete successfully: {e}")
            fatal = True

        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        if not fatal:
            total = summary.get('new', 0) + summary.get('failed', 0)
            failed = summary.get('failed', 0)

            if failed == 0:
                st.success(f"Done — {summary.get('new', 0)} transactions processed successfully.")
            else:
                st.warning(
                    f"Done — {summary.get('new', 0)} succeeded, {failed} failed out of {total} total."
                )

            # Show error table if any
            if errors:
                st.markdown("**Transactions with errors:**")
                st.table([{"Hash / Address": e['hash'], "Reason": e['reason']} for e in errors])

            # ---- Step 3: Download ----
            if rows:
                st.markdown("---")
                st.subheader("Step 3 — Download Results")

                output = io.StringIO()
                from process_merchant_csv import OUTPUT_COLUMNS
                writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)

                st.download_button(
                    label="Download Results",
                    data=output.getvalue().encode('utf-8-sig'),
                    file_name="fee_results.csv",
                    mime="text/csv",
                    type="primary",
                )
```

- [ ] **Step 2: Smoke-test the app locally**

```bash
streamlit run app.py
```

Expected: browser opens at `http://localhost:8501`, shows the Bitcoin Change logo and "Blockchain Fee Calculator" title with black background and gold accents. No Python errors in terminal.

Verify manually:
- Logo displays
- File uploader appears
- Uploading a file with wrong columns shows a red error message
- App does not crash

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add Streamlit UI app.py"
```

---

## Task 5: Windows launcher (run.bat)

**Files:**
- Create: `run.bat`

- [ ] **Step 1: Create run.bat**

```bat
@echo off
cd /d "%~dp0"
streamlit run app.py
pause
```

`%~dp0` ensures the script always runs from its own directory regardless of where the user double-clicks it from. `pause` keeps the terminal open on error so the user can read the message.

- [ ] **Step 2: Verify it works on Windows**

Double-click `run.bat`. Expected: a terminal window opens, Streamlit starts, and the browser opens automatically at `http://localhost:8501`.

- [ ] **Step 3: Commit**

```bash
git add run.bat
git commit -m "feat: add Windows run.bat launcher"
```

---

## Task 6: End-to-end smoke test

- [ ] **Step 1: Run all unit tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Manual end-to-end test**

1. Run `streamlit run app.py`
2. Upload a valid test CSV (e.g. `test-fee.csv` if present in the repo)
3. Click "Calculate Fees"
4. Verify progress bar moves, status text updates
5. Verify summary banner appears at the end
6. Click "Download Results" — confirm a CSV downloads

- [ ] **Step 3: Test error paths**

1. Upload a CSV missing required columns → confirm red error, no run button active
2. Upload a non-CSV file → Streamlit's uploader blocks it (type=["csv"])

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete Streamlit UI with branding, runner, and Windows launcher"
```
