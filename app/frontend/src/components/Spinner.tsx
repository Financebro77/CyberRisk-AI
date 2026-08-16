import { Loader2 } from 'lucide-react';

/** Full-width loading state for the synchronous Monte Carlo runs. */
export function Spinner({
  label = 'Running the model…',
  small,
}: {
  label?: string;
  small?: boolean;
}) {
  if (small) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-ink-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
        {label}
      </span>
    );
  }
  return (
    <div className="card panel-in flex items-center justify-center gap-4 px-6 py-12">
      <div className="relative">
        <Loader2 className="h-7 w-7 animate-spin text-accent" />
        <span className="absolute -inset-2 rounded-full bg-accent/10 blur-md" />
      </div>
      <div className="text-left">
        <div className="text-sm font-medium text-ink-900">{label}</div>
        <div className="mt-0.5 text-xs text-ink-500">
          This typically takes a few seconds — the Monte Carlo engine is computing 100k simulated years.
        </div>
      </div>
    </div>
  );
}

/** Small inline spinner for buttons. */
export function InlineSpinner() {
  return <Loader2 className="h-4 w-4 animate-spin" />;
}
