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
