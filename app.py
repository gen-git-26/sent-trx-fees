"""
app.py — Bitcoin Change Fee Calculator (Streamlit UI)
"""

import io
import csv
import sys
import os
import time
import tempfile
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
    pct = min(current / max(total, 1), 1.0) if total > 0 else 0.0

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
