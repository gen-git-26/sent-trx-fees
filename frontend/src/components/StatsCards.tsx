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
