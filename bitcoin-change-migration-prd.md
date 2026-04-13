# Bitcoin Change — Fee Calculator
## PRD + מסמך איפיון טכני מלא
### מיגרציה: Streamlit → Next.js (Vercel) + FastAPI (Render)

---

> **הוראות לקלאוד קוד**: קרא מסמך זה מהתחלה לסוף לפני שאתה כותב שורת קוד אחת.
> כל החלטת ארכיטקטורה, שמות קבצים, מבנה תיקיות, ו-API contracts מוגדרים כאן.
> אל תניח הנחות — אם משהו לא ברור, עצור ושאל.

---

## 1. רקע ומטרה

### מה המערכת עושה כיום
אפליקציית Streamlit של חברת **Bitcoin Change** — חברת ATM לקריפטו.
הכלי מקבל קובץ CSV ממערכת ה-ATM, מחלץ עסקאות cashIn ו-cashOut, ולכל עסקה:
1. שולף את נתוני העסקה מ-Blockchain (Etherscan / Blockchain.info)
2. מחשב את עמלת הרשת ששולמה (gas fee / mining fee) במטבע המקורי
3. ממיר לדולר לפי שער היסטורי (CoinGecko)
4. ממיר לשקלים לפי שער USD/ILS ביום העסקה (Yahoo Finance)
5. מוסיף גרסה עם מרווח 6%
6. מייצא קובץ CSV מלא עם כל הנתונים

### למה לעבור
- **Sleep Mode**: Streamlit Community Cloud מכניס את האפליקציה לשינה לאחר 7 ימים — רושם ראשוני גרוע
- **UI מוגבל**: Streamlit = framework לדאטה סיינטיסטים, לא מוצר ויזואלי
- **לא branded**: URL לא מותאם מותג, ה-Streamlit header גלוי
- **לא responsive**: נשבר במובייל
- **Performance**: כל אינטראקציה מריצה מחדש את כל הסקריפט Python

### מה רוצים להשיג
אפליקציית web מקצועית ו-branded הנראית כמו מוצר אמיתי,
מבוססת על **הלוגיקה הקיימת בלי לשכתב אותה** — רק לעטוף אותה ב-API מנוהל.

---

## 2. פלטת צבעים ו-Brand

מבוסס על לוגו Bitcoin Change:

```css
/* Bitcoin Change Design Tokens */
--bc-gold:        #F0A500;   /* Primary — הצהוב-זהב של הלוגו */
--bc-gold-hover:  #D4920A;   /* Hover state */
--bc-gold-light:  #FFF4D6;   /* Background tint */
--bc-black:       #0A0A0A;   /* Primary background */
--bc-surface:     #141414;   /* Card background */
--bc-surface-2:   #1E1E1E;   /* Elevated surface */
--bc-border:      #2A2A2A;   /* Border color */
--bc-text:        #FFFFFF;   /* Primary text */
--bc-text-muted:  #9B9B9B;   /* Secondary text */
--bc-success:     #22C55E;
--bc-error:       #EF4444;
--bc-warning:     #F59E0B;
```

**Font**: Inter (Google Fonts) — weights 400, 500, 600
**Logo**: השתמש בקובץ `logo_bit.jpg` מהריפו עבור ה-favicon ו-header

---

## 3. ארכיטקטורה

```
┌─────────────────────────────────────────────┐
│           FRONTEND — Next.js 14             │
│           TypeScript + Tailwind             │
│           Deployed: Vercel (Free)           │
│           URL: [custom domain / vercel.app] │
└────────────────┬────────────────────────────┘
                 │  REST API (JSON)
                 │  POST /api/jobs
                 │  GET  /api/jobs/{id}/status
                 │  GET  /api/jobs/{id}/results
                 │  POST /api/jobs/{id}/stop
                 │
┌────────────────▼────────────────────────────┐
│           BACKEND — FastAPI                 │
│           Python 3.11                       │
│           Deployed: Render.com (Free)       │
│           Scripts קיימים: ללא שינוי        │
└─────────────────────────────────────────────┘
```

### עקרון מרכזי
**הסקריפטים הקיימים (`runner.py`, `job_manager.py`, `process_transactions.py` וכד') לא משתנים.**
FastAPI הוא רק HTTP wrapper על `job_manager.py` הקיים.

---

## 4. מבנה תיקיות

```
bitcoin-change-fee-calculator/
│
├── frontend/                          # Next.js App
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── public/
│   │   └── logo.jpg                   # העתק של logo_bit.jpg
│   └── src/
│       ├── app/
│       │   ├── layout.tsx             # Root layout עם font + metadata
│       │   ├── page.tsx               # עמוד ראשי (/) — כולל הכל
│       │   └── globals.css            # CSS variables + Tailwind imports
│       ├── components/
│       │   ├── Header.tsx             # לוגו + כותרת
│       │   ├── UploadZone.tsx         # Drag & drop CSV upload
│       │   ├── JobPanel.tsx           # Progress + status panel (polling)
│       │   ├── ResultsTable.tsx       # טבלת תוצאות
│       │   ├── StatsCards.tsx         # KPI cards: processed / failed / skipped
│       │   └── DownloadButton.tsx     # כפתור הורדת CSV
│       ├── hooks/
│       │   └── useJobPoller.ts        # Custom hook לpolling כל שנייה
│       └── lib/
│           ├── api.ts                 # API client functions
│           └── types.ts               # TypeScript interfaces
│
├── backend/                           # FastAPI App
│   ├── main.py                        # FastAPI app + routes
│   ├── requirements.txt               # כולל את כל הdependencies הקיימים + fastapi/uvicorn
│   ├── .env.example
│   └── scripts/                       # העתקה מלאה של scripts/ הקיים
│       ├── checkpoint.py              # ללא שינוי
│       ├── job_manager.py             # ללא שינוי
│       ├── runner.py                  # ללא שינוי
│       ├── process_merchant_csv.py    # ללא שינוי
│       ├── process_transactions.py    # ללא שינוי
│       ├── eth_chash_out_exchange.py  # ללא שינוי
│       ├── fetch_blockchain_data.py   # ללא שינוי
│       └── fetch_exchange_rates.py    # ללא שינוי
│
├── .gitignore
└── README.md
```

---

## 5. Backend — FastAPI

### 5.1 קובץ `backend/main.py`

```python
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
```

### 5.2 Endpoints מלאים

#### `GET /health`
```
Response: {"status": "ok", "version": "1.0.0"}
```

#### `POST /api/jobs`
מקבל קובץ CSV, מוודא תקינות, מתחיל job ברקע.

```
Request:  multipart/form-data  { file: CSV }
Response 200: { "job_id": "singleton", "message": "Job started" }
Response 409: { "detail": "A job is already running" }
Response 422: { "detail": "Invalid file: Missing required columns: ..." }
```

**מימוש**:
```python
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
```

#### `GET /api/jobs/status`
Polling endpoint — קרוא ע"י ה-frontend כל שנייה.

```
Response 200:
{
  "status": "running" | "done" | "stopped" | "error" | "idle",
  "progress": { "current": 45, "total": 120 },
  "counters": { "new": 40, "failed": 2, "skipped": 3 },
  "log": ["Found 80 cashin...", "Processing 40 cashout..."],
  "last_hash": "0x1234...abcd",
  "elapsed_seconds": 47.3,
  "errors": [{ "hash": "0xabc...", "reason": "timeout" }]
}
```

**מימוש**:
```python
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
```

#### `POST /api/jobs/stop`
```
Response 200: { "message": "Stop signal sent" }
```

```python
@app.post("/api/jobs/stop")
def stop_job():
    job_manager.stop()
    return {"message": "Stop signal sent"}
```

#### `GET /api/jobs/results`
מחזיר את ה-CSV כ-download. זמין רק כשסטטוס הוא `done` או `stopped`.

```
Response 200: CSV file download (Content-Disposition: attachment; filename="fee_results.csv")
Response 409: { "detail": "No results available yet" }
```

```python
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
```

### 5.3 `backend/requirements.txt`

```
# Existing dependencies
requests>=2.31.0
pandas>=2.0.0
python-dotenv>=1.0.0
yfinance>=0.2.0

# New — FastAPI server
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.9
```

### 5.4 Environment Variables (backend)

```bash
# .env.example
ETHERSCAN_API_KEY=your_key_here
ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:3000
```

### 5.5 Render.com Configuration

קובץ `render.yaml` בשורש ה-`backend/`:
```yaml
services:
  - type: web
    name: bitcoin-change-api
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: ETHERSCAN_API_KEY
        sync: false
      - key: ALLOWED_ORIGINS
        sync: false
```

**חשוב לגבי Render Free Tier Sleep Mode**:
Render.com Free tier גם נרדם לאחר 15 דקות idle.
פתרון: הוסף "wake up" ping מה-frontend כשהמשתמש נכנס לדף:
```typescript
// בתוך useEffect ב-page.tsx
useEffect(() => {
  fetch(`${API_BASE}/health`).catch(() => {}); // silent wake-up ping
}, []);
```
**לאפשרות ללא sleep**: שדרג ל-Render Starter ($7/חודש) — מומלץ לproduction.

---

## 6. Frontend — Next.js

### 6.1 `frontend/package.json` (dependencies)

```json
{
  "dependencies": {
    "next": "14.2.0",
    "react": "^18",
    "react-dom": "^18",
    "typescript": "^5",
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "tailwindcss": "^3.4",
    "autoprefixer": "^10",
    "postcss": "^8",
    "clsx": "^2.1.0"
  }
}
```

**ללא** shadcn/ui, ללא Recharts — ה-UI פשוט מספיק עם Tailwind בלבד.

### 6.2 `frontend/src/lib/types.ts`

```typescript
export type JobStatus = 'idle' | 'running' | 'done' | 'stopped' | 'error';

export interface JobProgress {
  current: number;
  total: number;
}

export interface JobCounters {
  new: number;
  failed: number;
  skipped: number;
}

export interface JobError {
  hash: string;
  reason: string;
}

export interface JobState {
  status: JobStatus;
  progress: JobProgress;
  counters: JobCounters;
  log: string[];
  last_hash: string;
  elapsed_seconds: number | null;
  errors: JobError[];
}
```

### 6.3 `frontend/src/lib/api.ts`

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function startJob(file: File): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/api/jobs`, { method: 'POST', body: form });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail ?? 'Failed to start job');
  }
  return res.json();
}

export async function getStatus(): Promise<JobState> {
  const res = await fetch(`${API_BASE}/api/jobs/status`);
  if (!res.ok) throw new Error('Failed to fetch status');
  return res.json();
}

export async function stopJob(): Promise<void> {
  await fetch(`${API_BASE}/api/jobs/stop`, { method: 'POST' });
}

export function getResultsUrl(): string {
  return `${API_BASE}/api/jobs/results`;
}

export async function pingBackend(): Promise<void> {
  await fetch(`${API_BASE}/health`).catch(() => {});
}
```

### 6.4 `frontend/src/hooks/useJobPoller.ts`

```typescript
'use client';
import { useState, useEffect, useRef } from 'react';
import { getStatus } from '@/lib/api';
import type { JobState } from '@/lib/types';

const INITIAL_STATE: JobState = {
  status: 'idle',
  progress: { current: 0, total: 0 },
  counters: { new: 0, failed: 0, skipped: 0 },
  log: [],
  last_hash: '',
  elapsed_seconds: null,
  errors: [],
};

export function useJobPoller() {
  const [state, setState] = useState<JobState>(INITIAL_STATE);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const startPolling = () => {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(async () => {
      try {
        const s = await getStatus();
        setState(s);
        if (s.status !== 'running') stopPolling();
      } catch {/* silent */}
    }, 1000);
  };

  const stopPolling = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  // Initial fetch on mount
  useEffect(() => {
    getStatus().then(setState).catch(() => {});
    return stopPolling;
  }, []);

  return { state, startPolling, stopPolling };
}
```

### 6.5 `frontend/src/app/globals.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bc-gold: #F0A500;
  --bc-gold-hover: #D4920A;
  --bc-gold-light: #FFF4D6;
  --bc-black: #0A0A0A;
  --bc-surface: #141414;
  --bc-surface-2: #1E1E1E;
  --bc-border: #2A2A2A;
  --bc-text: #FFFFFF;
  --bc-text-muted: #9B9B9B;
}

body {
  background-color: var(--bc-black);
  color: var(--bc-text);
  font-family: 'Inter', sans-serif;
}
```

### 6.6 `frontend/tailwind.config.js`

```javascript
module.exports = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        gold: {
          DEFAULT: '#F0A500',
          hover: '#D4920A',
          light: '#FFF4D6',
        },
        bc: {
          black: '#0A0A0A',
          surface: '#141414',
          surface2: '#1E1E1E',
          border: '#2A2A2A',
        },
      },
    },
  },
};
```

---

## 7. Frontend Components — מפרט מלא

### 7.1 `frontend/src/app/layout.tsx`
```tsx
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Bitcoin Change — Fee Calculator',
  description: 'ATM Transaction Fee Calculator',
  icons: { icon: '/logo.jpg' },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="ltr">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
```

### 7.2 `frontend/src/components/Header.tsx`
```tsx
import Image from 'next/image';

export function Header() {
  return (
    <header className="border-b border-bc-border bg-bc-surface px-6 py-4">
      <div className="mx-auto max-w-3xl flex items-center justify-between">
        <Image src="/logo.jpg" alt="Bitcoin Change" width={200} height={44} priority />
        <span className="text-sm text-bc-text-muted">Fee Calculator</span>
      </div>
    </header>
  );
}
```

### 7.3 `frontend/src/components/UploadZone.tsx`

**תיאור**: Drag & drop zone לקובץ CSV.
- צבע border: `--bc-border` במצב רגיל, `--bc-gold` כאשר מרחפים קובץ מעליו (dragover)
- כאשר קובץ נבחר, מציג שם קובץ + גודל
- כפתור "Calculate Fees" מופיע לאחר בחירת קובץ
- כפתור: `bg-gold text-black font-semibold` עם `hover:bg-gold-hover`
- States: `idle`, `file_selected`, `uploading`

```tsx
Props:
  onJobStarted: () => void   // callback לאחר שה-job התחיל בהצלחה
  disabled: boolean          // true כשjob פעיל
```

**לוגיקה**:
1. `<input type="file" accept=".csv">` מוסתר, מופעל ע"י לחיצה על הzone
2. גם drag & drop נתמך (onDragOver, onDrop events)
3. בלחיצה על "Calculate Fees": קרא `startJob(file)` מ-`api.ts`
4. אם שגיאה: הצג error message מתחת לzone (אדום, `text-red-400`)
5. אם הצלחה: קרא `onJobStarted()`

### 7.4 `frontend/src/components/StatsCards.tsx`

שלושה KPI cards בשורה:

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   ✓ Processed   │  │   ✗ Failed      │  │   ↷ Skipped     │
│      [number]   │  │    [number]     │  │    [number]     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

- כל card: `bg-bc-surface border border-bc-border rounded-xl p-5`
- מספר: `text-3xl font-semibold`
- "Processed": `text-green-400`
- "Failed": `text-red-400`
- "Skipped": `text-yellow-400`

```tsx
Props:
  counters: { new: number; failed: number; skipped: number }
```

### 7.5 `frontend/src/components/JobPanel.tsx`

Panel ראשי — מוצג כאשר `status !== 'idle'`.

**Layout**:
```
┌─────────────────────────────────────────────────────┐
│  ● Running...                      [■ Stop]         │
│  ████████████████░░░░░░░  67%  (80/120)             │
│  Elapsed: 01:23   •   Est. remaining: ~00:41        │
│  Last: 0x1a2b3c4d5e6f...                            │
├─────────────────────────────────────────────────────┤
│  [StatsCards]                                       │
├─────────────────────────────────────────────────────┤
│  ▼ Status log (collapsed by default)                │
└─────────────────────────────────────────────────────┘
```

**Progress bar**: `div` עם `bg-bc-border` כרקע, `div` פנימי עם `bg-gold` וanimation `transition-all duration-300`
אחוזים מחושבים: `(progress.current / Math.max(progress.total, 1)) * 100`

**Status badge**:
- `running`: נקודה ירוקה מהבהבת (`animate-pulse`) + "Running..."
- `done`: ✓ ירוק + "Done"
- `stopped`: ⚠ צהוב + "Stopped — partial results available"
- `error`: ✗ אדום + הודעת שגיאה

**כפתור Stop**: `border border-bc-border text-bc-text-muted hover:border-red-500 hover:text-red-400`
קורא `stopJob()` ולאחר מכן `stopPolling()`

**Timing**: פונקציה `formatDuration(seconds)` שמחזירה `MM:SS` או `HH:MM:SS`

**Last hash**: מוצג רק כשstatus=running, מקוצר ל-20 תווים + `...`

**Status log**: `<details>/<summary>` לחשיפה. מציג עד 5 הודעות אחרונות. `text-xs text-bc-text-muted font-mono bg-bc-surface2 rounded p-3`

```tsx
Props:
  state: JobState
  onStop: () => void
```

### 7.6 `frontend/src/components/ResultsTable.tsx`

מוצג רק כשstatus=`done` או `stopped` ויש rows.

**Header**: "Results — N transactions"

**טבלת errors בלבד** (לא הrows עצמם — הם בCSV):
אם יש errors, הצג טבלה קטנה:
```
Hash / Address          │ Reason
0x1234...abcd          │ Request timeout
0x5678...efgh          │ Block not found
```

**כפתור Download**: ראה 7.7

```tsx
Props:
  counters: JobCounters
  errors: JobError[]
  resultsUrl: string
```

### 7.7 `frontend/src/components/DownloadButton.tsx`

```tsx
// כפתור הורדה עם animation
Props:
  href: string     // URL ל-/api/jobs/results
  partial: boolean // true אם status=stopped
```

**מראה**: `bg-gold text-black font-semibold px-6 py-3 rounded-lg hover:bg-gold-hover transition-colors`
**טקסט**: אם partial: "Download Partial Results (CSV)" אחרת: "Download Results (CSV)"

---

## 8. עמוד ראשי — `frontend/src/app/page.tsx`

```tsx
'use client';
import { useEffect, useState } from 'react';
import { Header } from '@/components/Header';
import { UploadZone } from '@/components/UploadZone';
import { JobPanel } from '@/components/JobPanel';
import { ResultsTable } from '@/components/ResultsTable';
import { DownloadButton } from '@/components/DownloadButton';
import { useJobPoller } from '@/hooks/useJobPoller';
import { stopJob, getResultsUrl, pingBackend } from '@/lib/api';

export default function HomePage() {
  const { state, startPolling, stopPolling } = useJobPoller();
  const isActive = state.status === 'running';
  const isDone = state.status === 'done' || state.status === 'stopped';

  useEffect(() => {
    pingBackend(); // Wake up Render backend on page load
    if (state.status === 'running') startPolling();
  }, []);

  const handleJobStarted = () => {
    startPolling();
  };

  const handleStop = async () => {
    await stopJob();
    stopPolling();
  };

  return (
    <div className="min-h-screen bg-bc-black">
      <Header />
      <main className="mx-auto max-w-3xl px-4 py-10 space-y-8">
        {/* Title */}
        <div>
          <h1 className="text-2xl font-semibold text-white">Blockchain Fee Calculator</h1>
          <p className="mt-1 text-sm text-bc-text-muted">
            Upload your ATM transactions CSV to calculate blockchain fees in USD and ILS.
          </p>
        </div>

        {/* Upload — hidden when job active */}
        {!isActive && (
          <UploadZone onJobStarted={handleJobStarted} disabled={isActive} />
        )}

        {/* Job Panel — shown when not idle */}
        {state.status !== 'idle' && (
          <JobPanel state={state} onStop={handleStop} />
        )}

        {/* Results — shown when done/stopped */}
        {isDone && (
          <>
            <ResultsTable
              counters={state.counters}
              errors={state.errors}
              resultsUrl={getResultsUrl()}
            />
            <DownloadButton
              href={getResultsUrl()}
              partial={state.status === 'stopped'}
            />
          </>
        )}
      </main>
    </div>
  );
}
```

---

## 9. Vercel Configuration

### `frontend/next.config.js`
```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  // No rewrites needed — CORS is handled on backend
};

module.exports = nextConfig;
```

### Environment Variables ב-Vercel Dashboard
```
NEXT_PUBLIC_API_URL=https://bitcoin-change-api.onrender.com
```

**חשוב**: `NEXT_PUBLIC_` prefix הכרחי כדי שהמשתנה יהיה זמין בclient-side code.

---

## 10. שינויים נדרשים בסקריפטים הקיימים

**כמעט ללא שינויים** — זה היה העיקרון.

השינוי היחיד הנדרש: `job_manager.py` ו-`checkpoint.py` משתמשים ב-path יחסי עבור תיקיית ה-checkpoint:

```python
# checkpoint.py — שורה 10 (הנוכחית)
CHECKPOINT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'checkpoint'
)
```

ב-Render, תיקיית ה-`/opt/render/project/src/checkpoint/` תיווצר אוטומטית.
**אין לשנות את הנתיב** — הוא עובד גם ב-backend/ directory.

**שינוי אחד**: ב-`job_manager.py`, ה-`auto_resume_if_checkpoint()` נקרא מ-`main.py` במקום מ-`app.py`:
```python
# main.py
job_manager.auto_resume_if_checkpoint()  # כבר מוגדר למעלה
```

---

## 11. Deployment — שלב אחר שלב

### שלב 1: Backend על Render

1. Push את תוכן `backend/` ל-GitHub repo נפרד (או subfolder)
2. ב-Render.com → New Web Service → Connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. הוסף environment variables:
   - `ETHERSCAN_API_KEY` = המפתח הקיים
   - `ALLOWED_ORIGINS` = `https://your-frontend.vercel.app`
6. Deploy. שמור את ה-URL: `https://bitcoin-change-api.onrender.com`

### שלב 2: Frontend על Vercel

1. Push את תוכן `frontend/` ל-GitHub
2. ב-vercel.com → New Project → Import repo
3. Framework: Next.js (auto-detected)
4. הוסף environment variable:
   - `NEXT_PUBLIC_API_URL` = ה-URL מ-Render
5. Deploy.
6. (אופציונלי) הוסף custom domain בהגדרות Vercel

### שלב 3: עדכן ALLOWED_ORIGINS ב-Render
לאחר שמקבלים את ה-Vercel URL, עדכן את `ALLOWED_ORIGINS` ב-Render env vars.

---

## 12. Local Development

### הרצת Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # הכנס את ETHERSCAN_API_KEY
uvicorn main:app --reload --port 8000
```

### הרצת Frontend
```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

פתח: `http://localhost:3000`

---

## 13. CSV Input Format (תיעוד לclaude code)

הקובץ שהמשתמש מעלה חייב להכיל את העמודות הבאות:

| עמודה | סוג | תיאור |
|---|---|---|
| `txClass` | string | `cashIn` או `cashOut` |
| `status` | string | `Sent` (עבור cashIn) / `Success` (עבור cashOut) |
| `txHash` | string | hash עסקה (עבור cashIn) |
| `toAddress` | string | כתובת ארנק ETH (עבור cashOut) |
| `cryptoCode` | string | `BTC`, `ETH`, `USDT` |

### קריטריוני סינון:
- **CashIn**: `txClass == 'cashIn'` AND `status == 'Sent'` AND `txHash` לא ריק
- **CashOut**: `txClass == 'cashOut'` AND `status == 'Success'` AND `cryptoCode == 'ETH'` AND `toAddress` לא ריק

---

## 14. Output CSV Columns (לתיעוד)

| עמודה | תיאור |
|---|---|
| `source` | `cashin` / `cashout` |
| `hash` | מזהה עסקה |
| `blockchain` | `BTC` / `ETH` / `USDT-ERC20` |
| `transaction_type` | סוג עסקה |
| `amount` | כמות נשלחה |
| `wallet_address` | כתובת ארנק |
| `date` | תאריך עסקה (YYYY-MM-DD) |
| `fee_crypto` | עמלה במטבע מקורי |
| `fee_crypto_symbol` | סימול המטבע |
| `fee_usd` | עמלה בדולר |
| `usd_ils_rate` | שער USD/ILS ביום העסקה |
| `fee_ils_standard` | עמלה בשקלים |
| `fee_ils_markup_6pct` | עמלה בשקלים + 6% מרווח |
| `crypto_amount_sent` | כמות קריפטו |
| `error` | שגיאה (אם יש) |

---

## 15. נקודות תשומת לב לclaude code

1. **אל תשכתב לוגיקה עסקית** — `scripts/` מועתקים כמות שהם. כל השינויים רק ב-`main.py`

2. **job_manager הוא singleton** — ה-FastAPI server מריץ תהליך אחד ב-Render. ה-state נשמר ב-memory. זה מספיק — האפליקציה מיועדת למשתמש בודד בכל פעם.

3. **Polling ב-1 שנייה** — ה-`useJobPoller` hook מבצע GET לכל שנייה כשjob רץ. כשמסתיים, מפסיק.

4. **Download is a direct link** — כפתור ה-download הוא `<a href={resultsUrl} download>` — לא fetch מ-JavaScript. זה יגרום לbrowser לפתוח save dialog.

5. **CORS must be set** — `ALLOWED_ORIGINS` ב-FastAPI חייב לכלול את ה-Vercel domain. בdev: `http://localhost:3000`.

6. **Wake-up ping** — ב-`page.tsx`, `useEffect` שולח GET ל`/health` מיד בטעינה. זה "מעיר" את Render backend שנרדם.

7. **File validation error** — `UploadZone` צריך להציג הודעת שגיאה ברורה אם ה-backend מחזיר 422. הודעה לדוגמה: "Invalid file: Missing required columns: cryptoCode, txHash"

8. **Partial results** — אם המשתמש לוחץ Stop, הכפתור "Download Partial Results" צריך לעבוד. הbackend מחזיר את כל ה-rows שנאספו עד כה.

9. **Auto-resume display** — אם ב-page load ה-status מ-GET /api/jobs/status הוא `running` (resume ממצב checkpoint), ה-frontend צריך להתחיל polling אוטומטית.

10. **TypeScript strict** — השתמש ב-`tsconfig.json` עם `"strict": true`.

---

## 16. לא בסקופ (Out of Scope)

הפיצ'רים הבאים **אינם** בגרסה הנוכחית. אל תממש אותם:

- אימות משתמשים / login
- שמירת היסטוריית jobs
- מספר jobs במקביל
- Dashboard עם גרפים
- Webhook notifications
- Real-time WebSockets (polling מספיק)
- Multi-language support
- Mobile app

---

*מסמך זה נכתב על בסיס ניתוח מלא של קוד המקור ב- `github.com/gen-git-26/sent-trx-fees` ושל לוגו Bitcoin Change.*
*גרסה: 1.0 | תאריך: ינואר 2026*
