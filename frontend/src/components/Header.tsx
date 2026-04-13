import Image from 'next/image';

export function Header() {
  return (
    <header className="border-b border-bc-border bg-bc-surface px-6 py-4">
      <div className="mx-auto max-w-3xl flex items-center justify-between">
        <Image src="/logo.jpg" alt="Bitcoin Change" width={200} height={44} priority />
        <span className="text-sm text-bc-text-muted">Fee Calculator</span>
      </div>
    </header>
  );
}
