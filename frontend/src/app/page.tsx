'use client';
import { useEffect, useState } from 'react';
import { Header } from '@/components/Header';
import { UploadZone } from '@/components/UploadZone';
import { JobPanel } from '@/components/JobPanel';
import { ResultsTable } from '@/components/ResultsTable';
import { DownloadButton } from '@/components/DownloadButton';
import { useJobPoller } from '@/hooks/useJobPoller';
import {
  stopJob,
  getResultsUrl,
  getErrorReportUrl,
  pingBackend,
  retryFailedJob,
} from '@/lib/api';

export default function HomePage() {
  const { state, startPolling, stopPolling } = useJobPoller();
  const [retryError, setRetryError] = useState<string | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const isActive = state.status === 'running';
  const isDone = state.status === 'done' || state.status === 'stopped';
  const hasFailures = state.errors.length > 0 || state.counters.failed > 0;

  useEffect(() => {
    pingBackend(); // Wake up Render backend on page load
    if (state.status === 'running') startPolling();
  }, []);

  const handleJobStarted = () => {
    setRetryError(null);
    startPolling();
  };

  const handleStop = async () => {
    await stopJob();
    stopPolling();
  };

  const handleRetryFailed = async () => {
    setIsRetrying(true);
    setRetryError(null);
    try {
      await retryFailedJob();
      startPolling();
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : 'Failed to retry failed rows');
    } finally {
      setIsRetrying(false);
    }
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
            />

            {retryError && <p className="text-sm text-red-400">{retryError}</p>}

            <div className="flex flex-wrap gap-3">
              {state.successful_results_available && (
                <DownloadButton
                  href={getResultsUrl()}
                  partial={state.status === 'stopped'}
                />
              )}

              {state.failed_report_available && (
                <DownloadButton href={getErrorReportUrl()} variant="danger">
                  Download Error Report (original CSV columns)
                </DownloadButton>
              )}

              {hasFailures && state.failed_report_available && (
                <button
                  onClick={handleRetryFailed}
                  disabled={isRetrying}
                  className="border border-bc-border text-bc-text hover:border-gold hover:text-gold font-semibold px-6 py-3 rounded-lg transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {isRetrying ? 'Starting retry...' : 'Retry Failed Rows'}
                </button>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
