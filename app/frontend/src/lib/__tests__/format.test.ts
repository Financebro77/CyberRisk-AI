/**
 * Formatting helpers.  The retention-precision bug: formatMoney rounds to 0
 * decimals at the $M scale, so $1,000,000 and $1,001,000 both render "$1M".
 * formatMoneyFull must show the exact dollars so a +1000 retention tweak is
 * visible on the insurance cards.
 */
import { describe, it, expect } from 'vitest';
import { formatMoney, formatMoneyFull } from '../format';

describe('formatMoneyFull (full-precision insurance figures)', () => {
  it('shows exact dollars without collapsing to millions', () => {
    expect(formatMoneyFull(1_001_000)).toBe('$1,001,000');
    expect(formatMoneyFull(1_000_000)).toBe('$1,000,000');
  });

  it('distinguishes a +1000 change that formatMoney collapses', () => {
    expect(formatMoneyFull(1_001_000)).not.toBe(formatMoneyFull(1_000_000));
  });

  it('renders a dash for missing values', () => {
    expect(formatMoneyFull(null)).toBe('—');
    expect(formatMoneyFull(undefined)).toBe('—');
  });
});

describe('formatMoney (compact KPI cards)', () => {
  it('keeps compact rounding at the million scale', () => {
    expect(formatMoney(1_000_000)).toBe('$1M');
    expect(formatMoney(1_001_000)).toBe('$1M');
  });
});
