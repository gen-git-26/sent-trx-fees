"""
job_manager.py — Module-level background-thread singleton for the processing pipeline.

Public API:
    start(csv_bytes, etherscan_key)      — start pipeline in background thread
    retry_failed(etherscan_key)          — retry the failed source rows from the last job
    stop()                               — signal stop; thread finishes current tx
    get_state()                          — thread-safe snapshot for the UI
    get_failed_report()                  — failed source rows using original CSV columns
    auto_resume_if_checkpoint()          — called at app startup; resumes if checkpoint found
"""

import csv
import hashlib
import io
import os
import sys
import tempfile
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

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
    'status': 'idle',       # idle | starting | running | stopped | done | error
    'thread': None,
    'stop_event': None,
    'progress': {'current': 0, 'total': 0},
    'rows': [],             # successful output rows only
    'errors': [],
    'failed_input_rows': [], # original CSV rows for failed transactions
    'counters': {'new': 0, 'failed': 0, 'skipped': 0},
    'log': [],
    'started_at': None,
    'csv_hash': None,
    'tmp_csv_path': None,
    'last_hash': '',
    'original_fieldnames': [],
    'original_rows': [],
}


def _reset_for_testing() -> None:
    """Reset singleton to idle state. Only for use in tests."""
    with _lock:
        se = _job.get('stop_event')
        t = _job.get('thread')
    if se is not None:
        se.set()
    if t is not None and t.is_alive():
        t.join(timeout=2.0)
    with _lock:
        _job.update({
            'status': 'idle',
            'thread': None,
            'stop_event': None,
            'progress': {'current': 0, 'total': 0},
            'rows': [],
            'errors': [],
            'failed_input_rows': [],
            'counters': {'new': 0, 'failed': 0, 'skipped': 0},
            'log': [],
            'started_at': None,
            'csv_hash': None,
            'tmp_csv_path': None,
            'last_hash': '',
            'original_fieldnames': [],
            'original_rows': [],
        })


def _log(msg: str) -> None:
    # Caller must hold _lock before calling this function.
    _job['log'].append(msg)
    if len(_job['log']) > 20:
        _job['log'] = _job['log'][-20:]


def _csv_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_source_rows(csv_path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read original CSV headers and rows so failed inputs can be downloaded/retried."""
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def _rows_to_csv_bytes(fieldnames: List[str], rows: List[Dict[str, str]]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')


def _dedupe_rows(rows: List[Dict[str, str]], fieldnames: List[str]) -> List[Dict[str, str]]:
    seen = set()
    deduped = []
    for row in rows:
        key = tuple(row.get(col, '') for col in fieldnames)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _matching_source_rows(identifier: str, input_id: Optional[str] = None) -> List[Dict[str, str]]:
    """Find original CSV rows that produced a failed hash/address."""
    needles = {v.strip().lower() for v in (identifier, input_id or '') if v and v.strip()}
    if not needles:
        return []

    matches = []
    for row in _job.get('original_rows', []):
        tx_hash = row.get('txHash', '').strip().lower()
        to_address = row.get('toAddress', '').strip().lower()
        if tx_hash in needles or to_address in needles:
            matches.append(row)
    return matches


def _cleanup_tmp_csv(csv_path: str) -> None:
    """Delete temp CSV if it was created by job_manager (not user-provided)."""
    try:
        if csv_path and csv_path.startswith(tempfile.gettempdir()) and os.path.exists(csv_path):
            os.unlink(csv_path)
    except OSError:
        pass


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
                if row.get('error'):
                    continue
                with _lock:
                    existing_hashes = {r.get('hash') for r in _job['rows'] if r.get('hash')}
                    if row.get('hash') not in existing_hashes:
                        _job['rows'].append(row)
                        _checkpoint.append_result(row, OUTPUT_COLUMNS)

            elif utype == 'error':
                with _lock:
                    _job['errors'].append(update)
                    failed_rows = _matching_source_rows(
                        update.get('hash', ''),
                        update.get('input_id'),
                    )
                    _job['failed_input_rows'] = _dedupe_rows(
                        _job['failed_input_rows'] + failed_rows,
                        _job['original_fieldnames'],
                    )

            elif utype == 'stopped':
                with _lock:
                    _job['status'] = 'stopped'
                    _log('Run stopped.')
                _cleanup_tmp_csv(csv_path)
                return

            elif utype == 'fatal':
                with _lock:
                    _job['status'] = 'error'
                    _log(f"Fatal error: {update['message']}")
                _cleanup_tmp_csv(csv_path)
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
                _cleanup_tmp_csv(csv_path)
                return

    except Exception as e:
        with _lock:
            _job['status'] = 'error'
            _log(f'Unexpected error: {e}')
        _cleanup_tmp_csv(csv_path)


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
            'failed_input_rows': list(_job['failed_input_rows']),
            'failed_report_available': bool(_job['failed_input_rows']),
            'successful_results_available': bool(_job['rows']),
            'counters': dict(_job['counters']),
            'log': list(_job['log']),
            'started_at': _job['started_at'],
            'last_hash': _job['last_hash'],
        }


def _start_job(
    csv_bytes: bytes,
    etherscan_key: Optional[str] = None,
    initial_rows: Optional[List[dict]] = None,
    retrying_failed: bool = False,
) -> None:
    with _lock:
        if _job['status'] in ('running', 'starting'):
            raise RuntimeError('A job is already running.')
        _job['status'] = 'starting'   # claim slot before releasing lock

    try:
        h = _csv_hash(csv_bytes)
        existing = _checkpoint.load()

        skip_hashes: set = set()
        skip_addresses: set = set()
        prior_rows: List[dict] = list(initial_rows or [])

        if existing and not retrying_failed:
            if existing.get('csv_hash') == h:
                skip_hashes = set(existing.get('processed_hashes', []))
                skip_addresses = set(existing.get('processed_addresses', []))
                prior_rows = _checkpoint.load_partial_results()
                csv_path = existing.get('csv_path', '')
                if not (csv_path and os.path.exists(csv_path)):
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='wb')
                    tmp.write(csv_bytes)
                    tmp.close()
                    csv_path = tmp.name
            else:
                _checkpoint.clear()
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='wb')
                tmp.write(csv_bytes)
                tmp.close()
                csv_path = tmp.name
        else:
            if retrying_failed:
                _checkpoint.clear()
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='wb')
            tmp.write(csv_bytes)
            tmp.close()
            csv_path = tmp.name

        fieldnames, source_rows = _read_source_rows(csv_path)
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
                'failed_input_rows': [],
                'counters': {'new': 0, 'failed': 0, 'skipped': 0},
                'log': ['Retrying failed rows...' if retrying_failed else ('Resuming from checkpoint...' if skip_hashes or skip_addresses else 'Starting...')],
                'started_at': datetime.now(),
                'csv_hash': h,
                'tmp_csv_path': csv_path,
                'last_hash': '',
                'original_fieldnames': fieldnames,
                'original_rows': source_rows,
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
    except Exception:
        with _lock:
            _job['status'] = 'idle'
        raise


def start(csv_bytes: bytes, etherscan_key: Optional[str] = None) -> None:
    """
    Start the pipeline in a background thread.

    If a checkpoint for the same CSV exists, resumes from that checkpoint.
    If a checkpoint for a different CSV exists, clears it and starts fresh.
    Raises RuntimeError if a job is already running.
    """
    _start_job(csv_bytes, etherscan_key=etherscan_key)


def retry_failed(etherscan_key: Optional[str] = None) -> None:
    """Retry failed source rows from the last completed/stopped job via the UI."""
    with _lock:
        if _job['status'] in ('running', 'starting'):
            raise RuntimeError('A job is already running.')
        fieldnames = list(_job.get('original_fieldnames') or [])
        failed_rows = list(_job.get('failed_input_rows') or [])
        successful_rows = list(_job.get('rows') or [])

    if not fieldnames or not failed_rows:
        raise RuntimeError('No failed rows are available to retry.')

    csv_bytes = _rows_to_csv_bytes(fieldnames, failed_rows)
    _start_job(
        csv_bytes,
        etherscan_key=etherscan_key,
        initial_rows=successful_rows,
        retrying_failed=True,
    )


def get_failed_report() -> Tuple[List[str], List[Dict[str, str]]]:
    """Return failed source rows with the exact original CSV columns/order."""
    with _lock:
        return list(_job.get('original_fieldnames') or []), list(_job.get('failed_input_rows') or [])


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
        if _job['status'] in ('running', 'starting'):
            return False

    try:
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
        fieldnames, source_rows = _read_source_rows(csv_path)

        try:
            started_at = datetime.fromisoformat(existing.get('started_at', ''))
        except ValueError:
            started_at = datetime.now()

        stop_event = threading.Event()

        with _lock:
            if _job['status'] in ('running', 'starting'):
                return False  # race condition: someone else started while we checked
            _job.update({
                'status': 'running',
                'stop_event': stop_event,
                'progress': {
                    'current': len(skip_hashes) + len(skip_addresses),
                    'total': 0,
                },
                'rows': prior_rows,
                'errors': [],
                'failed_input_rows': [],
                'counters': {'new': 0, 'failed': 0, 'skipped': 0},
                'log': ['Auto-resuming from checkpoint...'],
                'started_at': started_at,
                'csv_hash': existing.get('csv_hash'),
                'tmp_csv_path': csv_path,
                'last_hash': '',
                'original_fieldnames': fieldnames,
                'original_rows': source_rows,
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
    except Exception:
        with _lock:
            if _job['status'] == 'starting':
                _job['status'] = 'idle'
        return False
