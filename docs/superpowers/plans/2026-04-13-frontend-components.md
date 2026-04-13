# Frontend Scaffold + Components Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the Next.js scaffold and 5 UI components (Header, UploadZone, StatsCards, JobPanel, DownloadButton) — no page wiring.

**Architecture:** Next.js 14 App Router with TypeScript strict mode. Components are pure presentational or handle local state only. All colors come from CSS custom properties referenced via Tailwind utilities. Verification at each step is `npx tsc --noEmit` (no test framework in scope).

**Tech Stack:** Next.js 14, React 18, TypeScript 5, Tailwind CSS 3, Inter (Google Fonts)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `frontend/package.json` | Create | Dependencies and scripts |
| `frontend/next.config.js` | Create | Next.js config |
| `frontend/tailwind.config.js` | Create | CSS var → Tailwind utility mapping |
| `frontend/postcss.config.js` | Create | Tailwind + autoprefixer |
| `frontend/tsconfig.json` | Create | strict: true, `@/` alias |
| `frontend/src/app/globals.css` | Create | CSS custom properties + Tailwind imports |
| `frontend/src/lib/types.ts` | Create | Shared TypeScript types (JobState, etc.) |
| `frontend/src/lib/api.ts` | Create | Minimal stub so UploadZone compiles |
| `frontend/public/logo.jpg` | Create | Copy of logo_bit.jpg from repo root |
| `frontend/src/components/Header.tsx` | Create | Logo + title bar |
| `frontend/src/components/StatsCards.tsx` | Create | 3 KPI cards (Processed/Failed/Skipped) |
| `frontend/src/components/DownloadButton.tsx` | Create | Gold download link |
| `frontend/src/components/UploadZone.tsx` | Create | Drag & drop CSV upload with local state |
| `frontend/src/components/JobPanel.tsx` | Create | Progress, status badge, stop button, log |

---

## Task 1: Scaffold — package.json + config files

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/next.config.js`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tsconfig.json`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "bitcoin-change-fee-calculator",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "14.2.3",
    "react": "^18",
    "react-dom": "^18"
  },
  "devDependencies": {
    "typescript": "^5",
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "autoprefixer": "^10.0.1",
    "postcss": "^8",
    "tailwindcss": "^3.3.0"
  }
}
```

- [ ] **Step 2: Create `frontend/next.config.js`**

```js
/** @type {import('next').NextConfig} */
const nextConfig = {};
module.exports = nextConfig;
```

- [ ] **Step 3: Create `frontend/tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        'bc-black':     'var(--bc-black)',
        'bc-surface':   'var(--bc-surface)',
        'bc-surface2':  'var(--bc-surface-2)',
        'bc-border':    'var(--bc-border)',
        'bc-text':      'var(--bc-text)',
        'bc-text-muted':'var(--bc-text-muted)',
        gold:           'var(--bc-gold)',
        'gold-hover':   'var(--bc-gold-hover)',
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 4: Create `frontend/postcss.config.js`**

```js
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "es5",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{"name": "next"}],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 6: Run `npm install`**

```bash
cd frontend && npm install
```

Expected: packages installed, `node_modules/` created, no errors.

- [ ] **Step 7: Commit scaffold configs**

```bash
cd frontend && git add package.json next.config.js tailwind.config.js postcss.config.js tsconfig.json
git commit -m "feat: add Next.js scaffold config files"
```

---

## Task 2: CSS vars, types, api stub, and public logo

**Files:**
- Create: `frontend/src/app/globals.css`
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/public/logo.jpg` (copy)

- [ ] **Step 1: Create `frontend/src/app/globals.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bc-gold:        #F0A500;
  --bc-gold-hover:  #D4920A;
  --bc-gold-light:  #FFF4D6;
  --bc-black:       #0A0A0A;
  --bc-surface:     #141414;
  --bc-surface-2:   #1E1E1E;
  --bc-border:      #2A2A2A;
  --bc-text:        #FFFFFF;
  --bc-text-muted:  #9B9B9B;
}

body {
  background-color: var(--bc-black);
  color: var(--bc-text);
  font-family: 'Inter', sans-serif;
}
```

- [ ] **Step 2: Create `frontend/src/lib/types.ts`**

```ts
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

- [ ] **Step 3: Create `frontend/src/lib/api.ts` (stub)**

This is the minimum needed so `UploadZone` can import `startJob`. Full implementation is a later session.

```ts
// Stub — full implementation in a later session
export async function startJob(file: File): Promise<{ job_id: string }> {
  throw new Error('Not implemented');
}
```

- [ ] **Step 4: Copy logo to public/**

```bash
cp /workspaces/sent-trx-fees/logo_bit.jpg /workspaces/sent-trx-fees/frontend/public/logo.jpg
```

- [ ] **Step 5: Commit**

```bash
cd /workspaces/sent-trx-fees && git add frontend/src/app/globals.css frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/public/logo.jpg
git commit -m "feat: add globals.css, shared types, api stub, and logo"
```

---

## Task 3: Header component

**Files:**
- Create: `frontend/src/components/Header.tsx`

- [ ] **Step 1: Create `frontend/src/components/Header.tsx`**

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

- [ ] **Step 2: Type-check**

```bash
cd /workspaces/sent-trx-fees/frontend && npx tsc --noEmit
```

Expected: no errors. If you see "Cannot find module 'next/image'" ensure `npm install` ran in Task 1.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Header.tsx
git commit -m "feat: add Header component"
```

---

## Task 4: StatsCards component

**Files:**
- Create: `frontend/src/components/StatsCards.tsx`

- [ ] **Step 1: Create `frontend/src/components/StatsCards.tsx`**

```tsx
import type { JobCounters } from '@/lib/types';

interface Props {
  counters: JobCounters;
}

export function StatsCards({ counters }: Props) {
  return (
    <div className="grid grid-cols-3 gap-4">
      <StatCard label="✓ Processed" value={counters.new} labelClass="text-green-400" />
      <StatCard label="✗ Failed" value={counters.failed} labelClass="text-red-400" />
      <StatCard label="↷ Skipped" value={counters.skipped} labelClass="text-yellow-400" />
    </div>
  );
}

function StatCard({
  label,
  value,
  labelClass,
}: {
  label: string;
  value: number;
  labelClass: string;
}) {
  return (
    <div className="bg-bc-surface border border-bc-border rounded-xl p-5">
      <p className={`text-sm font-medium ${labelClass}`}>{label}</p>
      <p className="text-3xl font-semibold text-bc-text mt-1">{value}</p>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd /workspaces/sent-trx-fees/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StatsCards.tsx
git commit -m "feat: add StatsCards component"
```

---

## Task 5: DownloadButton component

**Files:**
- Create: `frontend/src/components/DownloadButton.tsx`

- [ ] **Step 1: Create `frontend/src/components/DownloadButton.tsx`**

```tsx
interface Props {
  href: string;
  partial: boolean;
}

export function DownloadButton({ href, partial }: Props) {
  return (
    <a
      href={href}
      download
      className="inline-block bg-gold text-black font-semibold px-6 py-3 rounded-lg hover:bg-gold-hover transition-colors"
    >
      {partial ? 'Download Partial Results (CSV)' : 'Download Results (CSV)'}
    </a>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd /workspaces/sent-trx-fees/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DownloadButton.tsx
git commit -m "feat: add DownloadButton component"
```

---

## Task 6: UploadZone component

**Files:**
- Create: `frontend/src/components/UploadZone.tsx`

This component manages its own state (idle → file_selected → uploading) and handles drag & drop events.

- [ ] **Step 1: Create `frontend/src/components/UploadZone.tsx`**

```tsx
'use client';
import { useRef, useState } from 'react';
import { startJob } from '@/lib/api';

type UploadState = 'idle' | 'file_selected' | 'uploading';

interface Props {
  onJobStarted: () => void;
  disabled: boolean;
}

export function UploadZone({ onJobStarted, disabled }: Props) {
  const [uploadState, setUploadState] = useState<UploadState>('idle');
  const [file, setFile] = useState<File | null>(null);
  const [dragover, setDragover] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFile(f: File) {
    setFile(f);
    setUploadState('file_selected');
    setError(null);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragover(true);
  }

  function handleDragLeave() {
    setDragover(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragover(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  }

  async function handleCalculate() {
    if (!file) return;
    setUploadState('uploading');
    setError(null);
    try {
      await startJob(file);
      onJobStarted();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setUploadState('file_selected');
    }
  }

  const borderColor = dragover ? 'border-gold' : 'border-bc-border';

  return (
    <div className="space-y-3">
      <div
        className={`border-2 border-dashed ${borderColor} rounded-xl p-10 text-center cursor-pointer transition-colors`}
        onClick={() => { if (!disabled) inputRef.current?.click(); }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleInputChange}
          disabled={disabled}
        />
        {file ? (
          <p className="text-bc-text">
            {file.name}{' '}
            <span className="text-bc-text-muted text-sm">
              ({(file.size / 1024).toFixed(1)} KB)
            </span>
          </p>
        ) : (
          <p className="text-bc-text-muted">Drop CSV here or click to browse</p>
        )}
      </div>

      {uploadState === 'file_selected' && (
        <button
          onClick={handleCalculate}
          className="bg-gold text-black font-semibold px-6 py-3 rounded-lg hover:bg-gold-hover transition-colors"
        >
          Calculate Fees
        </button>
      )}

      {uploadState === 'uploading' && (
        <button
          disabled
          className="bg-gold text-black font-semibold px-6 py-3 rounded-lg opacity-60 cursor-not-allowed"
        >
          Uploading...
        </button>
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd /workspaces/sent-trx-fees/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UploadZone.tsx
git commit -m "feat: add UploadZone component with drag & drop and upload states"
```

---

## Task 7: JobPanel component

**Files:**
- Create: `frontend/src/components/JobPanel.tsx`

This is the most complex component. It imports `StatsCards` and renders sub-sections based on `state.status`.

- [ ] **Step 1: Create `frontend/src/components/JobPanel.tsx`**

```tsx
'use client';
import { StatsCards } from './StatsCards';
import type { JobState, JobStatus } from '@/lib/types';

interface Props {
  state: JobState;
  onStop: () => void;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  if (h > 0) return `${String(h).padStart(2, '0')}:${mm}:${ss}`;
  return `${mm}:${ss}`;
}

function StatusBadge({
  status,
  errorMessage,
}: {
  status: JobStatus;
  errorMessage?: string;
}) {
  if (status === 'running') {
    return (
      <span className="flex items-center gap-2 text-sm text-bc-text">
        <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
        Running...
      </span>
    );
  }
  if (status === 'done') {
    return <span className="text-sm text-green-400">✓ Done</span>;
  }
  if (status === 'stopped') {
    return (
      <span className="text-sm text-yellow-400">⚠ Stopped — partial results available</span>
    );
  }
  if (status === 'error') {
    return <span className="text-sm text-red-400">✗ {errorMessage ?? 'Error'}</span>;
  }
  return null;
}

export function JobPanel({ state, onStop }: Props) {
  const { status, progress, counters, log, last_hash, elapsed_seconds, errors } = state;

  const pct = Math.min(
    100,
    Math.round((progress.current / Math.max(progress.total, 1)) * 100)
  );
  const lastLogs = log.slice(-5);

  const canEstimateRemaining =
    status === 'running' &&
    elapsed_seconds !== null &&
    progress.current > 0 &&
    progress.total > progress.current;

  const estimatedRemaining = canEstimateRemaining
    ? Math.round(
        (elapsed_seconds! / progress.current) * (progress.total - progress.current)
      )
    : null;

  return (
    <div className="bg-bc-surface border border-bc-border rounded-xl p-6 space-y-5">
      {/* Status row */}
      <div className="flex items-center justify-between">
        <StatusBadge status={status} errorMessage={errors[0]?.reason} />
        {status === 'running' && (
          <button
            onClick={onStop}
            className="border border-bc-border text-bc-text-muted hover:border-red-500 hover:text-red-400 px-3 py-1 rounded text-sm transition-colors"
          >
            ■ Stop
          </button>
        )}
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="w-full bg-bc-border rounded-full h-2">
          <div
            className="bg-gold h-2 rounded-full transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-sm text-bc-text-muted">
          {pct}% ({progress.current}/{progress.total})
        </p>
      </div>

      {/* Timing */}
      {elapsed_seconds !== null && (
        <p className="text-sm text-bc-text-muted">
          Elapsed: {formatDuration(elapsed_seconds)}
          {estimatedRemaining !== null && (
            <> • Est. remaining: ~{formatDuration(estimatedRemaining)}</>
          )}
        </p>
      )}

      {/* Last hash */}
      {status === 'running' && last_hash && (
        <p className="text-xs text-bc-text-muted font-mono">
          Last: {last_hash.slice(0, 20)}...
        </p>
      )}

      {/* Stats */}
      <StatsCards counters={counters} />

      {/* Status log */}
      {lastLogs.length > 0 && (
        <details>
          <summary className="text-sm text-bc-text-muted cursor-pointer select-none">
            ▼ Status log
          </summary>
          <div className="mt-2 text-xs text-bc-text-muted font-mono bg-bc-surface2 rounded p-3 space-y-1">
            {lastLogs.map((msg, i) => (
              <p key={i}>{msg}</p>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd /workspaces/sent-trx-fees/frontend && npx tsc --noEmit
```

Expected: no errors. Note: tsc may warn about `next-env.d.ts` not existing — run `npx next build` once to generate it, then re-run tsc.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/JobPanel.tsx
git commit -m "feat: add JobPanel component with progress, status badge, timing, and log"
```

---

## Final Verification

- [ ] **Run full type-check across all components**

```bash
cd /workspaces/sent-trx-fees/frontend && npx tsc --noEmit
```

Expected: 0 errors, 0 warnings.

- [ ] **Confirm all 5 component files exist**

```bash
ls frontend/src/components/
```

Expected output:
```
DownloadButton.tsx  Header.tsx  JobPanel.tsx  StatsCards.tsx  UploadZone.tsx
```
