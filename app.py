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
    file_bytes = uploaded_file.read()

    # Validate columns immediately — write temp file just for validation, clean up after
    with tempfile.NamedTemporaryFile(delete=True, suffix=".csv", mode='wb') as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        try:
            validate_csv_columns(tmp.name)
        except MissingColumnsError as e:
            st.error(f"Invalid file: {e}")
            st.stop()

    st.success("File looks good. Ready to process.")

    # ---- Step 2: Run ----
    st.markdown("---")
    st.subheader("Step 2 — Calculate Fees")

    if st.button("Calculate Fees", type="primary"):
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='wb') as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            progress_bar = st.progress(0)
            status_text = st.empty()

            rows = []
            errors = []
            fatal = False
            summary = {}

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
            if tmp_path:
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

            if errors:
                st.markdown("**Transactions with errors:**")
                st.table([{"Hash / Address": e['hash'], "Reason": e['reason']} for e in errors])

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
