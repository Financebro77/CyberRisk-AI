import { ShieldCheck } from 'lucide-react';

/** The CyberRisk AI mark — a shield in the brand square. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <div
      className="flex items-center justify-center rounded-lg bg-brand-600 text-white"
      style={{ width: size, height: size }}
    >
      <ShieldCheck style={{ width: size * 0.6, height: size * 0.6 }} />
    </div>
  );
}
