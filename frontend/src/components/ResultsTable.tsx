'use client';
import type { JobCounters, JobError } from '@/lib/types';

interface Props {
  counters: JobCounters;
  errors: JobError[];
  resultsUrl: string;
}

export function ResultsTable({ counters, errors, resultsUrl }: Props) {
  const total = counters.new + counters.failed + counters.skipped;

  return (
    <div className="bg-bc-surface border border-bc-border rounded-xl p-6 space-y-4">
      <h2 className="text-base font-semibold text-white">
        Results — {total} transactions
      </h2>

      <div className="flex gap-6 text-sm">
        <span className="text-green-400">{counters.new} processed</span>
        <span className="text-red-400">{counters.failed} failed</span>
        <span className="text-yellow-400">{counters.skipped} skipped</span>
      </div>

      {errors.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b border-bc-border text-bc-text-muted">
                <th className="pb-2 pr-4 font-medium">Hash / Address</th>
                <th className="pb-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {errors.map((e, i) => (
                <tr key={i} className="border-b border-bc-border last:border-0">
                  <td className="py-2 pr-4 font-mono text-xs text-bc-text-muted">
                    {e.hash.slice(0, 10)}...{e.hash.slice(-4)}
                  </td>
                  <td className="py-2 text-red-400">{e.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
