"""
main.py — FastAPI wrapper around the existing job_manager.py pipeline.
All business logic stays in scripts/. This file only handles HTTP.
"""
import io
import csv
import os
import sys
import tempfile
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

import job_manager
from runner import validate_csv_columns, MissingColumnsError
from process_merchant_csv import OUTPUT_COLUMNS

job_manager.auto_resume_if_checkpoint()

app = FastAPI(title="Bitcoin Change Fee Calculator API", version="1.0.0")

# CORS — allow Vercel frontend domain + localhost for dev
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/jobs")
async def start_job(file: UploadFile = File(...)):
    file_bytes = await file.read()

    # Validate columns using existing function
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode='wb') as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        validate_csv_columns(tmp_path)
    except MissingColumnsError as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        os.unlink(tmp_path)

    etherscan_key = os.getenv("ETHERSCAN_API_KEY")

    try:
        job_manager.start(file_bytes, etherscan_key=etherscan_key)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"job_id": "singleton", "message": "Job started"}


@app.get("/api/jobs/status")
def get_status():
    state = job_manager.get_state()
    elapsed = None
    if state.get('started_at'):
        from datetime import datetime
        elapsed = (datetime.now() - state['started_at']).total_seconds()
    return {
        "status": state['status'],
        "progress": state['progress'],
        "counters": state['counters'],
        "log": state['log'],
        "last_hash": state.get('last_hash', ''),
        "elapsed_seconds": round(elapsed, 1) if elapsed else None,
        "errors": state.get('errors', []),
    }


@app.post("/api/jobs/stop")
def stop_job():
    job_manager.stop()
    return {"message": "Stop signal sent"}


@app.get("/api/jobs/results")
def download_results():
    state = job_manager.get_state()
    if state['status'] not in ('done', 'stopped') or not state.get('rows'):
        raise HTTPException(status_code=409, detail="No results available yet")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(state['rows'])

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fee_results.csv"}
    )
