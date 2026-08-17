/**
 * Chat deep-link routing (Feature 3): /consult?tab=chat opens the interactive
 * consultant chat tab instead of the default assess tab.  The heavy chat
 * component is mocked so the test asserts routing, not chat internals.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ConsultantPortal from '../ConsultantPortal';

vi.mock('../Consultant', () => ({
  default: () => <div>chat-tab-content</div>,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ConsultantPortal />
    </MemoryRouter>,
  );
}

describe('ConsultantPortal chat routing (?tab=chat)', () => {
  it('defaults to the assess tab', () => {
    renderAt('/consult');
    expect(screen.getByText('Company assessment')).toBeTruthy();
    expect(screen.queryByText('chat-tab-content')).toBeNull();
  });

  it('opens the chat tab when ?tab=chat is present', () => {
    renderAt('/consult?tab=chat');
    expect(screen.getByText('chat-tab-content')).toBeTruthy();
    expect(screen.queryByText('Company assessment')).toBeNull();
  });

  it('ignores unknown tab values and falls back to assess', () => {
    renderAt('/consult?tab=whatever');
    expect(screen.getByText('Company assessment')).toBeTruthy();
    expect(screen.queryByText('chat-tab-content')).toBeNull();
  });
});
