import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatMoney } from '../lib/format';

export interface StructureData {
  policyLimit: number;
  retention: number;
  insurerPayment: number;
  residual: number;
}

interface Props {
  current: StructureData;
  recommended: StructureData;
  live: StructureData | null;
}

const METRICS = [
  { key: 'policyLimit', label: 'Policy limit' },
  { key: 'retention', label: 'Retention' },
  { key: 'insurerPayment', label: 'Expected recovery' },
  { key: 'residual', label: 'Residual exposure' },
] as const;

/**
 * Current vs Recommended vs live slider setting, all on the same $ axis.
 * Recharts animates bar height changes when `live` updates, so dragging a
 * slider smoothly morphs the bars.
 */
export function InsuranceOptimiseChart({ current, recommended, live }: Props) {
  const data = METRICS.map((m) => ({
    name: m.label,
    Current: current[m.key],
    Recommended: recommended[m.key],
    'Your setting': live?.[m.key] ?? 0,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8 }} barGap={4}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#64748b' }} />
        <YAxis tick={{ fontSize: 12, fill: '#64748b' }} tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} />
        <Tooltip
          formatter={(value, name) => [formatMoney(Number(value)), String(name)]}
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="Current" fill="#94a3b8" radius={[4, 4, 0, 0]} barSize={30} />
        <Bar dataKey="Recommended" fill="#16a34a" radius={[4, 4, 0, 0]} barSize={30}>
          {data.map((_, i) => (
            <Cell key={`rec-${i}`} fill="#16a34a" />
          ))}
        </Bar>
        <Bar dataKey="Your setting" fill="#2563eb" radius={[4, 4, 0, 0]} barSize={30} />
      </BarChart>
    </ResponsiveContainer>
  );
}
