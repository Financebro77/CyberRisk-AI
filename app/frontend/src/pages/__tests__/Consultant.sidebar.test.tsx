/**
 * Desktop consultant sidebar (Feature 3): a ChatGPT/Doubao-style conversation
 * list owning the browser's per-device session ids (localStorage), with
 * resume-from-SQLite, new-chat, and delete.
 *
 * The `api` module is mocked so no network/backend is touched.  Contract under
 * test:
 *
 *   - the sidebar lists the owned conversations from localStorage,
 *   - mount resumes the active (or most recent) conversation's transcript,
 *     including persisted tool charts,
 *   - "New chat" creates a fresh session and KEEPS the previous one,
 *   - delete calls the API, prunes localStorage, and drops the row,
 *   - deleting the last conversation starts a fresh one,
 *   - the localStorage conversation-id list stays in sync.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { api } from '../../lib/api';
import Consultant from '../Consultant';
import { relativeTime } from '../../components/ChatSidebar';
import type { ChatSession } from '../../lib/types';

vi.mock('../../lib/api', () => ({
  api: {
    chat: {
      createSession: vi.fn(),
      turn: vi.fn(),
      deleteSession: vi.fn(),
      history: vi.fn(),
      getSession: vi.fn(),
      listSessions: vi.fn(),
      renameSession: vi.fn(),
    },
  },
}));

const chat = api.chat as unknown as Record<string, ReturnType<typeof vi.fn>>;

const CONVERSATIONS_KEY = 'cyberrisk-conversations';
const ACTIVE_KEY = 'cyberrisk-active-conversation';

/** A persisted tool trace the transcript renders charts from on resume. */
const TOOL_TRACE = [
  {
    name: 'run_loss_simulation',
    arguments: { n_years: 50000 },
    ok: true,
    data: {
      status: 'ok',
      eal: 1_400_000,
      var_95: 3_000_000,
      var_99: 5_000_000,
      es_99: 8_000_000,
      prob_zero_loss: 0.3,
      loss_distribution: {
        p50: 100_000,
        p90: 1_000_000,
        p95: 2_000_000,
        p99: 5_000_000,
        p99_9: 9_000_000,
      },
    },
  },
];

const mk = (overrides: Partial<ChatSession>): ChatSession => ({
  session_id: 'a',
  title: 'New conversation',
  created_at: '2026-08-16T00:00:00.000Z',
  updated_at: '2026-08-16T00:00:00.000Z',
  history: [],
  ...overrides,
});

function seedIds(ids: string[], active?: string) {
  localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(ids));
  if (active) localStorage.setItem(ACTIVE_KEY, active);
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
});

describe('Consultant sidebar', () => {
  it('lists owned conversations from localStorage and resumes the active one', async () => {
    seedIds(['a', 'b'], 'a');
    chat.listSessions.mockResolvedValue({
      sessions: [
        mk({
          session_id: 'a',
          title: 'Retail firm assessment',
          updated_at: '2026-08-16T08:00:00.000Z',
          history: [
            { role: 'user', content: 'Please assess a retail firm', tool_trace: null },
            { role: 'assistant', content: 'Here is the retail assessment.', tool_trace: null },
          ],
        }),
        mk({ session_id: 'b', title: 'Second conversation', updated_at: '2026-08-16T07:00:00.000Z' }),
      ],
    });

    render(<Consultant />);

    // Sidebar rows for every owned conversation (the active title also shows
    // in the header, so use getAllByText).
    expect(await screen.findAllByText('Retail firm assessment')).not.toHaveLength(0);
    expect(screen.getAllByText('Second conversation')).not.toHaveLength(0);
    // The active conversation's transcript is resumed from the server.
    expect(screen.getByText('Here is the retail assessment.')).toBeTruthy();
    // No session was created: we resumed an existing one.
    expect(chat.createSession).not.toHaveBeenCalled();
  });

  it('New chat creates a session and keeps the previous one in the sidebar', async () => {
    seedIds(['a'], 'a');
    chat.listSessions.mockResolvedValue({
      sessions: [
        mk({
          session_id: 'a',
          title: 'Retail firm assessment',
          history: [
            { role: 'user', content: 'Please assess a retail firm', tool_trace: null },
            { role: 'assistant', content: 'Done with the retail assessment.', tool_trace: null },
          ],
        }),
      ],
    });
    chat.createSession.mockResolvedValue({ session_id: 'b' });

    render(<Consultant />);
    await screen.findAllByText('Retail firm assessment');

    fireEvent.click(screen.getByRole('button', { name: /new chat/i }));

    // Previous conversation survives (no delete); the new id becomes active
    // and is owned locally.  The header flips to "New conversation" only once
    // createSession resolves, so awaiting it flushes the async persistence.
    expect(await screen.findAllByText('New conversation')).not.toHaveLength(0);
    expect(chat.deleteSession).not.toHaveBeenCalled();
    expect(chat.createSession).toHaveBeenCalledTimes(1);
    expect(JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) ?? '[]')).toEqual(['a', 'b']);
    expect(localStorage.getItem(ACTIVE_KEY)).toBe('b');
    // Transcript cleared back to the empty state.
    expect(screen.getByText(/how can i help with your cyber exposure/i)).toBeTruthy();
  });

  it('resume renders persisted tool charts for earlier assistant messages', async () => {
    seedIds(['a'], 'a');
    chat.listSessions.mockResolvedValue({
      sessions: [
        mk({
          session_id: 'a',
          title: 'Simulated loss',
          history: [
            { role: 'user', content: 'Run the loss model', tool_trace: null },
            { role: 'assistant', content: 'Here is the simulation.', tool_trace: TOOL_TRACE },
          ],
        }),
      ],
    });

    render(<Consultant />);

    // The persisted turn re-renders its chart + modelled-metrics footer.
    // (EAL renders through formatMoney — 1.4M rounds to "$1M" — so assert on
    // the stable footer labels rather than a rounded figure.)
    expect(await screen.findByText('Loss distribution')).toBeTruthy();
    expect(screen.getByText('Modelled')).toBeTruthy();
    expect(screen.getByText(/EAL \$1M/)).toBeTruthy();
  });

  it('delete calls the API, prunes localStorage, and drops the row', async () => {
    seedIds(['a', 'b'], 'b');
    chat.listSessions.mockResolvedValue({
      sessions: [
        mk({
          session_id: 'a',
          title: 'Retail firm assessment',
          history: [
            { role: 'user', content: 'Please assess a retail firm', tool_trace: null },
            { role: 'assistant', content: 'Done with the retail assessment.', tool_trace: null },
          ],
        }),
        mk({
          session_id: 'b',
          title: 'Second conversation',
          updated_at: '2026-08-16T09:00:00.000Z',
          history: [
            { role: 'user', content: 'Hello', tool_trace: null },
            { role: 'assistant', content: 'Second conversation answer.', tool_trace: null },
          ],
        }),
      ],
    });
    chat.getSession.mockResolvedValue(
      mk({
        session_id: 'a',
        title: 'Retail firm assessment',
        history: [
          { role: 'user', content: 'Please assess a retail firm', tool_trace: null },
          { role: 'assistant', content: 'Done with the retail assessment.', tool_trace: null },
        ],
      }),
    );

    render(<Consultant />);
    await screen.findByText('Second conversation answer.');

    // Delete the ACTIVE conversation (b).  The button is hover-revealed but
    // still queryable by its accessible name.
    fireEvent.click(screen.getByRole('button', { name: 'Delete conversation Second conversation' }));

    expect(chat.deleteSession).toHaveBeenCalledWith('b');
    expect(JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) ?? '[]')).toEqual(['a']);
    // The remaining conversation is resumed in its place.
    expect(await screen.findByText('Done with the retail assessment.')).toBeTruthy();
    expect(screen.queryByText('Second conversation')).toBeNull();
  });

  it('deleting the last conversation starts a fresh one', async () => {
    seedIds(['a'], 'a');
    chat.listSessions.mockResolvedValue({
      sessions: [
        mk({
          session_id: 'a',
          title: 'Retail firm assessment',
          history: [
            { role: 'user', content: 'Please assess a retail firm', tool_trace: null },
            { role: 'assistant', content: 'Done with the retail assessment.', tool_trace: null },
          ],
        }),
      ],
    });
    chat.createSession.mockResolvedValue({ session_id: 'b' });

    render(<Consultant />);
    await screen.findByText('Done with the retail assessment.');

    fireEvent.click(screen.getByRole('button', { name: 'Delete conversation Retail firm assessment' }));

    expect(chat.deleteSession).toHaveBeenCalledWith('a');
    // One fresh session is created in place of the deleted one.  Awaiting the
    // header flip to "New conversation" flushes the async persistence.
    expect(await screen.findAllByText('New conversation')).not.toHaveLength(0);
    expect(chat.createSession).toHaveBeenCalledTimes(1);
    expect(JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) ?? '[]')).toEqual(['b']);
    expect(localStorage.getItem(ACTIVE_KEY)).toBe('b');
    expect(screen.getByText(/how can i help with your cyber exposure/i)).toBeTruthy();
  });

  it('formats relative timestamps for the sidebar', () => {
    const now = Date.now();
    const iso = (msAgo: number) => new Date(now - msAgo).toISOString();
    expect(relativeTime(iso(30_000))).toBe('just now');
    expect(relativeTime(iso(5 * 60_000))).toBe('5m ago');
    expect(relativeTime(iso(3 * 60 * 60_000))).toBe('3h ago');
    expect(relativeTime(iso(4 * 24 * 60 * 60_000))).toBe('4d ago');
  });
});
