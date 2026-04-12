"""
checkpoint.py — Persist job state and partial results to disk.
"""
import csv
import json
import os
import tempfile
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
    fd, tmp = tempfile.mkstemp(dir=CHECKPOINT_DIR, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load() -> Optional[Dict]:
    """Return checkpoint dict, or None if no checkpoint exists."""
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
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


def load_partial_results() -> List[Dict]:
    """Return all rows written so far, or [] if file missing/unreadable."""
    if not os.path.exists(RESULTS_FILE):
        return []
    try:
        with open(RESULTS_FILE, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except (csv.Error, UnicodeDecodeError):
        return []


def clear() -> None:
    """Delete checkpoint files on clean job completion."""
    for path in (STATE_FILE, RESULTS_FILE):
        try:
            if os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass
