import { AlertTriangle, RotateCcw } from 'lucide-react';

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

/** Friendly error state for a failed API call, with optional retry. */
export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="card panel-in flex items-center gap-3 border-risk-high/30 bg-risk-high/5 px-4 py-3"
    >
      <AlertTriangle className="h-4 w-4 shrink-0 text-risk-high" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-risk-high">Something went wrong</div>
        <div className="truncate text-xs text-ink-600">{message}</div>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-risk-high/30 px-3 py-1.5 text-xs font-semibold text-risk-high transition-colors hover:bg-risk-high/10"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Retry
        </button>
      )}
    </div>
  );
}

/** Neutral "more information needed" callout, matching the tool guard. */
export function NeedsMoreInfo({ needed }: { needed: string[] }) {
  return (
    <div className="card panel-in flex items-center gap-3 border-ink-300 bg-ink-100 px-4 py-3">
      <div>
        <span className="text-sm font-semibold text-ink-700">More information needed:</span>
        <span className="ml-1 text-sm text-ink-600">{needed.join(', ')}</span>
      </div>
      <span className="ml-auto text-xs text-ink-500">Add the client's revenue and security controls.</span>
    </div>
  );
}
