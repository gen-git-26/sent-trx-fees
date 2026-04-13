'use client';
import { useEffect } from 'react';
import { Header } from '@/components/Header';
import { UploadZone } from '@/components/UploadZone';
import { JobPanel } from '@/components/JobPanel';
import { ResultsTable } from '@/components/ResultsTable';
import { DownloadButton } from '@/components/DownloadButton';
import { useJobPoller } from '@/hooks/useJobPoller';
// API functions will be implemented in a later session

export default function HomePage() {
  const { state, startPolling, stopPolling } = useJobPoller();
  const isActive = state.status === 'running';
  const isDone = state.status === 'done' || state.status === 'stopped';

  useEffect(() => {
    // pingBackend(); // TODO: implement in backend
    if (state.status === 'running') startPolling();
  }, []);

  const handleJobStarted = () => {
    startPolling();
  };

  const handleStop = async () => {
    // await stopJob(); // TODO: implement in backend
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
              resultsUrl="" // TODO: implement getResultsUrl
            />
            <DownloadButton
              href="" // TODO: implement getResultsUrl
              partial={state.status === 'stopped'}
            />
          </>
        )}
      </main>
    </div>
  );
}
