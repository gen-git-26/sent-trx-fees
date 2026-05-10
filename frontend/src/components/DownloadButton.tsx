import type { ReactNode } from 'react';

interface Props {
  href: string;
  partial?: boolean;
  variant?: 'primary' | 'secondary' | 'danger';
  children?: ReactNode;
}

const styles = {
  primary: 'bg-gold text-black hover:bg-gold-hover',
  secondary: 'border border-bc-border text-bc-text hover:border-gold hover:text-gold',
  danger: 'border border-red-500/60 text-red-400 hover:bg-red-500/10',
};

export function DownloadButton({ href, partial = false, variant = 'primary', children }: Props) {
  return (
    <a
      href={href}
      download
      className={`inline-block font-semibold px-6 py-3 rounded-lg transition-colors ${styles[variant]}`}
    >
      {children ?? (partial ? 'Download Partial Results (CSV)' : 'Download Results (CSV)')}
    </a>
  );
}
