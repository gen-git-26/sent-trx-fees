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
