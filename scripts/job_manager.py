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
            prior_rows = _checkpoint.load_partial_results()
            csv_path = existing.get('csv_path', '')
            if not (csv_path and os.path.exists(csv_path)):
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
    if se is not None:
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
    prior_rows = _checkpoint.load_partial_results()
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
