import { Loader2 } from 'lucide-react';
import { Logo } from './Logo';

/** Full-screen loading shown while a lazy route chunk loads. */
export function PageLoader() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-ink-50">
      <Logo size={44} />
      <div className="flex items-center gap-2 text-sm text-ink-500">
        <Loader2 className="h-4 w-4 animate-spin text-accent" />
        Loading workspace…
      </div>
    </div>
  );
}
