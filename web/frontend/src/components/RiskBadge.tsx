/** Risk category chip with the consulting color coding. */
export function RiskBadge({ category }: { category: string }) {
  const tone = (() => {
    switch (category.toLowerCase()) {
      case 'low':
        return 'bg-risk-low/10 text-risk-low ring-risk-low/30';
      case 'medium':
        return 'bg-risk-med/10 text-risk-med ring-risk-med/30';
      case 'high':
        return 'bg-risk-high/10 text-risk-high ring-risk-high/30';
      case 'critical':
        return 'bg-risk-crit/10 text-risk-crit ring-risk-crit/30';
      default:
        return 'bg-ink-200 text-ink-600 ring-ink-300';
    }
  })();

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold tracking-wide ring-1 ${tone}`}
    >
      {category}
    </span>
  );
}
