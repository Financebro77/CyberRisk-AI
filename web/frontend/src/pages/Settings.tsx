import { useState } from 'react';
import { SectionCard } from '../components/SectionCard';
import { useTheme } from '../lib/useTheme';
import { Check, Moon, Sun, Bell, Database, UserRound } from 'lucide-react';

export default function Settings() {
  const { theme, toggleTheme } = useTheme();

  const [simYears, setSimYears] = useState(100_000);
  const [notifySim, setNotifySim] = useState(true);
  const [notifyReport, setNotifyReport] = useState(true);
  const [notifyIns, setNotifyIns] = useState(false);
  const [saved, setSaved] = useState(false);

  const save = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-ink-900">Settings</h2>
        <p className="mt-1 text-sm text-ink-500">
          Preferences for the CyberRisk AI consulting workspace.
        </p>
      </div>

      {/* Appearance */}
      <SectionCard title="Appearance" subtitle="Theme preference for this workspace">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => theme !== 'light' && toggleTheme()}
            className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors ${
              theme === 'light'
                ? 'border-brand-500 bg-brand-50 text-brand-700 ring-1 ring-brand-500'
                : 'border-ink-200 text-ink-600 hover:border-ink-300'
            }`}
          >
            <Sun className="h-4 w-4" /> Light
            {theme === 'light' && <Check className="h-3.5 w-3.5 text-brand-600" />}
          </button>
          <button
            type="button"
            onClick={() => theme !== 'dark' && toggleTheme()}
            className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors ${
              theme === 'dark'
                ? 'border-brand-500 bg-brand-50 text-brand-700 ring-1 ring-brand-500'
                : 'border-ink-200 text-ink-600 hover:border-ink-300'
            }`}
          >
            <Moon className="h-4 w-4" /> Dark
            {theme === 'dark' && <Check className="h-3.5 w-3.5 text-brand-600" />}
          </button>
        </div>
      </SectionCard>

      {/* Model */}
      <SectionCard title="Model & simulation" subtitle="Defaults for loss modelling runs">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-ink-600">Monte Carlo simulation years</span>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={10_000}
              max={200_000}
              step={10_000}
              value={simYears}
              onChange={(e) => setSimYears(Number(e.target.value))}
              className="w-full max-w-sm accent-brand-600"
            />
            <span className="w-16 font-mono text-sm text-ink-900">{simYears.toLocaleString()}</span>
          </div>
        </label>
        <p className="mt-2 text-xs text-ink-500">
          Higher values improve tail precision but take longer. The engine caches runs, so
          re-evaluating a structure is fast.
        </p>
      </SectionCard>

      {/* Notifications */}
      <SectionCard title="Notifications" subtitle="Choose what to be notified about">
        <div className="space-y-3">
          <ToggleRow
            icon={<Bell className="h-4 w-4 text-ink-400" />}
            label="Simulation complete"
            desc="Notify when a Monte Carlo run finishes"
            checked={notifySim}
            onChange={setNotifySim}
          />
          <ToggleRow
            icon={<Database className="h-4 w-4 text-ink-400" />}
            label="Report generated"
            desc="Notify when an executive report is ready"
            checked={notifyReport}
            onChange={setNotifyReport}
          />
          <ToggleRow
            icon={<UserRound className="h-4 w-4 text-ink-400" />}
            label="Insurance recommendation"
            desc="Notify when a new structure is recommended"
            checked={notifyIns}
            onChange={setNotifyIns}
          />
        </div>
      </SectionCard>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-500"
        >
          Save preferences
        </button>
        {saved && (
          <span className="inline-flex items-center gap-1.5 text-sm text-emerald-600">
            <Check className="h-4 w-4" /> Saved
          </span>
        )}
      </div>
    </div>
  );
}

function ToggleRow({
  icon,
  label,
  desc,
  checked,
  onChange,
}: {
  icon: React.ReactNode;
  label: string;
  desc: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        {icon}
        <div>
          <div className="text-sm font-medium text-ink-800">{label}</div>
          <div className="text-xs text-ink-500">{desc}</div>
        </div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${checked ? 'bg-brand-600' : 'bg-ink-200'}`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${checked ? 'left-[22px]' : 'left-0.5'}`}
        />
      </button>
    </div>
  );
}
