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
