# Background Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Streamlit fee-calculator so the processing pipeline runs in a background thread, continues when the machine sleeps or browser disconnects, supports Stop with partial-results download, shows a live progress panel, and checkpoints after every transaction for auto-resume on restart.

**Architecture:** A module-level singleton in `job_manager.py` owns a `threading.Thread` and a `threading.Event` for stop signalling. `checkpoint.py` writes a JSON state file and a rolling partial-results CSV after each transaction. `app.py` polls `job_manager.get_state()` with `st.rerun()` every second and renders the progress panel; `runner.py` gains `skip_hashes`, `skip_addresses`, and `stop_event` parameters.

**Tech Stack:** Python 3, Streamlit, threading, hashlib, csv, json, pytest

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scripts/checkpoint.py` | Read/write job_state.json and partial_results.csv |
| Create | `scripts/job_manager.py` | Module-level background-thread singleton |
| Modify | `scripts/runner.py` | Add skip sets, stop_event, `result` yield type |
| Modify | `app.py` | Replace blocking loop with polling panel |
| Create | `tests/test_checkpoint.py` | Unit tests for checkpoint module |
| Create | `tests/test_job_manager.py` | Unit tests for job_manager module |
| Modify | `tests/test_runner.py` | Tests for skip and stop behaviour |

---

## Task 1: `checkpoint.py` — disk persistence

**Files:**
- Create: `scripts/checkpoint.py`
- Create: `tests/test_checkpoint.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_checkpoint.py`:

```python
import csv
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@pytest.fixture(autouse=True)
def patch_checkpoint_dir(tmp_path, monkeypatch):
    import checkpoint
    monkeypatch.setattr(checkpoint, 'CHECKPOINT_DIR', str(tmp_path))
    monkeypatch.setattr(checkpoint, 'STATE_FILE', str(tmp_path / 'job_state.json'))
    monkeypatch.setattr(checkpoint, 'RESULTS_FILE', str(tmp_path / 'partial_results.csv'))
    yield


def test_load_returns_none_when_missing():
    import checkpoint
    assert checkpoint.load() is None


def test_save_and_load_roundtrip():
    import checkpoint
    checkpoint.save(
        csv_path='/tmp/test.csv',
        csv_hash='abc123',
        processed_hashes=['0xaaa'],
        processed_addresses=['0xbbb'],
        started_at='2026-04-12T10:00:00',
    )
    state = checkpoint.load()
    assert state['csv_hash'] == 'abc123'
    assert '0xaaa' in state['processed_hashes']
    assert '0xbbb' in state['processed_addresses']
    assert state['status'] == 'running'


def test_append_result_and_load(tmp_path):
    import checkpoint
    fieldnames = ['hash', 'fee_usd', 'error']
    checkpoint.append_result({'hash': '0x1', 'fee_usd': '0.50', 'error': ''}, fieldnames)
    checkpoint.append_result({'hash': '0x2', 'fee_usd': '1.00', 'error': ''}, fieldnames)
    rows = checkpoint.load_partial_results(fieldnames)
    assert len(rows) == 2
    assert rows[0]['hash'] == '0x1'
    assert rows[1]['fee_usd'] == '1.00'


def test_clear_removes_files():
    import checkpoint
    fieldnames = ['hash', 'fee_usd', 'error']
    checkpoint.save('/tmp/x.csv', 'h', [], [], '2026-04-12T10:00:00')
    checkpoint.append_result({'hash': '0x1', 'fee_usd': '1', 'error': ''}, fieldnames)
    checkpoint.clear()
    assert checkpoint.load() is None
    assert checkpoint.load_partial_results(fieldnames) == []


def test_append_result_creates_header_once(tmp_path):
    import checkpoint
    fieldnames = ['hash', 'fee_usd', 'error']
    for i in range(3):
        checkpoint.append_result({'hash': f'0x{i}', 'fee_usd': str(i), 'error': ''}, fieldnames)
    with open(checkpoint.RESULTS_FILE, encoding='utf-8-sig') as f:
        content = f.read()
    # header should appear exactly once
    assert content.count('hash,fee_usd,error') == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /workspaces/sent-trx-fees && python -m pytest tests/test_checkpoint.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'checkpoint'`

- [ ] **Step 3: Create `scripts/checkpoint.py`**

```python
"""
checkpoint.py — Persist job state and partial results to disk.
"""
import csv
import json
import os
from typing import Dict, List, Optional

CHECKPOINT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'checkpoint'
)
STATE_FILE = os.path.join(CHECKPOINT_DIR, 'job_state.json')
RESULTS_FILE = os.path.join(CHECKPOINT_DIR, 'partial_results.csv')


def _ensure_dir() -> None:
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)


def save(
    csv_path: str,
    csv_hash: str,
    processed_hashes: List[str],
    processed_addresses: List[str],
    started_at: str,
) -> None:
    """Write current job progress to disk."""
    _ensure_dir()
    state = {
        'csv_path': csv_path,
        'csv_hash': csv_hash,
        'processed_hashes': list(processed_hashes),
        'processed_addresses': list(processed_addresses),
        'started_at': started_at,
        'status': 'running',
    }
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


def load() -> Optional[Dict]:
    """Return checkpoint dict, or None if no checkpoint exists."""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def append_result(row: Dict, fieldnames: List[str]) -> None:
    """Append one result row to the partial results CSV."""
    _ensure_dir()
    file_exists = os.path.exists(RESULTS_FILE) and os.path.getsize(RESULTS_FILE) > 0
    with open(RESULTS_FILE, 'a', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def load_partial_results(fieldnames: List[str]) -> List[Dict]:
    """Return all rows written so far, or [] if file missing/unreadable."""
    if not os.path.exists(RESULTS_FILE):
        return []
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


def clear() -> None:
    """Delete checkpoint files on clean job completion."""
    for path in (STATE_FILE, RESULTS_FILE):
        try:
            if os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /workspaces/sent-trx-fees && python -m pytest tests/test_checkpoint.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /workspaces/sent-trx-fees && git add scripts/checkpoint.py tests/test_checkpoint.py && git commit -m "feat: add checkpoint module for disk-based job persistence"
```

---

## Task 2: Update `runner.py` — skip sets, stop event, result yields

**Files:**
- Modify: `scripts/runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_runner.py`:

```python
import threading
import io
import csv

def _make_csv(tmp_path, rows):
    """Helper: write a minimal valid CSV and return its path."""
    p = tmp_path / 'input.csv'
    fieldnames = ['txClass', 'status', 'txHash', 'toAddress', 'cryptoCode']
    with open(p, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(p)


def test_run_pipeline_skip_hashes_skips_entry(tmp_path, monkeypatch):
    """When skip_hashes contains a hash, that hash is not processed."""
    import runner

    processed = []

    def fake_process_transaction(tx_hash, *args, **kwargs):
        processed.append(tx_hash)
        return {'hash': tx_hash, 'error': None}

    monkeypatch.setattr(runner, 'process_transaction', fake_process_transaction)
    monkeypatch.setattr(runner, 'normalize_cashin_row', lambda r: r)
    monkeypatch.setattr(runner, 'preload_all_rates', lambda: {})
    monkeypatch.setattr(runner, 'read_and_filter_merchant_csv',
                        lambda p: (['0xAAA', '0xBBB'], []))

    updates = list(runner.run_pipeline(
        'dummy.csv',
        skip_hashes={'0xAAA'},
    ))

    assert '0xAAA' not in processed
    assert '0xBBB' in processed


def test_run_pipeline_stop_event_halts_pipeline(tmp_path, monkeypatch):
    """When stop_event is set, pipeline yields {'type': 'stopped'} and returns."""
    import runner

    stop_event = threading.Event()
    stop_event.set()  # already set before pipeline runs

    monkeypatch.setattr(runner, 'preload_all_rates', lambda: {})
    monkeypatch.setattr(runner, 'read_and_filter_merchant_csv',
                        lambda p: (['0xAAA', '0xBBB', '0xCCC'], []))
    monkeypatch.setattr(runner, 'process_transaction', lambda *a, **k: {'hash': '0x', 'error': None})
    monkeypatch.setattr(runner, 'normalize_cashin_row', lambda r: r)

    updates = list(runner.run_pipeline('dummy.csv', stop_event=stop_event))
    types = [u['type'] for u in updates]
    assert 'stopped' in types
    assert 'done' not in types
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /workspaces/sent-trx-fees && python -m pytest tests/test_runner.py::test_run_pipeline_skip_hashes_skips_entry tests/test_runner.py::test_run_pipeline_stop_event_halts_pipeline -v
```

Expected: both FAIL (`TypeError: run_pipeline() got an unexpected keyword argument 'skip_hashes'`)

- [ ] **Step 3: Update `run_pipeline` signature and add skip/stop logic**

Replace the `run_pipeline` function signature and the cashin/cashout worker functions in `scripts/runner.py`. The full updated function:

```python
def run_pipeline(
    file_path: str,
    max_workers: int = 2,
    etherscan_api_key: str = None,
    skip_hashes: set = None,
    skip_addresses: set = None,
    stop_event=None,
) -> Generator[Dict, None, None]:
    """
    Run the full processing pipeline.

    Yields dicts:
        {'type': 'status', 'message': str}
        {'type': 'progress', 'current': int, 'total': int, 'hash': str}
        {'type': 'result', 'row': dict}
        {'type': 'error', 'hash': str, 'reason': str}
        {'type': 'done', 'rows': List[Dict], 'new': int, 'failed': int, 'skipped': int}
        {'type': 'fatal', 'message': str}
        {'type': 'stopped'}
    """
    if skip_hashes is None:
        skip_hashes = set()
    if skip_addresses is None:
        skip_addresses = set()

    if etherscan_api_key is None:
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
    processed_count = len(skip_hashes) + len(skip_addresses)

    # --- Cashin ---
    def process_one_cashin(item):
        nonlocal processed_count
        i, tx_hash = item

        if tx_hash in skip_hashes:
            return [{'type': 'skipped', 'hash': tx_hash}]

        if stop_event and stop_event.is_set():
            return [{'type': 'stopped'}]

        with cache_lock:
            local_price_cache = dict(price_cache)

        result = process_transaction(tx_hash, etherscan_api_key, rate_cache, local_price_cache)

        with cache_lock:
            price_cache.update(local_price_cache)

        result = normalize_cashin_row(result)

        with rows_lock:
            rows.append(result)

        with counters_lock:
            processed_count += 1
            current_count = processed_count
            if result.get('error'):
                counters['failed'] += 1
                errors.append({'hash': tx_hash, 'reason': result['error']})
            else:
                counters['new'] += 1

        return [
            {'type': 'result', 'row': result},
            {'type': 'progress', 'current': current_count, 'total': total, 'hash': tx_hash},
        ]

    # --- Cashout ETH ---
    def process_one_cashout(item):
        nonlocal processed_count
        idx, address = item
        updates = []

        if address in skip_addresses:
            return [{'type': 'skipped', 'hash': address}]

        if stop_event and stop_event.is_set():
            return [{'type': 'stopped'}]

        if not etherscan_api_key:
            with counters_lock:
                processed_count += 1
                counters['skipped'] += 1
            return updates

        try:
            matching_txs = get_transactions_from_address(address, etherscan_api_key)
            if not matching_txs:
                with counters_lock:
                    processed_count += 1
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
                    updates.append({'type': 'result', 'row': result})
                else:
                    with counters_lock:
                        counters['failed'] += 1
                        errors.append({'hash': tx_hash, 'reason': 'process_transaction_data returned None'})

            with counters_lock:
                processed_count += 1
            updates.append({'type': 'progress', 'current': processed_count, 'total': total, 'hash': address})

        except Exception as e:
            with counters_lock:
                processed_count += 1
                counters['failed'] += 1
                errors.append({'hash': address, 'reason': str(e)})
            updates.append({'type': 'progress', 'current': processed_count, 'total': total, 'hash': address})

        return updates

    yield {'type': 'status', 'message': f'Processing {len(cashin_hashes)} cashin transactions...'}

    stopped = False
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one_cashin, item): item
                   for item in enumerate(cashin_hashes, 1)}
        for future in as_completed(futures):
            for update in future.result():
                if update.get('type') == 'stopped':
                    stopped = True
                    break
                yield update
            if stopped:
                break

    if stopped:
        yield {'type': 'stopped'}
        return

    if cashout_addresses:
        yield {'type': 'status', 'message': f'Processing {len(cashout_addresses)} cashout ETH addresses...'}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_one_cashout, item): item
                       for item in enumerate(cashout_addresses, 1)}
            for future in as_completed(futures):
                for update in future.result():
                    if update.get('type') == 'stopped':
                        stopped = True
                        break
                    yield update
                if stopped:
                    break

    if stopped:
        yield {'type': 'stopped'}
        return

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

- [ ] **Step 4: Run the new tests plus existing ones**

```bash
cd /workspaces/sent-trx-fees && python -m pytest tests/test_runner.py -v
```

Expected: all 5 tests PASS (3 existing + 2 new)

- [ ] **Step 5: Commit**

```bash
cd /workspaces/sent-trx-fees && git add scripts/runner.py tests/test_runner.py && git commit -m "feat: add skip_hashes, skip_addresses, stop_event to run_pipeline"
```

---

## Task 3: `job_manager.py` — background thread singleton

**Files:**
- Create: `scripts/job_manager.py`
- Create: `tests/test_job_manager.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_job_manager.py`:

```python
import os
import sys
import threading
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


@pytest.fixture(autouse=True)
def reset_job(monkeypatch, tmp_path):
    """Reset global job state and redirect checkpoint dir before each test."""
    import job_manager
    import checkpoint

    monkeypatch.setattr(checkpoint, 'CHECKPOINT_DIR', str(tmp_path))
    monkeypatch.setattr(checkpoint, 'STATE_FILE', str(tmp_path / 'job_state.json'))
    monkeypatch.setattr(checkpoint, 'RESULTS_FILE', str(tmp_path / 'partial_results.csv'))

    job_manager._reset_for_testing()
    yield
    job_manager._reset_for_testing()


def _fake_pipeline_slow(stop_event):
    """A fake run_pipeline that sleeps and checks stop_event."""
    import runner as _runner

    def fake(*args, skip_hashes=None, skip_addresses=None, stop_event=None, **kwargs):
        yield {'type': 'status', 'message': 'starting'}
        for i in range(10):
            if stop_event and stop_event.is_set():
                yield {'type': 'stopped'}
                return
            time.sleep(0.05)
            yield {'type': 'progress', 'current': i + 1, 'total': 10, 'hash': f'0x{i:040x}'}
            yield {'type': 'result', 'row': {'hash': f'0x{i:040x}', 'fee_usd': '1.0', 'error': ''}}
        yield {'type': 'done', 'rows': [], 'new': 10, 'failed': 0, 'skipped': 0}

    return fake


def test_get_state_initial():
    import job_manager
    state = job_manager.get_state()
    assert state['status'] == 'idle'


def test_start_transitions_to_running(monkeypatch, tmp_path):
    import job_manager
    import runner

    csv_bytes = b'txClass,status,txHash,toAddress,cryptoCode\n'
    monkeypatch.setattr(runner, 'run_pipeline', _fake_pipeline_slow(None))

    job_manager.start(csv_bytes, etherscan_key=None)
    time.sleep(0.05)
    state = job_manager.get_state()
    assert state['status'] == 'running'


def test_stop_transitions_to_stopped(monkeypatch, tmp_path):
    import job_manager
    import runner

    csv_bytes = b'txClass,status,txHash,toAddress,cryptoCode\n'
    stop_holder = [None]

    def fake_pipeline(*args, skip_hashes=None, skip_addresses=None, stop_event=None, **kwargs):
        stop_holder[0] = stop_event
        yield {'type': 'status', 'message': 'starting'}
        for i in range(20):
            if stop_event and stop_event.is_set():
                yield {'type': 'stopped'}
                return
            time.sleep(0.02)
            yield {'type': 'progress', 'current': i + 1, 'total': 20, 'hash': f'0x{i}'}
            yield {'type': 'result', 'row': {'hash': f'0x{i}', 'fee_usd': '1', 'error': ''}}
        yield {'type': 'done', 'rows': [], 'new': 20, 'failed': 0, 'skipped': 0}

    monkeypatch.setattr(runner, 'run_pipeline', fake_pipeline)

    job_manager.start(csv_bytes, etherscan_key=None)
    time.sleep(0.1)
    job_manager.stop()
    time.sleep(0.2)

    state = job_manager.get_state()
    assert state['status'] == 'stopped'


def test_auto_resume_returns_false_when_no_checkpoint():
    import job_manager
    assert job_manager.auto_resume_if_checkpoint() is False


def test_auto_resume_starts_thread_when_checkpoint_exists(monkeypatch, tmp_path):
    import job_manager
    import runner
    import checkpoint

    # Write a fake checkpoint pointing to a real temp CSV
    csv_path = str(tmp_path / 'test.csv')
    with open(csv_path, 'w') as f:
        f.write('txClass,status,txHash,toAddress,cryptoCode\n')

    checkpoint.save(csv_path, 'fakehash', ['0xDONE'], [], '2026-04-12T10:00:00')

    def fake_pipeline(*args, skip_hashes=None, skip_addresses=None, stop_event=None, **kwargs):
        yield {'type': 'status', 'message': 'resuming'}
        yield {'type': 'done', 'rows': [], 'new': 0, 'failed': 0, 'skipped': 0}

    monkeypatch.setattr(runner, 'run_pipeline', fake_pipeline)

    result = job_manager.auto_resume_if_checkpoint()
    assert result is True
    time.sleep(0.1)
    state = job_manager.get_state()
    assert state['status'] in ('running', 'done')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /workspaces/sent-trx-fees && python -m pytest tests/test_job_manager.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'job_manager'`

- [ ] **Step 3: Create `scripts/job_manager.py`**

```python
"""
job_manager.py — Module-level background-thread singleton for the processing pipeline.

Public API:
    start(csv_bytes, etherscan_key)      — start pipeline in background thread
    stop()                               — signal stop; thread finishes current tx
    get_state()                          — thread-safe snapshot for the UI
    auto_resume_if_checkpoint()          — called at app startup; resumes if checkpoint found
"""

import hashlib
import os
import sys
import tempfile
import threading
from datetime import datetime
from typing import List, Optional

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import checkpoint as _checkpoint
import runner as _runner
from process_merchant_csv import OUTPUT_COLUMNS

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_lock = threading.Lock()

_job = {
    'status': 'idle',       # idle | running | stopped | done | error
    'thread': None,
    'stop_event': None,
    'progress': {'current': 0, 'total': 0},
    'rows': [],
    'errors': [],
    'counters': {'new': 0, 'failed': 0, 'skipped': 0},
    'log': [],
    'started_at': None,
    'csv_hash': None,
    'tmp_csv_path': None,
    'last_hash': '',
}


def _reset_for_testing() -> None:
    """Reset singleton to idle state. Only for use in tests."""
    with _lock:
        _job.update({
            'status': 'idle',
            'thread': None,
            'stop_event': None,
            'progress': {'current': 0, 'total': 0},
            'rows': [],
            'errors': [],
            'counters': {'new': 0, 'failed': 0, 'skipped': 0},
            'log': [],
            'started_at': None,
            'csv_hash': None,
            'tmp_csv_path': None,
            'last_hash': '',
        })


def _log(msg: str) -> None:
    _job['log'].append(msg)
    if len(_job['log']) > 20:
        _job['log'] = _job['log'][-20:]


def _csv_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Background thread worker
# ---------------------------------------------------------------------------

def _run_thread(
    csv_path: str,
    etherscan_key: Optional[str],
    skip_hashes: set,
    skip_addresses: set,
) -> None:
    with _lock:
        stop_event = _job['stop_event']
        started_at_iso = _job['started_at'].isoformat()
        csv_hash = _job['csv_hash']

    processed_hashes = set(skip_hashes)
    processed_addresses = set(skip_addresses)

    try:
        for update in _runner.run_pipeline(
            csv_path,
            etherscan_api_key=etherscan_key,
            skip_hashes=skip_hashes,
            skip_addresses=skip_addresses,
            stop_event=stop_event,
        ):
            utype = update.get('type')

            if utype == 'status':
                with _lock:
                    _log(update['message'])

            elif utype == 'progress':
                h = update['hash']
                if len(h) == 66:
                    processed_hashes.add(h)
                else:
                    processed_addresses.add(h)
                with _lock:
                    _job['progress']['current'] = update['current']
                    _job['progress']['total'] = update['total']
                    _job['last_hash'] = h
                _checkpoint.save(
                    csv_path,
                    csv_hash,
                    list(processed_hashes),
                    list(processed_addresses),
                    started_at_iso,
                )

            elif utype == 'result':
                row = update['row']
                with _lock:
                    _job['rows'].append(row)
                _checkpoint.append_result(row, OUTPUT_COLUMNS)

            elif utype == 'error':
                with _lock:
                    _job['errors'].append(update)

            elif utype == 'stopped':
                with _lock:
                    _job['status'] = 'stopped'
                    _log('Run stopped.')
                return

            elif utype == 'fatal':
                with _lock:
                    _job['status'] = 'error'
                    _log(f"Fatal error: {update['message']}")
                return

            elif utype == 'done':
                with _lock:
                    c = update
                    _job['counters'] = {
                        'new': c['new'],
                        'failed': c['failed'],
                        'skipped': c['skipped'],
                    }
                    _job['status'] = 'done'
                    _log(f"Done — {c['new']} succeeded, {c['failed']} failed, {c['skipped']} skipped.")
                _checkpoint.clear()
                return

    except Exception as e:
        with _lock:
            _job['status'] = 'error'
            _log(f'Unexpected error: {e}')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_state() -> dict:
    """Return a thread-safe snapshot of the current job state."""
    with _lock:
        return {
            'status': _job['status'],
            'progress': dict(_job['progress']),
            'rows': list(_job['rows']),
            'errors': list(_job['errors']),
            'counters': dict(_job['counters']),
            'log': list(_job['log']),
            'started_at': _job['started_at'],
            'last_hash': _job['last_hash'],
        }


def start(csv_bytes: bytes, etherscan_key: Optional[str] = None) -> None:
    """
    Start the pipeline in a background thread.

    If a checkpoint for the same CSV exists, resumes from that checkpoint.
    If a checkpoint for a different CSV exists, clears it and starts fresh.
    Raises RuntimeError if a job is already running.
    """
    with _lock:
        if _job['status'] == 'running':
            raise RuntimeError('A job is already running.')

    h = _csv_hash(csv_bytes)
    existing = _checkpoint.load()

    skip_hashes: set = set()
    skip_addresses: set = set()
    prior_rows: List[dict] = []

    if existing:
        if existing.get('csv_hash') == h:
            skip_hashes = set(existing.get('processed_hashes', []))
            skip_addresses = set(existing.get('processed_addresses', []))
            prior_rows = _checkpoint.load_partial_results(OUTPUT_COLUMNS)
            csv_path = existing.get('csv_path', '')
            if csv_path and os.path.exists(csv_path):
                # reuse existing temp file
                pass
            else:
                # temp CSV gone, write new one
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='wb')
                tmp.write(csv_bytes)
                tmp.close()
                csv_path = tmp.name
        else:
            # Different CSV — clear old checkpoint
            _checkpoint.clear()
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='wb')
            tmp.write(csv_bytes)
            tmp.close()
            csv_path = tmp.name
    else:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='wb')
        tmp.write(csv_bytes)
        tmp.close()
        csv_path = tmp.name

    stop_event = threading.Event()

    with _lock:
        _job.update({
            'status': 'running',
            'stop_event': stop_event,
            'progress': {
                'current': len(skip_hashes) + len(skip_addresses),
                'total': 0,
            },
            'rows': prior_rows,
            'errors': [],
            'counters': {'new': 0, 'failed': 0, 'skipped': 0},
            'log': ['Resuming from checkpoint...' if skip_hashes or skip_addresses else 'Starting...'],
            'started_at': datetime.now(),
            'csv_hash': h,
            'tmp_csv_path': csv_path,
            'last_hash': '',
        })

    t = threading.Thread(
        target=_run_thread,
        args=(csv_path, etherscan_key, skip_hashes, skip_addresses),
        daemon=True,
        name='pipeline-worker',
    )
    with _lock:
        _job['thread'] = t
    t.start()


def stop() -> None:
    """Signal the running pipeline to stop after the current transaction."""
    with _lock:
        se = _job.get('stop_event')
    if se:
        se.set()


def auto_resume_if_checkpoint() -> bool:
    """
    Called at app startup. If a valid checkpoint exists and the temp CSV is
    still on disk, starts a resume thread automatically. Returns True if resumed.
    """
    with _lock:
        if _job['status'] == 'running':
            return False

    existing = _checkpoint.load()
    if not existing or existing.get('status') != 'running':
        return False

    csv_path = existing.get('csv_path', '')
    if not csv_path or not os.path.exists(csv_path):
        return False  # can't resume without the CSV

    skip_hashes = set(existing.get('processed_hashes', []))
    skip_addresses = set(existing.get('processed_addresses', []))
    prior_rows = _checkpoint.load_partial_results(OUTPUT_COLUMNS)
    etherscan_key = os.getenv('ETHERSCAN_API_KEY')

    try:
        started_at = datetime.fromisoformat(existing.get('started_at', ''))
    except ValueError:
        started_at = datetime.now()

    stop_event = threading.Event()

    with _lock:
        _job.update({
            'status': 'running',
            'stop_event': stop_event,
            'progress': {
                'current': len(skip_hashes) + len(skip_addresses),
                'total': 0,
            },
            'rows': prior_rows,
            'errors': [],
            'counters': {'new': 0, 'failed': 0, 'skipped': 0},
            'log': ['Auto-resuming from checkpoint...'],
            'started_at': started_at,
            'csv_hash': existing.get('csv_hash'),
            'tmp_csv_path': csv_path,
            'last_hash': '',
        })

    t = threading.Thread(
        target=_run_thread,
        args=(csv_path, etherscan_key, skip_hashes, skip_addresses),
        daemon=True,
        name='pipeline-worker',
    )
    with _lock:
        _job['thread'] = t
    t.start()
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /workspaces/sent-trx-fees && python -m pytest tests/test_job_manager.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Run full test suite to check nothing is broken**

```bash
cd /workspaces/sent-trx-fees && python -m pytest tests/ -v --ignore=tests/test_etherscan_api.py --ignore=tests/test_fetch_exchange_rates.py
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
cd /workspaces/sent-trx-fees && git add scripts/job_manager.py tests/test_job_manager.py && git commit -m "feat: add job_manager background-thread singleton with stop and auto-resume"
```

---

## Task 4: Update `app.py` — polling progress panel

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Replace `app.py` with the updated version**

Replace the entire contents of `app.py`:

```python
"""
app.py — Bitcoin Change Fee Calculator (Streamlit UI)
"""

import io
import csv
import sys
import os
import time
from datetime import datetime, timedelta

import streamlit as st

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from runner import validate_csv_columns, MissingColumnsError
from process_merchant_csv import OUTPUT_COLUMNS
import job_manager

# ---- Auto-resume on startup (once per process) ----
job_manager.auto_resume_if_checkpoint()

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


def _format_duration(seconds: float) -> str:
    td = timedelta(seconds=int(max(seconds, 0)))
    h, rem = divmod(td.seconds, 3600)
    m, s = divmod(rem, 60)
    if td.days or h:
        return f"{td.days * 24 + h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _render_job_panel(state: dict) -> None:
    """Render the live progress panel for a running/stopped/done/error job."""
    status = state['status']
    progress = state['progress']
    counters = state['counters']
    log = state['log']
    started_at = state['started_at']

    current = progress.get('current', 0)
    total = progress.get('total', 0)
    pct = current / max(total, 1)

    # ---- Header row ----
    col_status, col_stop = st.columns([3, 1])
    with col_status:
        if status == 'running':
            st.markdown("**● Running...**")
        elif status == 'stopped':
            st.warning("Stopped — partial results available below.")
        elif status == 'done':
            c = counters
            if c['failed'] == 0 and c['skipped'] == 0:
                st.success(f"Done — {c['new']} transactions processed successfully.")
            elif c['failed'] == 0:
                st.warning(f"Done — {c['new']} processed, {c['skipped']} skipped.")
            else:
                st.warning(f"Done — {c['new']} succeeded, {c['failed']} failed, {c['skipped']} skipped.")
        elif status == 'error':
            st.error(f"Error: {log[-1] if log else 'Unknown error'}")

    with col_stop:
        if status == 'running':
            if st.button("■ Stop", type="secondary"):
                job_manager.stop()
                st.rerun()

    # ---- Progress bar ----
    label = f"{int(pct * 100)}%  ({current}/{total})" if total > 0 else "Starting..."
    st.progress(pct, text=label)

    # ---- Timing ----
    if started_at:
        elapsed = (datetime.now() - started_at).total_seconds()
        elapsed_str = _format_duration(elapsed)
        if current >= 5 and total > current:
            eta_seconds = elapsed / current * (total - current)
            eta_str = _format_duration(eta_seconds)
            st.caption(f"Elapsed: {elapsed_str}   •   Est. remaining: ~{eta_str}")
        else:
            st.caption(f"Elapsed: {elapsed_str}")

    # ---- Last processed hash ----
    if state.get('last_hash') and status == 'running':
        last = state['last_hash']
        display = last[:20] + '...' if len(last) > 20 else last
        st.caption(f"Last processed: {display}")

    # ---- Counters ----
    c = counters
    st.caption(f"✓ {c['new']} succeeded   ✗ {c['failed']} failed   ↷ {c['skipped']} skipped")

    # ---- Log ----
    if log:
        with st.expander("Status log", expanded=False):
            for msg in log[-5:]:
                st.info(msg)

    # ---- Errors table ----
    errors = state.get('errors', [])
    if errors:
        st.markdown("**Transactions with errors:**")
        st.table([{"Hash / Address": e['hash'], "Reason": e['reason']} for e in errors])

    # ---- Download ----
    rows = state.get('rows', [])
    if rows and status in ('done', 'stopped'):
        st.markdown("---")
        st.subheader("Download Results")
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
        st.download_button(
            label="Download Results" if status == 'done' else "Download Partial Results",
            data=output.getvalue().encode('utf-8-sig'),
            file_name="fee_results.csv",
            mime="text/csv",
            type="primary",
        )


# ---- Check if job is active ----
state = job_manager.get_state()

if state['status'] != 'idle':
    _render_job_panel(state)
    if state['status'] == 'running':
        time.sleep(1)
        st.rerun()
    st.stop()

# ---- Step 1: Upload (only shown when idle) ----
st.subheader("Step 1 — Upload CSV")
uploaded_file = st.file_uploader("Upload the ATM transactions CSV", type=["csv"])

if uploaded_file is not None:
    file_bytes = uploaded_file.read()

    # Validate columns
    import tempfile
    val_tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='wb') as val_tmp:
            val_tmp.write(file_bytes)
            val_tmp_path = val_tmp.name
        validate_csv_columns(val_tmp_path)
    except MissingColumnsError as e:
        st.error(f"Invalid file: {e}")
        st.stop()
    finally:
        if val_tmp_path:
            try:
                os.unlink(val_tmp_path)
            except Exception:
                pass

    st.success("File looks good. Ready to process.")

    # ---- Step 2: Run ----
    st.markdown("---")
    st.subheader("Step 2 — Calculate Fees")

    try:
        etherscan_key = st.secrets.get("ETHERSCAN_API_KEY")
    except Exception:
        etherscan_key = None
    etherscan_key = etherscan_key or os.getenv("ETHERSCAN_API_KEY")

    if st.button("Calculate Fees", type="primary"):
        job_manager.start(file_bytes, etherscan_key=etherscan_key)
        st.rerun()
```

- [ ] **Step 2: Verify the app starts without errors**

```bash
cd /workspaces/sent-trx-fees && python -c "import ast, sys; ast.parse(open('app.py').read()); print('syntax OK')"
```

Expected: `syntax OK`

- [ ] **Step 3: Verify the checkpoint directory is created**

```bash
cd /workspaces/sent-trx-fees && python -c "
import sys; sys.path.insert(0, 'scripts')
import checkpoint
checkpoint.save('/tmp/x.csv', 'abc', [], [], '2026-04-12T10:00:00')
import os; print('checkpoint dir exists:', os.path.exists('checkpoint'))
import json; print(json.load(open('checkpoint/job_state.json')))
"
```

Expected: prints `checkpoint dir exists: True` and the JSON state

- [ ] **Step 4: Run full test suite**

```bash
cd /workspaces/sent-trx-fees && python -m pytest tests/ -v --ignore=tests/test_etherscan_api.py --ignore=tests/test_fetch_exchange_rates.py
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
cd /workspaces/sent-trx-fees && git add app.py && git commit -m "feat: replace blocking pipeline call with background-thread polling UI and stop button"
```

---

## Task 5: Add `checkpoint/` to `.gitignore`

**Files:**
- Modify: `.gitignore` (create if missing)

- [ ] **Step 1: Add checkpoint directory to .gitignore**

```bash
cd /workspaces/sent-trx-fees && echo 'checkpoint/' >> .gitignore && git add .gitignore && git commit -m "chore: ignore checkpoint/ directory"
```

Expected: no errors

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| Continues running when machine sleeps | daemon Thread in job_manager (OS resumes thread on wake) |
| Continues running when browser disconnects | Thread lives in Streamlit process, independent of sessions |
| Stop button | Task 4 UI — `■ Stop` button calls `job_manager.stop()` |
| Download partial results after stop | Task 4 — Download button shown when `status == 'stopped'` |
| Progress bar with % | Task 4 — `st.progress(pct, text=label)` with current/total |
| Elapsed time | Task 4 — `_format_duration(elapsed)` |
| ETA | Task 4 — shown after ≥5 transactions |
| Counters (succeeded/failed/skipped) | Task 4 — `_render_job_panel` caption row |
| Checkpoint after every transaction | Task 3 — `_run_thread` saves checkpoint on every `progress` event |
| Auto-resume on restart | Task 3 — `auto_resume_if_checkpoint()` in task 3; called at app startup in task 4 |
| CSV identity check (SHA-256) | Task 3 — `start()` compares `_csv_hash(csv_bytes)` with checkpoint |
| Temp CSV missing → warning | Task 3 — `auto_resume_if_checkpoint` returns False; task 4 shows upload UI |
| Clean finish deletes checkpoint | Task 3 — `_checkpoint.clear()` on `done` event |

All requirements covered. No gaps.
