# Frontend Components — Design Spec
**Date**: 2026-04-13  
**Session**: 4 — Components  
**Source**: PRD §6–7

---

## Scope

Create the Next.js frontend scaffold and 5 UI components. No page wiring. The components are standalone and importable.

---

## Scaffold Files

| File | Purpose |
|---|---|
| `frontend/package.json` | Next.js 14, TypeScript, Tailwind CSS, autoprefixer, postcss |
| `frontend/next.config.js` | Standard Next.js config (no special options needed) |
| `frontend/tailwind.config.js` | Custom color utilities mapping to CSS vars |
| `frontend/postcss.config.js` | Tailwind + autoprefixer |
| `frontend/tsconfig.json` | strict: true, `@/` → `./src/` path alias |
| `frontend/src/app/globals.css` | CSS vars + Tailwind base/components/utilities |
| `frontend/src/lib/types.ts` | Shared TypeScript types |
| `frontend/public/logo.jpg` | Copy of `logo_bit.jpg` from repo root |

### Tailwind color mapping (`tailwind.config.js`)
```js
colors: {
  'bc-black':     'var(--bc-black)',
  'bc-surface':   'var(--bc-surface)',
  'bc-surface2':  'var(--bc-surface-2)',
  'bc-border':    'var(--bc-border)',
  'bc-text':      'var(--bc-text)',
  'bc-text-muted':'var(--bc-text-muted)',
  'gold':         'var(--bc-gold)',
  'gold-hover':   'var(--bc-gold-hover)',
}
```

### CSS variables (`globals.css`)
```css
:root {
  --bc-gold: #F0A500;
  --bc-gold-hover: #D4920A;
  --bc-black: #0A0A0A;
  --bc-surface: #141414;
  --bc-surface-2: #1E1E1E;
  --bc-border: #2A2A2A;
  --bc-text: #FFFFFF;
  --bc-text-muted: #9B9B9B;
}
```

### Shared types (`lib/types.ts`)
```ts
export type JobStatus = 'idle' | 'running' | 'done' | 'stopped' | 'error';
export interface JobProgress { current: number; total: number; }
export interface JobCounters { new: number; failed: number; skipped: number; }
export interface JobError { hash: string; reason: string; }
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

---

## Components

### Header
**File**: `frontend/src/components/Header.tsx`  
**Props**: none  
**Behavior**: Static. Logo image (200×44) + "Fee Calculator" label.  
**Styles**: `border-b border-bc-border bg-bc-surface px-6 py-4`, max-w-3xl centered row.

---

### UploadZone
**File**: `frontend/src/components/UploadZone.tsx`  
**Props**: `onJobStarted: () => void`, `disabled: boolean`

**States**:
- `idle` — dashed border (`--bc-border`), "Drop CSV here or click to browse"
- `file_selected` — shows filename + size, "Calculate Fees" button appears
- `uploading` — button disabled/loading

**Behavior**:
- Hidden `<input type="file" accept=".csv">` triggered by zone click
- `onDragOver` / `onDrop` handlers; border turns gold (`--bc-gold`) on dragover
- "Calculate Fees" calls `startJob(file)` from `api.ts`
- On error: red message below zone (`text-red-400`)
- On success: calls `onJobStarted()`

**Button style**: `bg-gold text-black font-semibold hover:bg-gold-hover`

---

### StatsCards
**File**: `frontend/src/components/StatsCards.tsx`  
**Props**: `counters: { new: number; failed: number; skipped: number }`

Three cards in a row:
- **Processed** (`counters.new`) — label `text-green-400`
- **Failed** (`counters.failed`) — label `text-red-400`
- **Skipped** (`counters.skipped`) — label `text-yellow-400`

**Card style**: `bg-bc-surface border border-bc-border rounded-xl p-5`  
**Number style**: `text-3xl font-semibold`

---

### JobPanel
**File**: `frontend/src/components/JobPanel.tsx`  
**Props**: `state: JobState`, `onStop: () => void`  
**Shown when**: `state.status !== 'idle'`

**Sections**:
1. **Status row**: badge (left) + Stop button (right)
   - `running`: green pulse dot + "Running..."
   - `done`: ✓ green + "Done"
   - `stopped`: ⚠ yellow + "Stopped — partial results available"
   - `error`: ✗ red + error message
2. **Progress bar**: `bg-bc-border` track, `bg-gold transition-all duration-300` fill. Percentage = `current / max(total, 1) * 100`. Shows `67% (80/120)` label.
3. **Timing**: `Elapsed: MM:SS • Est. remaining: ~MM:SS`. Helper `formatDuration(seconds)` → `MM:SS` or `HH:MM:SS`.
4. **Last hash**: shown only when `status === 'running'`, truncated to 20 chars + `...`
5. **StatsCards**: embedded
6. **Status log**: `<details>/<summary>` collapsed by default. Last 5 log messages. `text-xs font-mono bg-bc-surface2 rounded p-3`

**Stop button style**: `border border-bc-border text-bc-text-muted hover:border-red-500 hover:text-red-400`

---

### DownloadButton
**File**: `frontend/src/components/DownloadButton.tsx`  
**Props**: `href: string`, `partial: boolean`

**Behavior**: `<a>` styled as button, `download` attribute.  
**Text**: `partial ? "Download Partial Results (CSV)" : "Download Results (CSV)"`  
**Style**: `bg-gold text-black font-semibold px-6 py-3 rounded-lg hover:bg-gold-hover transition-colors`

---

## Out of Scope (Session 4)

- `frontend/src/app/layout.tsx` — page wiring
- `frontend/src/app/page.tsx` — page wiring
- `frontend/src/lib/api.ts` — API calls
- `frontend/src/hooks/useJobPoller.ts` — polling hook
- `frontend/src/components/ResultsTable.tsx` — not in the 5 listed

---

## Implementation Order

1. Scaffold (package.json, configs, globals.css, types.ts, public/logo.jpg)
2. Header (simplest — no state)
3. StatsCards (pure display)
4. DownloadButton (pure display)
5. UploadZone (local state + file handling)
6. JobPanel (most complex — depends on StatsCards)
