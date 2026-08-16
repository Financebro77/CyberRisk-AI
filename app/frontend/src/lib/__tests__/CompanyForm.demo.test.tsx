import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { CompanyForm } from '../../components/CompanyForm';

afterEach(cleanup);

describe('CompanyForm demo mode', () => {
  it('loads a demo company with a numeric revenue on press', () => {
    render(<CompanyForm onSubmit={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /load demo/i }));
    const revenue = screen.getByLabelText(/revenue/i) as HTMLInputElement;
    expect(revenue.value).not.toBe('');
    expect(Number(revenue.value)).toBeGreaterThan(0);
  });

  it('produces different demo values across repeated presses', () => {
    render(<CompanyForm onSubmit={() => {}} />);
    const button = screen.getByRole('button', { name: /load demo/i });
    const revenues = new Set<string>();
    for (let i = 0; i < 3; i++) {
      fireEvent.click(button);
      revenues.add((screen.getByLabelText(/revenue/i) as HTMLInputElement).value);
    }
    expect(revenues.size).toBeGreaterThan(1);
  });

  it('submits real policy terms (retention + limit) after loading a demo', () => {
    const onSubmit = vi.fn();
    render(<CompanyForm submitLabel="Submit assessment" onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole('button', { name: /load demo/i }));
    fireEvent.click(screen.getByRole('button', { name: /submit assessment/i }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.per_occurrence_deductible).toBeGreaterThan(0);
    expect(payload.annual_aggregate_limit).toBeGreaterThan(0);
  });
});
