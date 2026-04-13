# Background Pipeline — Design Spec
**Date:** 2026-04-12  
**Status:** Approved

## Overview

Upgrade the Bitcoin/ETH fee-calculator Streamlit app so the processing pipeline:
1. Continues running when the machine sleeps or the browser disconnects
2. Can be stopped mid-run with partial results downloadable immediately
3. Shows a live progress panel (% done, elapsed, ETA, counters)
4. Saves a checkpoint after every transaction so a crashed/interrupted run can auto-resume

---

## Architecture

### New files

| File | Purpose |
|------|---------|
| `scripts/job_manager.py` | Global background-thread state, start/stop API |
| `scripts/checkpoint.py` | Read/write checkpoint JSON and partial CSV to disk |
| `checkpoint/job_state.json` | Active checkpoint (deleted on clean finish) |
| `checkpoint/partial_results.csv` | Rolling results file (append per transaction) |

### Modified files

| File | Change |
|------|--------|
| `app.py` | Replace blocking pipeline call with polling UI loop |
| `scripts/runner.py` | Accept `skip_hashes` / `skip_addresses` sets for resume |

---

## Components

### `job_manager.py`

Module-level singleton dict shared across all Streamlit sessions in the same process:

```python
_job = {
    "status": "idle",          # idle | running | stopped | done | error
    "thread": None,            # threading.Thread
    "stop_event": None,        # threading.Event
    "progress": {"current": 0, "total": 0},
    "rows": [],                # accumulated result rows
    "errors": [],              # {"hash": str, "reason": str}
    "counters": {"new": 0, "failed": 0, "skipped": 0},
    "log": [],                 # status message strings (last ~20)
    "started_at": None,        # datetime
    "csv_hash": None,          # SHA-256 of uploaded CSV bytes
    "tmp_csv_path": None,      # path to temp CSV file
}
```

Public API:
- `start(csv_bytes, etherscan_key)` — validates no job running, writes temp CSV, starts thread
- `stop()` — sets `stop_event`; thread finishes current transaction then exits
- `get_state()` — returns a snapshot dict safe to read from the UI thread
- `auto_resume_if_checkpoint()` — called at app startup; if `job_state.json` exists, starts a resume thread

### `checkpoint.py`

- `save(job_state)` — writes `checkpoint/job_state.json` (processed hashes/addresses, csv_path, csv_hash, started_at)
- `load()` → dict or None
- `append_result(row)` — appends one row to `checkpoint/partial_results.csv`
- `load_partial_results()` → list of dicts
- `clear()` — deletes both checkpoint files (called on clean finish)

### `runner.py` changes

`run_pipeline` gains two new optional parameters:
```python
def run_pipeline(
    file_path: str,
    max_workers: int = 2,
    etherscan_api_key: str = None,
    skip_hashes: set = None,       # NEW
    skip_addresses: set = None,    # NEW
    stop_event: threading.Event = None,  # NEW
) -> Generator[Dict, None, None]:
```

- Hashes/addresses in `skip_*` sets are skipped at the start of each worker function
- Before each transaction the worker checks `stop_event.is_set()`; if True, yields `{'type': 'stopped'}` and returns
- New yield type: `{'type': 'stopped'}` — signals clean stop

---

## Data Flow

```
app.py (UI thread)
  │
  ├─ upload CSV → job_manager.start()
  │                    │
  │                    └─ Thread: runner.run_pipeline()
  │                                │
  │                                ├─ per transaction: checkpoint.append_result()
  │                                │                   checkpoint.save()
  │                                │
  │                                └─ on stop/done: job._status updated
  │
  ├─ st.rerun() every 1s → job_manager.get_state() → render progress panel
  │
  └─ Stop button → job_manager.stop()
```

---

## UI — Progress Panel

Shown while `status == "running"` or `status == "stopped"`:

```
● Running...                              [■ Stop]

████████████░░░░░░░  63% (126/200)

Status: Processing 0xabc123...
Elapsed: 00:04:32      Est. remaining: ~02:38

✓ 118 succeeded    ✗ 8 failed    ↷ 0 skipped
```

- Progress bar: `st.progress(current / total)`
- ETA: `elapsed / current * (total - current)` — shown only after ≥5 transactions
- Elapsed: `datetime.now() - started_at`
- Log: last 5 status messages in `st.info` expandable section

After stop/done: Download button appears immediately using `partial_results.csv` or final rows.

---

## Checkpoint / Resume Flow

**On app startup** (`app.py` top-level, before any UI):
1. `job_manager.auto_resume_if_checkpoint()` is called
2. If `job_state.json` exists and `status == "running"`:
   - Loads `processed_hashes`, `processed_addresses`, `csv_path`
   - If temp CSV still exists → starts resume thread with `skip_*` sets populated
   - If temp CSV missing → marks checkpoint as unresumable, shows warning

**CSV identity check:**
- SHA-256 of uploaded bytes stored in checkpoint
- On resume, if user uploads a new file with different hash → prompt: "Different file detected. Clear checkpoint and start fresh?"

**Clean finish:**
- `checkpoint.clear()` is called → deletes `job_state.json` and `partial_results.csv`

---

## Error Handling

| Scenario | Behavior |
|----------|---------|
| Machine sleeps | Thread suspended by OS, resumes on wake — no action needed |
| Browser disconnects | Streamlit process stays alive, thread keeps running |
| Streamlit server crash | Thread dies; checkpoint on disk allows resume at next startup |
| Temp CSV deleted (OS cleanup) | Resume not possible; warning shown, user must re-upload |
| Etherscan API error per-tx | Logged as error, transaction marked failed, pipeline continues |
| Fatal API failure (rate-limit) | `stop_event` set, partial results saved, error shown |

---

## Out of Scope

- Multiple simultaneous jobs (one job at a time)
- Authentication / multi-user isolation
- Persistent storage beyond local filesystem
