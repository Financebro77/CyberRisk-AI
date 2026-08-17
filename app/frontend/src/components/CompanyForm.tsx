import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Eraser, FlaskConical, Loader2, Play } from 'lucide-react';
import { randomizeDemoCompany } from '../lib/demoRandom';
import type { CompanyBrief, PolicyInput } from '../lib/types';

interface CompanyFormProps {
  /** Extra controls rendered under the brief fields (policy terms, control change, etc.). */
  children?: React.ReactNode;
  /** Button label, defaults to "Run Model". */
  submitLabel?: string;
  onSubmit: (brief: CompanyBrief & PolicyInput) => void | Promise<unknown>;
  /** Fired with the current assembled brief whenever any field/knob changes —
   *  the parent debounces this into an auto re-run (live score refresh). */
  onChange?: (brief: CompanyBrief & PolicyInput) => void;
  loading?: boolean;
  initial?: CompanyBrief;
}

/** Imperative API so Demo Mode can populate + run the form from outside. */
export interface CompanyFormHandle {
  /** Fill every field from a brief, then optionally submit. */
  loadCompany: (brief: CompanyBrief, opts?: { submit?: boolean }) => void;
  clearForm: () => void;
}

/*
 * Structured form that maps a richer client-profile survey onto the backend's
 * 8 CompanyBrief fields.
 *
 * The backend consumes `security_controls` as free text and parses it with a
 * clause-aware keyword scanner (see src/cyberrisk/agent/tools.py
 * `_scan_security_controls`).  Each requested field below therefore becomes a
 * select whose option maps to a clause the parser recognises, e.g.:
 *
 *     MFA coverage = "Comprehensive"  ->  "MFA is comprehensive"
 *
 * and the clauses are joined with the parser's clause separators so one
 * control never downgrades another.  Everything else maps 1:1 to a real
 * CompanyBrief field (industry, revenue, customer_records,
 * technology_dependency, existing_coverage, risk_appetite).
 */

/* ----------------------- option catalogs ----------------------- */

type IndustryOption = string;
const INDUSTRIES: IndustryOption[] = [
  'Healthcare',
  'Financial Services',
  'Insurance',
  'Technology',
  'Retail',
  'Manufacturing',
  'Professional Services',
  'Energy',
  'Government',
  'Telecommunications',
];

type ControlLevel = string;
const MFA_OPTIONS: ControlLevel[] = ['None', 'Minimal', 'Partial', 'Comprehensive'];
const PAM_OPTIONS: ControlLevel[] = ['None', 'Basic', 'Defined', 'Segmented'];
const NETWORK_OPTIONS: ControlLevel[] = ['None', 'Weak', 'Basic', 'Segmented'];
const BACKUP_OPTIONS: ControlLevel[] = ['None', 'Monthly', 'Daily', 'Continuous'];
const VULN_OPTIONS: ControlLevel[] = ['None', 'Ad-hoc', 'Monthly', 'Continuous'];
const INCIDENT_OPTIONS: ControlLevel[] = ['None', 'Ad-hoc', 'Documented', 'Tested'];

const DEPENDENCY_OPTIONS = ['Low', 'Moderate', 'High'];

/* ------------------- backend field constants ------------------- */

const FIELD_LABELS: Record<keyof CompanyBrief, string> = {
  firm_name: 'Company name',
  industry: 'Industry',
  revenue_usd: 'Revenue (USD)',
  customer_records: 'Customer records',
  technology_dependency: 'Technology dependency',
  security_controls: 'Security controls',
  previous_incidents: 'Previous incidents',
  existing_coverage: 'Existing coverage',
  risk_appetite: 'Risk appetite',
  country: 'Country',
  employees: 'Employees',
  sensitive_records: 'Sensitive records',
  cloud_dependency: 'Cloud dependency',
  third_party_dependency: 'Third-party dependency',
  mfa_coverage: 'MFA coverage',
  pam: 'Privileged access management',
  network_segmentation: 'Network segmentation',
  backup_strategy: 'Backup strategy',
  vulnerability_management: 'Vulnerability management',
  incident_response: 'Incident response',
  policy_limit: 'Policy limit',
  retention: 'Retention',
};

/* ---------------- requested-field -> clause builder ------------ */

/**
 * The free-text controls description assembled from the structured selects.
 * Each clause is qualified by its own option value so the parser's
 * clause-local qualifier resolves correctly (strong / weak / none / neutral).
 */
function buildSecurityControls(c: {
  mfa_coverage?: string;
  pam?: string;
  network_segmentation?: string;
  backup_strategy?: string;
  vulnerability_management?: string;
  incident_response?: string;
}): string {
  const clauses: string[] = [];
  if (c.mfa_coverage) clauses.push(`MFA is ${c.mfa_coverage.toLowerCase()}`);
  if (c.network_segmentation) clauses.push(`network segmentation is ${c.network_segmentation.toLowerCase()}`);
  if (c.pam) clauses.push(`privileged access management is ${c.pam.toLowerCase()}`);
  if (c.vulnerability_management) clauses.push(`vulnerability management is ${c.vulnerability_management.toLowerCase()}`);
  if (c.backup_strategy) clauses.push(`backups are ${c.backup_strategy.toLowerCase()}`);
  if (c.incident_response) clauses.push(`incident response is ${c.incident_response.toLowerCase()}`);
  return clauses.join(', ');
}

/**
 * Assemble the full submission brief (values + policy knobs + assembled
 * controls text) exactly as it will be sent to the engine.  Pure function so
 * the manual submit and the live `onChange` fire the identical payload shape.
 */
function buildBrief(values: Record<string, string>, controlsText: string): CompanyBrief & PolicyInput {
  const brief: CompanyBrief & PolicyInput = {
    firm_name: values.firm_name || undefined,
    industry: values.industry || undefined,
    technology_dependency: values.technology_dependency || undefined,
    existing_coverage: values.existing_coverage || undefined,
    risk_appetite: values.risk_appetite || undefined,
    // Raw structured extras (sent as hints; the API drops unknown fields)
    country: values.country || undefined,
    sensitive_records: values.sensitive_records || undefined,
    cloud_dependency: values.cloud_dependency || undefined,
    third_party_dependency: values.third_party_dependency || undefined,
    mfa_coverage: values.mfa_coverage || undefined,
    pam: values.pam || undefined,
    network_segmentation: values.network_segmentation || undefined,
    backup_strategy: values.backup_strategy || undefined,
    vulnerability_management: values.vulnerability_management || undefined,
    incident_response: values.incident_response || undefined,
  };
  // security_controls assembled from the structured controls selects, or the
  // manual override if the user typed their own description.
  brief.security_controls = controlsText || buildSecurityControls(values) || undefined;
  if (values.revenue_usd !== '') brief.revenue_usd = Number(values.revenue_usd);
  if (values.customer_records !== '') brief.customer_records = Number(values.customer_records);
  if (values.employees !== '') brief.employees = Number(values.employees);
  brief.previous_incidents = values.previous_incidents === '' ? 0 : Number(values.previous_incidents);
  // The insurance knobs the engine honors: retention = per-occurrence
  // deductible, policy limit = annual aggregate limit (see /api/report/executive).
  if (values.retention !== '') brief.per_occurrence_deductible = Number(values.retention);
  if (values.policy_limit !== '') brief.annual_aggregate_limit = Number(values.policy_limit);
  return brief;
}

/* Demo Mode loads a fresh random company every press (see lib/demoRandom). */

/* ------------------------ select configs ----------------------- */

interface SelectConfig {
  key: keyof CompanyBrief;
  label: string;
  options: string[];
  placeholder: string;
}

const COMPANY_SELECTS: SelectConfig[] = [
  { key: 'industry', label: 'Industry', options: INDUSTRIES, placeholder: 'Select industry' },
  { key: 'technology_dependency', label: 'Technology dependency', options: DEPENDENCY_OPTIONS, placeholder: 'Select level' },
];

const CONTROL_SELECTS: SelectConfig[] = [
  { key: 'mfa_coverage', label: 'MFA coverage', options: MFA_OPTIONS, placeholder: 'Select coverage' },
  { key: 'pam', label: 'Privileged access management', options: PAM_OPTIONS, placeholder: 'Select level' },
  { key: 'network_segmentation', label: 'Network segmentation', options: NETWORK_OPTIONS, placeholder: 'Select level' },
  { key: 'backup_strategy', label: 'Backup strategy', options: BACKUP_OPTIONS, placeholder: 'Select frequency' },
  { key: 'vulnerability_management', label: 'Vulnerability management', options: VULN_OPTIONS, placeholder: 'Select cadence' },
  { key: 'incident_response', label: 'Incident response', options: INCIDENT_OPTIONS, placeholder: 'Select maturity' },
];

const NUMBER_FIELDS: Array<keyof CompanyBrief> = ['revenue_usd', 'customer_records', 'employees', 'previous_incidents', 'policy_limit', 'retention'];

const NUM_DEFAULTS: Partial<Record<keyof CompanyBrief, number>> = {
  previous_incidents: 0,
};

/* ------------------------- helpers ---------------------------- */

const emptyForm = () => {
  const base: Record<string, string> = {};
  for (const k of ['firm_name', 'industry', 'technology_dependency', 'existing_coverage', 'risk_appetite', 'country', 'sensitive_records', 'cloud_dependency', 'third_party_dependency']) base[k] = '';
  for (const k of CONTROL_SELECTS) base[k.key] = '';
  for (const k of NUMBER_FIELDS) base[k] = '';
  base.previous_incidents = '0';
  return base;
};

function initialValues(initial?: CompanyBrief): Record<string, string> {
  const base = emptyForm();
  if (!initial) return base;
  // Company brief values
  for (const k of ['firm_name', 'industry', 'technology_dependency', 'existing_coverage', 'risk_appetite', 'country', 'sensitive_records', 'cloud_dependency', 'third_party_dependency'] as const) {
    base[k] = (initial[k] as string | undefined) ?? '';
  }
  // Control selects from the brief's structured extras
  for (const cfg of CONTROL_SELECTS) {
    const v = (initial[cfg.key] as string | undefined) ?? '';
    if (v) base[cfg.key] = v;
  }
  // Numbers
  for (const k of NUMBER_FIELDS) {
    const v = initial[k] as number | undefined;
    base[k] = v === undefined || v === null ? (NUM_DEFAULTS[k] !== undefined ? String(NUM_DEFAULTS[k]) : '') : String(v);
  }
  return base;
}

/* ------------------------ component --------------------------- */

export const CompanyForm = forwardRef<CompanyFormHandle, CompanyFormProps>(function CompanyForm(
  { children, submitLabel = 'Run Model', onSubmit, onChange, loading, initial },
  ref,
) {
  const [values, setValues] = useState<Record<string, string>>(() => initialValues(initial));
  /** Optional manual override for the assembled controls text. */
  const [controlsText, setControlsText] = useState(initial?.security_controls ?? '');

  /** The assembled controls description, derived live from the selects. */
  const assembledControls = useMemo(() => buildSecurityControls(values), [values]);

  // Keep a ref to onChange so every mutator (including the deps-[] imperative
  // handle) fires the latest callback without re-creating anything per render.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  /** Live-refresh signal: emits the current assembled brief after a change. */
  const emitChange = (next: Record<string, string>, controls: string) => {
    onChangeRef.current?.(buildBrief(next, controls));
  };

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const next = { ...values, [k]: e.target.value };
    setValues(next);
    emitChange(next, controlsText);
  };

  const setControl = (cfg: SelectConfig) => (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = { ...values, [cfg.key]: e.target.value };
    setValues(next);
    setControlsText('');
    emitChange(next, '');
  };

  const loadDemo = () => {
    // A fresh random company each press (see lib/demoRandom.ts).
    const next = initialValues(randomizeDemoCompany().brief);
    setValues(next);
    setControlsText('');
    emitChange(next, '');
  };

  const clearForm = () => {
    const next = emptyForm();
    setValues(next);
    setControlsText('');
    emitChange(next, '');
  };

  const canSubmit = useMemo(() => {
    const hasRevenue = values.revenue_usd !== '' && Number(values.revenue_usd) > 0;
    const hasControls = assembledControls.trim().length > 0 || controlsText.trim().length > 0;
    return hasRevenue && hasControls;
  }, [values, assembledControls, controlsText]);

  const submit = () => {
    void onSubmit(buildBrief(values, controlsText));
  };

  // Keep a ref to submit so useImperativeHandle always calls the latest
  // version without re-creating the handle on every keystroke.
  const submitRef = useRef<() => void>(submit);
  submitRef.current = submit;

  /** External API for Demo Mode: fill the form (and optionally run). */
  useImperativeHandle(
    ref,
    () => ({
      loadCompany: (brief, opts) => {
        const next = initialValues(brief);
        setValues(next);
        setControlsText('');
        emitChange(next, '');
        if (opts?.submit) {
          // Defer so the state lands before we read the assembled controls.
          requestAnimationFrame(() => submitRef.current());
        }
      },
      clearForm,
    }),
    [],
  );

  return (
    <div className="card p-6">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-base font-semibold text-ink-900">Client profile</h3>
      </div>
      <p className="mb-5 text-sm text-ink-500">
        Revenue and a security-controls description are required to run the loss model.
      </p>

      {/* Company profile section */}
      <div className="mb-6">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Company profile</div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* firm_name */}
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-600">Company name</span>
            <input
              type="text"
              value={values.firm_name}
              onChange={set('firm_name')}
              placeholder="e.g. Meridian Logistics"
              className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            />
          </label>

          {/* industry + technology dependency selects */}
          {COMPANY_SELECTS.map((cfg) => (
            <label key={cfg.key} className="block">
              <span className="mb-1 block text-xs font-medium text-ink-600">{cfg.label}</span>
              <select
                value={values[cfg.key]}
                onChange={set(cfg.key)}
                className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
              >
                <option value="">{cfg.placeholder}</option>
                {cfg.options.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </label>
          ))}

          {/* country */}
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-600">Country</span>
            <input
              type="text"
              value={values.country}
              onChange={set('country')}
              placeholder="e.g. United States"
              className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            />
          </label>

          {/* numbers */}
          {['revenue_usd', 'customer_records', 'employees'].map((k) => (
            <label key={k} className="block">
              <span className="mb-1 block text-xs font-medium text-ink-600">{FIELD_LABELS[k as keyof CompanyBrief]}</span>
              <input
                type="number"
                min={0}
                value={values[k]}
                onChange={set(k)}
                placeholder={k === 'revenue_usd' ? 'e.g. 250000000' : ''}
                className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
              />
            </label>
          ))}

          {/* sensitive records + dependencies (selects) */}
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-600">Sensitive records</span>
            <select
              value={values.sensitive_records}
              onChange={set('sensitive_records')}
              className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            >
              <option value="">Select type</option>
              <option>Finance &amp; HR data</option>
              <option>Customer PII</option>
              <option>Payment card data</option>
              <option>Health / medical records</option>
              <option>Intellectual property</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-600">Cloud dependency</span>
            <select
              value={values.cloud_dependency}
              onChange={set('cloud_dependency')}
              className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            >
              <option value="">Select level</option>
              {DEPENDENCY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-600">Third-party dependency</span>
            <select
              value={values.third_party_dependency}
              onChange={set('third_party_dependency')}
              className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            >
              <option value="">Select level</option>
              {DEPENDENCY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
        </div>
      </div>

      {/* Security controls section */}
      <div className="mb-6">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Security controls</div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {CONTROL_SELECTS.map((cfg) => (
            <label key={cfg.key} className="block">
              <span className="mb-1 block text-xs font-medium text-ink-600">{cfg.label}</span>
              <select
                value={values[cfg.key]}
                onChange={setControl(cfg)}
                className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
              >
                <option value="">{cfg.placeholder}</option>
                {cfg.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </label>
          ))}
        </div>

        {/* Read-only assembled controls text (what the backend parses) */}
        <div className="mt-4">
          <span className="mb-1 block text-xs font-medium text-ink-600">Assembled security controls (sent to model)</span>
          <div className="flex items-center gap-2">
            <input
              type="text"
              readOnly
              value={controlsText || assembledControls}
              placeholder="e.g. MFA is comprehensive, network segmentation is strong"
              className="field border-dashed font-mono text-xs text-ink-700"
            />
            <button
              type="button"
              onClick={() => setControlsText(assembledControls)}
              className="shrink-0 rounded-lg border border-ink-300 px-3 py-2 text-xs font-medium text-ink-600 transition-colors hover:border-brand-500 hover:text-accent"
              title="Reassemble from the selects above"
            >
              Sync
            </button>
          </div>
          <p className="mt-1 text-[11px] text-ink-400">
            Selects above are assembled into this clause-safe description, which the engine parses per control.
          </p>
        </div>
      </div>

      {/* Insurance section */}
      <div className="mb-6">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-400">Insurance</div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-600">Policy limit</span>
            <input
              type="number"
              min={0}
              value={values.policy_limit}
              onChange={set('policy_limit')}
              placeholder="e.g. 10000000"
              className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-600">Retention</span>
            <input
              type="number"
              min={0}
              value={values.retention}
              onChange={set('retention')}
              placeholder="e.g. 250000"
              className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-600">Previous incidents</span>
            <input
              type="number"
              min={0}
              value={values.previous_incidents}
              onChange={set('previous_incidents')}
              className="field focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            />
          </label>
        </div>
      </div>

      {children}

      {/* Action bar */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={loadDemo}
            className="inline-flex items-center gap-2 rounded-lg border border-ink-300 px-4 py-2 text-sm font-medium text-ink-600 transition-colors hover:border-brand-500 hover:text-accent"
          >
            <FlaskConical className="h-4 w-4" />
            Load Demo Company
          </button>
          <button
            type="button"
            onClick={clearForm}
            className="inline-flex items-center gap-2 rounded-lg border border-ink-300 px-4 py-2 text-sm font-medium text-ink-600 transition-colors hover:border-ink-500 hover:text-ink-900"
          >
            <Eraser className="h-4 w-4" />
            Clear Form
          </button>
        </div>
        <div className="flex items-center gap-3">
          {!canSubmit && (
            <p className="text-xs text-ink-500">Add revenue and security controls to enable the model.</p>
          )}
          <button
            type="button"
            onClick={submit}
            disabled={loading || !canSubmit}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {loading ? 'Running…' : submitLabel}
          </button>
        </div>
      </div>
    </div>
  );
});
