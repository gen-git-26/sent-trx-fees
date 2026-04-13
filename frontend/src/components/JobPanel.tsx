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
