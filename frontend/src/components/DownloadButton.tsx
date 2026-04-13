interface Props {
  href: string;
  partial: boolean;
}

export function DownloadButton({ href, partial }: Props) {
  return (
    <a
      href={href}
      download
      className="inline-block bg-gold text-black font-semibold px-6 py-3 rounded-lg hover:bg-gold-hover transition-colors"
    >
      {partial ? 'Download Partial Results (CSV)' : 'Download Results (CSV)'}
    </a>
  );
}
