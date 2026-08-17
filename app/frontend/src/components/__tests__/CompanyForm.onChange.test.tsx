import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { CompanyForm } from '../CompanyForm';

afterEach(cleanup);

/**
 * Live-refresh contract: every form mutator fires `onChange` with the CURRENT
 * assembled brief (values + controls + policy knobs), so the parent can
 * debounce an auto re-run.  Not fired on mount; always reflects the change
 * that just happened.
 */
describe('CompanyForm onChange (live refresh)', () => {
  it('does not fire onChange on initial mount', () => {
    const onChange = vi.fn();
    render(<CompanyForm onSubmit={() => {}} onChange={onChange} />);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('fires onChange with the new retention when the retention knob changes', () => {
    const onChange = vi.fn();
    render(<CompanyForm onSubmit={() => {}} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/retention/i), { target: { value: '1500000' } });
    expect(onChange).toHaveBeenCalledTimes(1);
    const brief = onChange.mock.calls[0][0];
    expect(brief.per_occurrence_deductible).toBe(1500000);
  });

  it('fires onChange with the new policy limit when the limit knob changes', () => {
    const onChange = vi.fn();
    render(<CompanyForm onSubmit={() => {}} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/policy limit/i), { target: { value: '40000000' } });
    const brief = onChange.mock.calls[0][0];
    expect(brief.annual_aggregate_limit).toBe(40000000);
  });

  it('assembles the security-controls text from the selected controls', () => {
    const onChange = vi.fn();
    render(<CompanyForm onSubmit={() => {}} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/mfa coverage/i), { target: { value: 'Comprehensive' } });
    const brief = onChange.mock.calls[0][0];
    expect(brief.security_controls).toContain('MFA is comprehensive');
  });

  it('fires onChange after loading a demo company with a complete brief', () => {
    const onChange = vi.fn();
    render(<CompanyForm onSubmit={() => {}} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /load demo/i }));
    expect(onChange).toHaveBeenCalled();
    const brief = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(brief.revenue_usd).toBeGreaterThan(0);
    expect(brief.security_controls).toBeTruthy();
  });

  it('fires onChange after clearing the form (incomplete brief)', () => {
    const onChange = vi.fn();
    render(<CompanyForm onSubmit={() => {}} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /load demo/i }));
    fireEvent.click(screen.getByRole('button', { name: /clear form/i }));
    const brief = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(brief.revenue_usd).toBeUndefined();
  });

  it('submits the same brief shape via onSubmit', () => {
    const onSubmit = vi.fn();
    render(<CompanyForm submitLabel="Go" onSubmit={onSubmit} />);
    fireEvent.change(screen.getByLabelText(/revenue/i), { target: { value: '500000000' } });
    fireEvent.change(screen.getByLabelText(/mfa coverage/i), { target: { value: 'Comprehensive' } });
    fireEvent.change(screen.getByLabelText(/retention/i), { target: { value: '1000000' } });
    fireEvent.click(screen.getByRole('button', { name: /go/i }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const brief = onSubmit.mock.calls[0][0];
    expect(brief.revenue_usd).toBe(500000000);
    expect(brief.per_occurrence_deductible).toBe(1000000);
    expect(brief.security_controls).toContain('MFA is comprehensive');
  });
});
