/**
 * Live-refresh contract for the assess tab (Feature 2): tweaking any form
 * knob re-runs the executive report automatically, debounced, in place.
 *
 * The `api` module is mocked so no backend is touched.  Fake timers drive the
 * 600ms quiet window.  Contract under test:
 *
 *   - no auto-run on mount,
 *   - a knob change fires exactly one run after the window, with the new knob,
 *   - rapid knob changes coalesce into a single run (latest payload),
 *   - a manual submit cancels a pending auto-run,
 *   - a "Refreshing…" badge appears while a background re-run is in flight and
 *     the stale report stays visible (stale-while-revalidate),
 *   - an INCOMPLETE brief (revenue cleared) fires no auto-run and keeps the
 *     last good report rendered,
 *   - the insurance cards show the exact dollar figure (formatMoneyFull), so a
 *     +1000 retention tweak is visible on screen.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { api } from '../../lib/api';
import ConsultantPortal from '../ConsultantPortal';
import type { ExecutiveReportResponse } from '../../lib/types';

vi.mock('../../lib/api', () => ({
  api: {
    executiveReport: vi.fn(),
  },
}));

const executiveReport = api.executiveReport as unknown as ReturnType<typeof vi.fn>;

/** Minimal render-safe executive report (see AdvisoryReport consumers). */
const REPORT: ExecutiveReportResponse = {
  status: 'ok',
  firm_name: 'Test Co',
  executive_summary: { risk_score: 55, risk_category: 'Medium', sentence: 'Test summary.' },
  risk_rating: {
    score: 55,
    category: 'Medium',
    domain_scores: {},
    risk_drivers: ['weak_mfa'],
  },
  financial_exposure: {
    eal: 1_000_000,
    var_95: 2_000_000,
    var_99: 3_000_000,
    es_99: 4_000_000,
    pml_1in200: 5_000_000,
    pml_1in1000: 6_000_000,
    loss_distribution: { p50: 0, p90: 0, p95: 0, p99: 0, p99_9: 0 },
    prob_zero_loss: 0.1,
  },
  insurance_analysis: {
    ground_up_loss: {
      eal: 1_000_000,
      var_95: 2_000_000,
      var_99: 3_000_000,
      es_95: 3_500_000,
      es_99: 4_000_000,
      pml_1in1000: 6_000_000,
    },
    insurance_response: {
      policy_limit: 5_000_000,
      retention: 1_000_000,
      covered_loss: 0,
      insurer_payment: 0,
      p_annual_limit_exhausted: 0.01,
    },
    client_retained_loss: {
      retained_eal: 800_000,
      retained_es_99: 3_500_000,
      gross_loss_at_p99_9: 6_000_000,
      insurance_recovery_at_p99_9: 2_000_000,
      residual_exposure_at_p99_9: 4_000_000,
    },
    evaluation: { residual_uncovered: true, summary: 'Test insurance evaluation.' },
  },
  mitigation_roadmap: [],
  scenario_contributions: {},
  model_limitations: { heading: 'Model limitations', limitations: ['Test limitation.'] },
};

/** Advance fake timers inside act so any run() triggered is flushed by React. */
const advance = (ms: number) => act(() => vi.advanceTimersByTime(ms));

/** Flush the run() promise's microtasks (setData/setLoading). */
const flush = () => act(async () => {});

/** A complete brief passes the auto-run completeness gate: revenue + controls. */
async function seedComplete() {
  fireEvent.change(screen.getByLabelText(/revenue/i), { target: { value: '250000000' } });
  fireEvent.change(screen.getByLabelText(/mfa coverage/i), { target: { value: 'Comprehensive' } });
  advance(600);
  await flush();
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('AssessmentTab live refresh (debounced auto re-run)', () => {
  it('does not run the model on mount', () => {
    vi.useFakeTimers();
    render(
      <MemoryRouter>
        <ConsultantPortal />
      </MemoryRouter>,
    );
    expect(executiveReport).not.toHaveBeenCalled();
  });

  it('auto-runs exactly once with the new retention after the debounce window', async () => {
    vi.useFakeTimers();
    executiveReport.mockResolvedValue(REPORT);
    render(
      <MemoryRouter>
        <ConsultantPortal />
      </MemoryRouter>,
    );
    await seedComplete();
    executiveReport.mockClear();
    fireEvent.change(screen.getByLabelText(/retention/i), { target: { value: '1500000' } });
    // Inside the quiet window nothing fires yet.
    advance(500);
    expect(executiveReport).not.toHaveBeenCalled();
    // Window elapses: one run carrying the new retention.
    advance(100);
    await flush();
    expect(executiveReport).toHaveBeenCalledTimes(1);
    expect(executiveReport.mock.calls[0][0].per_occurrence_deductible).toBe(1_500_000);
  });

  it('coalesces rapid knob changes into a single run with the latest payload', async () => {
    vi.useFakeTimers();
    executiveReport.mockResolvedValue(REPORT);
    render(
      <MemoryRouter>
        <ConsultantPortal />
      </MemoryRouter>,
    );
    await seedComplete();
    executiveReport.mockClear();
    fireEvent.change(screen.getByLabelText(/retention/i), { target: { value: '1000000' } });
    fireEvent.change(screen.getByLabelText(/policy limit/i), { target: { value: '40000000' } });
    advance(600);
    await flush();
    expect(executiveReport).toHaveBeenCalledTimes(1);
    const brief = executiveReport.mock.calls[0][0];
    expect(brief.per_occurrence_deductible).toBe(1_000_000);
    expect(brief.annual_aggregate_limit).toBe(40_000_000);
  });

  it('a manual submit cancels a pending auto-run', async () => {
    vi.useFakeTimers();
    executiveReport.mockResolvedValue(REPORT);
    render(
      <MemoryRouter>
        <ConsultantPortal />
      </MemoryRouter>,
    );
    await seedComplete();
    executiveReport.mockClear();
    fireEvent.change(screen.getByLabelText(/retention/i), { target: { value: '900000' } });
    fireEvent.click(screen.getByRole('button', { name: /submit assessment/i }));
    // Advance well past the window: the debounced run must NOT also fire.
    advance(600);
    await flush();
    expect(executiveReport).toHaveBeenCalledTimes(1);
  });

  it('shows a Refreshing… badge while a background re-run is in flight', async () => {
    vi.useFakeTimers();
    executiveReport.mockResolvedValue(REPORT);
    render(
      <MemoryRouter>
        <ConsultantPortal />
      </MemoryRouter>,
    );
    // Seed a first report so stale data is on screen.
    await seedComplete();
    expect(screen.queryByText(/refreshing/i)).toBeNull();
    // Tweak a knob: background re-run starts, badge appears, stale data stays.
    fireEvent.change(screen.getByLabelText(/retention/i), { target: { value: '900000' } });
    advance(600);
    expect(screen.getByText(/refreshing/i)).toBeTruthy();
    await flush();
    expect(screen.queryByText(/refreshing/i)).toBeNull();
  });

  it('an incomplete brief fires no auto-run and keeps the last report', async () => {
    vi.useFakeTimers();
    executiveReport.mockResolvedValue(REPORT);
    render(
      <MemoryRouter>
        <ConsultantPortal />
      </MemoryRouter>,
    );
    await seedComplete();
    expect(screen.getByText('Test summary.')).toBeTruthy();
    executiveReport.mockClear();
    // Clear revenue mid-edit: the brief is incomplete, no run may fire, and
    // the previous report must stay on screen (never silently blanked).
    fireEvent.change(screen.getByLabelText(/revenue/i), { target: { value: '' } });
    advance(600);
    await flush();
    expect(executiveReport).not.toHaveBeenCalled();
    expect(screen.getByText('Test summary.')).toBeTruthy();
  });

  it('insurance card shows the exact retention figure after a +1000 change', async () => {
    vi.useFakeTimers();
    executiveReport.mockResolvedValue(REPORT);
    render(
      <MemoryRouter>
        <ConsultantPortal />
      </MemoryRouter>,
    );
    await seedComplete();
    // REPORT has retention 1_000_000 — full precision, not "$1M".
    expect(screen.getByText('$1,000,000')).toBeTruthy();
    // Retention +1000 → the card must show $1,001,000.
    const raised: ExecutiveReportResponse = {
      ...REPORT,
      insurance_analysis: {
        ...REPORT.insurance_analysis,
        insurance_response: {
          ...REPORT.insurance_analysis.insurance_response,
          retention: 1_001_000,
        },
      },
    };
    executiveReport.mockResolvedValue(raised);
    fireEvent.change(screen.getByLabelText(/retention/i), { target: { value: '1001000' } });
    advance(600);
    await flush();
    expect(screen.getByText('$1,001,000')).toBeTruthy();
    expect(screen.queryByText('$1,000,000')).toBeNull();
  });
});
