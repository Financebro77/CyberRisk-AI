/**
 * Landing page (four-reference redesign) — light smoke assertions.  The
 * redesign is visual work; these tests pin the reference-derived copy and the
 * anchor sections (two-tone CYBER ATTACK headline, threat pill, scan CTA,
 * terminal proof, dashboard panel, marquee, signal readout), not pixels.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Landing from '../Landing';

// vitest.config has no `globals`, so testing-library's auto-cleanup does not
// run; without this, each render() accumulates in the DOM and every query
// after the first sees N copies of the page.  Same convention as the
// ConsultantPortal tests.
afterEach(cleanup);

function renderLanding() {
  return render(
    <MemoryRouter>
      <Landing />
    </MemoryRouter>,
  );
}

describe('Landing (four-reference redesign)', () => {
  it('leads with the giant two-tone CYBER ATTACK headline', () => {
    renderLanding();
    // Accessible name = the h1's text content across the cyan/red spans.
    expect(screen.getByRole('heading', { name: 'CYBER ATTACK' })).toBeTruthy();
  });

  it('shows the threat-detected alert pill', () => {
    renderLanding();
    expect(screen.getByText('THREAT DETECTED')).toBeTruthy();
    expect(screen.getByText('RISK LEVEL CRITICAL')).toBeTruthy();
  });

  it('shows the "Identify. Analyze. Neutralize." tagline', () => {
    renderLanding();
    expect(screen.getByText('Identify. Analyze. Neutralize.')).toBeTruthy();
  });

  it('offers the Run Risk Scan CTA with a company-profile input', () => {
    renderLanding();
    expect(screen.getByPlaceholderText(/enter your company profile/i)).toBeTruthy();
    expect(screen.getAllByRole('link', { name: /run risk scan/i }).length).toBeGreaterThan(0);
  });

  it('shows the terminal readout with the EAL line', () => {
    renderLanding();
    expect(
      screen.getByRole('img', { name: /Simulated cyber risk assessment/ }),
    ).toBeTruthy();
    expect(screen.getAllByText(/Expected annual loss/).length).toBeGreaterThan(0);
  });

  it('shows the live dashboard panel with the AI Shield status', () => {
    renderLanding();
    expect(screen.getByText('AI SHIELD ONLINE')).toBeTruthy();
    expect(screen.getByText('RISK SCORE')).toBeTruthy();
  });

  it('runs the threat marquee', () => {
    renderLanding();
    expect(screen.getAllByText('RANSOMWARE').length).toBeGreaterThan(0);
  });

  it('keeps the AI consultant deep link in the nav', () => {
    renderLanding();
    expect(screen.getAllByText('AI Cyber Risk Consultant').length).toBeGreaterThan(0);
  });

  it('shows the loss-distribution signal readout markers', () => {
    renderLanding();
    expect(
      screen.getByRole('img', { name: /Modelled annual loss distribution/ }),
    ).toBeTruthy();
    expect(screen.getAllByText('1-in-100-year').length).toBeGreaterThan(0);
    expect(screen.getAllByText('1-in-1000-year').length).toBeGreaterThan(0);
  });
});

describe('Landing (Armageddon rebrand)', () => {
  it('brands the nav with the Armageddon wordmark', () => {
    renderLanding();
    // The nav brand link carries the new name — the old "CYBERRISK//AI" is gone.
    expect(screen.getByRole('link', { name: /armageddon/i })).toBeTruthy();
  });

  it('shows the Armageddon logo mark in the nav', () => {
    renderLanding();
    // The logo mark is a labelled image, not a bare icon.
    expect(screen.getByRole('img', { name: /armageddon logo/i })).toBeTruthy();
  });

  it('brands the footer with Armageddon', () => {
    renderLanding();
    // Scoped to the footer — the nav wordmark also says ARMAGEDDON now.
    expect(within(screen.getByRole('contentinfo')).getByText(/ARMAGEDDON/i)).toBeTruthy();
  });
});
