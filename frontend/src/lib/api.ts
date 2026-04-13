import type { JobState } from './types';

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
