# Streamlit Local UI — Design Spec

**Date:** 2026-03-30
**Status:** Approved

---

## Overview

A local Streamlit web application that wraps the existing `scripts/process_merchant_csv.py` script. The app runs on the user's Windows machine, opens automatically in a browser, and allows a non-technical internal user to upload a CSV, run the fee calculation, and download the result — without touching the terminal or any code.

All data stays on the local machine. No external hosting. No changes to the existing scripts.

---

## Users

Single internal Windows user, non-technical. Runs once a month.

---

## Architecture

```
run.bat (double-click)
    → launches: streamlit run app.py
    → browser opens automatically at localhost
    → user uploads CSV
    → app calls process_merchant_csv.py logic
    → user downloads output CSV
```

The existing `scripts/` directory is unchanged. `app.py` imports and calls the same functions used by `process_merchant_csv.py`. The `.env` file (containing `ETHERSCAN_API_KEY`) is pre-configured and not exposed in the UI.

---

## UI Flow

Single page, three sequential steps:

### Step 1 — Upload
- File uploader: "Upload CSV file"
- Validates immediately on upload:
  - Checks that required columns exist (`txClass`, `txHash`, `toAddress`, `status`, etc.)
  - If invalid: red error message listing exactly which columns are missing
  - If valid: green confirmation, "Run" button appears

### Step 2 — Run
- Button: "Calculate Fees"
- Progress bar with real-time status line (e.g. `[12/142] Processing: 0x011f5a...`)
- If a fatal error occurs mid-run (network failure, API error):
  - Red banner: "Process did not complete successfully"
  - Summary: "X of Y transactions processed before failure"
  - Error detail shown (human-readable, not a stack trace)

### Step 3 — Results
- On full success: green banner "Done — X transactions processed"
- Summary table of failed individual transactions (hash + reason), if any
- Button: "Download Results" — downloads the output CSV
- If process did not complete: download button is hidden; only the error state is shown

---

## Error Handling

| Situation | UI Response |
|---|---|
| Missing/wrong columns in uploaded file | Red message listing missing columns, run blocked |
| Invalid file format (not CSV) | Red message: "Please upload a valid CSV file" |
| API / network error mid-run | Red banner, partial count, error detail |
| Individual transactions failed | Warning section with table: hash + error reason |
| Full success with no errors | Green banner + download button |
| Full success with some errors | Yellow banner + download button + error table |

---

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit application (root of repo) |
| `run.bat` | Double-click launcher for Windows |
| `requirements.txt` | Python dependencies including `streamlit` |

---

## Branding & Colors

Logo file: `logo_bit.jpg` (displayed at top of page)

Color palette derived from the Bitcoin Change logo:

| Role | Color |
|---|---|
| Background | `#0d0d0d` (black) |
| Primary accent | `#f7a51e` (gold/orange) |
| Text | `#ffffff` (white) |
| Buttons | `#f7a51e` background, `#0d0d0d` text |
| Error banners | `#cc3333` |
| Success banners | `#2a7a2a` |

Streamlit custom theme applied via `.streamlit/config.toml`.

---

## Constraints

- Language: English
- Runs locally on Windows
- No data leaves the machine
- `.env` is pre-configured; no API key input in UI
- All existing `scripts/` files remain untouched
