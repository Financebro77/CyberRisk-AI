/** A single shimmering placeholder block. */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

/** Metric-card skeleton used while a simulation runs. */
export function SkeletonCard() {
  return (
    <div className="card p-4">
      <Skeleton className="mb-2 h-3 w-24" />
      <Skeleton className="mb-1 h-6 w-20" />
      <Skeleton className="h-3 w-28" />
    </div>
  );
}

/** Grid of skeleton metric cards, sized for the KPI rows. */
export function SkeletonMetricRow({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

/** Chart-card skeleton with a tall body. */
export function SkeletonChart() {
  return (
    <div className="card p-4">
      <Skeleton className="mb-1 h-4 w-40" />
      <Skeleton className="mb-4 h-3 w-56" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
