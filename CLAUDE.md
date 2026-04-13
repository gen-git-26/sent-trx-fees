# Bitcoin Change — Fee Calculator Migration

## Project
Migrating Streamlit app to Next.js (frontend) + FastAPI (backend).
PRD: bitcoin-change-migration-prd.md — READ THIS FIRST before any task.

## Stack
- frontend/: Next.js 14, TypeScript, Tailwind, no extra UI libs
- backend/: FastAPI + uvicorn, wrapping existing scripts/ unchanged
- Deploy: Vercel (frontend) + Render.com (backend)

## CRITICAL RULES
- scripts/ directory: COPY ONLY, never modify logic
- backend/main.py: HTTP wrapper only — no business logic
- All colors from CSS vars in globals.css, never hardcode hex
- TypeScript strict: true always

## Commands
- frontend: cd frontend && npm run dev
- backend: cd backend && uvicorn main:app --reload --port 8000
- typecheck: cd frontend && npx tsc --noEmit

## Compaction
When compacting, preserve: list of completed files, failing tests, next task.