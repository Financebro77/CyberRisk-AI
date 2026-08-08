import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const DOMAIN_LABELS: Record<string, string> = {
  threat_exposure: 'Threat exposure',
  vulnerability_mgmt: 'Vulnerability mgmt',
  access_control: 'Access control',
  endpoint_resilience: 'Endpoint resilience',
  third_party_risk: 'Third-party risk',
  resilience_governance: 'Resilience & governance',
};

/** Horizontal bars for the six domain scores (0-100, higher = worse). */
export function DomainScoresChart({ scores }: { scores: Record<string, number> }) {
  const data = Object.entries(scores).map(([key, value]) => ({
    name: DOMAIN_LABELS[key] ?? key.replace(/_/g, ' '),
    score: value,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 12, fill: '#64748b' }} />
        <YAxis
          type="category"
          dataKey="name"
          width={150}
          tick={{ fontSize: 12, fill: '#334155' }}
        />
        <Tooltip
          formatter={(value) => [`${value} / 100`, 'Domain score']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={18}>
          {data.map((d) => (
            <Cell key={d.name} fill={d.score >= 60 ? '#dc2626' : d.score >= 40 ? '#d97706' : '#16a34a'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** AAL by scenario — horizontal bars, sorted descending. */
export function AalByScenarioChart({ aal }: { aal: Record<string, number> }) {
  const data = Object.entries(aal)
    .map(([key, value]) => ({ name: key.replace(/_/g, ' '), aal: value }))
    .sort((a, b) => b.aal - a.aal);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 12, fill: '#64748b' }} tickFormatter={(v) => `$${(v / 1e6).toFixed(1)}M`} />
        <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12, fill: '#334155' }} />
        <Tooltip
          formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Annual average loss']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <Bar dataKey="aal" fill="#2563eb" radius={[0, 4, 4, 0]} barSize={18} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Scenario contribution share of EAL — pie/stacked view. */
export function ScenarioContributionChart({ contribution }: { contribution: Record<string, number> }) {
  const COLORS = ['#2563eb', '#3b82f6', '#60a5fa', '#0ea5e9', '#f59e0b', '#10b981', '#8b5cf6'];
  const data = Object.entries(contribution)
    .map(([key, value], i) => ({
      name: key.replace(/_/g, ' '),
      value: value,
      fill: COLORS[i % COLORS.length],
    }))
    .sort((a, b) => b.value - a.value);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} interval={0} angle={-30} textAnchor="end" height={60} />
        <YAxis tick={{ fontSize: 12, fill: '#64748b' }} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
        <Tooltip
          formatter={(value) => [`${(Number(value) * 100).toFixed(1)}%`, 'Share of EAL']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={34}>
          {data.map((d) => (
            <Cell key={d.name} fill={d.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Loss distribution quantiles (p50..p99.9) — the model's annual loss curve. */
export function LossDistributionChart({ quantiles }: { quantiles: Record<string, number> }) {
  const data = Object.entries(quantiles).map(([key, value]) => ({
    name: key.toUpperCase(),
    loss: value,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#64748b' }} />
        <YAxis tick={{ fontSize: 12, fill: '#64748b' }} tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} />
        <Tooltip
          formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Annual loss']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <Bar dataKey="loss" radius={[4, 4, 0, 0]} barSize={42}>
          {data.map((_, i) => (
            <Cell key={i} fill={i >= 3 ? '#dc2626' : i >= 1 ? '#d97706' : '#2563eb'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Loss exceedance curve — P(loss >= X) from the engine's simulated sample. */
export function LossExceedanceChart({ points }: { points: Array<{ loss: number; prob: number }> }) {
  const data = [...points].sort((a, b) => a.loss - b.loss);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 8, right: 16, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="loss"
          type="number"
          scale="log"
          domain={['dataMin', 'dataMax']}
          tickFormatter={(v) => `$${Number(v) >= 1e6 ? `${(v / 1e6).toFixed(0)}M` : `${(v / 1e3).toFixed(0)}K`}`}
          tick={{ fontSize: 11, fill: '#64748b' }}
        />
        <YAxis
          type="number"
          domain={[0, 1]}
          tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
          tick={{ fontSize: 12, fill: '#64748b' }}
        />
        <Tooltip
          formatter={(value, name) => [
            name === 'prob' ? `${(Number(value) * 100).toFixed(2)}%` : `$${Number(value).toLocaleString()}`,
            name === 'prob' ? 'P(loss ≥)' : 'Loss level',
          ]}
          labelFormatter={(v) => `Loss: $${Number(v).toLocaleString()}`}
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <ReferenceLine
          y={0.01}
          stroke="#dc2626"
          strokeDasharray="4 4"
          label={{ value: '1-in-100', position: 'insideBottomRight', fontSize: 11, fill: '#dc2626' }}
        />
        <Line
          type="monotone"
          dataKey="prob"
          stroke="#2563eb"
          strokeWidth={2.5}
          dot={{ r: 3, fill: '#2563eb', strokeWidth: 0 }}
          activeDot={{ r: 5 }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Insurance waterfall — ground-up → retained → transferred → residual, all backend data. */
export function InsuranceWaterfallChart({
  groundUp,
  retention,
  insurerPayment,
  residual,
}: {
  groundUp: number;
  retention: number;
  insurerPayment: number;
  residual: number;
}) {
  // Waterfall via a hidden "base" series + visible bars.  Each step positions
  // the visible bar above the running total from the previous step.
  const steps: Array<{ name: string; base: number; value: number; fill: string }> = [
    { name: 'Ground-up EAL', base: 0, value: groundUp, fill: '#1e293b' },
    { name: 'Retention', base: groundUp - retention, value: retention, fill: '#dc2626' },
    { name: 'Insurer payment', base: groundUp - retention - insurerPayment, value: insurerPayment, fill: '#2563eb' },
    { name: 'Residual', base: 0, value: residual, fill: '#f59e0b' },
  ];

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={steps} margin={{ top: 8, right: 16, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} interval={0} angle={-14} textAnchor="end" height={56} />
        <YAxis tick={{ fontSize: 12, fill: '#64748b' }} tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} />
        <Tooltip
          formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Amount']}
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="base" stackId="wf" fill="transparent" tooltipType="none" legendType="none" />
        <Bar dataKey="value" stackId="wf" radius={[4, 4, 0, 0]} barSize={44}>
          {steps.map((s) => (
            <Cell key={s.name} fill={s.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
export function BeforeAfterChart({
  before,
  after,
}: {
  before: { eal: number; var_99: number; es_99: number };
  after: { eal: number; var_99: number; es_99: number };
}) {
  const data = [
    { name: 'EAL', 'Current state': before.eal, 'After control': after.eal },
    { name: 'VaR 99', 'Current state': before.var_99, 'After control': after.var_99 },
    { name: 'ES 99', 'Current state': before.es_99, 'After control': after.es_99 },
  ];

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#64748b' }} />
        <YAxis tick={{ fontSize: 12, fill: '#64748b' }} tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} />
        <Tooltip
          formatter={(value, name) => [`$${Number(value).toLocaleString()}`, name]}
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="Current state" fill="#94a3b8" radius={[4, 4, 0, 0]} barSize={26} />
        <Bar dataKey="After control" fill="#2563eb" radius={[4, 4, 0, 0]} barSize={26} />
      </BarChart>
    </ResponsiveContainer>
  );
}
