/**
 * Chat-shell hook tests — cover the API/chat layer of the voice client.
 *
 * The `api` module is mocked so no network or backend is touched.  Scenarios:
 * app startup (session created), API connection, backend failure (exact
 * string), conversation state (server history is authoritative), invalid
 * input, risk-engine invocation (turn called with the user text), and
 * privacy/security (DELETE on end session, no storage writes).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { api } from '../../lib/api';
import { useChat, BACKEND_UNAVAILABLE, RECOGNITION_FAILURE } from '../useChat';

vi.mock('../../lib/api', () => ({
  api: {
    chat: {
      createSession: vi.fn(),
      turn: vi.fn(),
      deleteSession: vi.fn(),
      history: vi.fn(),
    },
  },
}));

const createSession = api.chat.createSession as unknown as ReturnType<typeof vi.fn>;
const turn = api.chat.turn as unknown as ReturnType<typeof vi.fn>;
const deleteSession = api.chat.deleteSession as unknown as ReturnType<typeof vi.fn>;

const HISTORY = [
  { role: 'user', content: 'Assess a healthcare firm' },
  {
    role: 'assistant',
    content: 'I need a little more information before I can calculate the risk.',
  },
];

function turnResponse(overrides: Record<string, unknown> = {}) {
  return {
    session_id: 'sess-1',
    role: 'assistant',
    content: 'I need a little more information before I can calculate the risk.',
    tool_trace: [],
    history: HISTORY,
    safety: null,
    model: 'deepseek-chat',
    privacy_notice: '',
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  // No localStorage/sessionStorage writes are allowed anywhere in the hook.
  localStorage.clear();
  sessionStorage.clear();
  const spyL = vi.spyOn(Storage.prototype, 'setItem');
  const spyS = vi.spyOn(Storage.prototype, 'removeItem');
  // store spies for assertions
  (globalThis as Record<string, unknown>).__storageSpies = { spyL, spyS };
});

describe('useChat', () => {
  it('creates a session on mount (app startup)', async () => {
    createSession.mockResolvedValue({ session_id: 'sess-1' });
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(createSession).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'));
  });

  it('surfaces the exact backend-unavailable string when session creation fails', async () => {
    createSession.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.error).toBe(BACKEND_UNAVAILABLE));
  });

  it('does not send empty or whitespace-only input (invalid input)', async () => {
    createSession.mockResolvedValue({ session_id: 'sess-1' });
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'));

    await act(async () => {
      await result.current.send('   ');
      await result.current.send('');
    });
    expect(turn).not.toHaveBeenCalled();
    expect(result.current.messages).toHaveLength(0);
  });

  it('calls the risk engine via api.chat.turn with the exact user text', async () => {
    createSession.mockResolvedValue({ session_id: 'sess-1' });
    turn.mockResolvedValue(turnResponse());
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'));

    await act(async () => {
      await result.current.send('What is my expected annual loss?');
    });
    expect(turn).toHaveBeenCalledWith('sess-1', { message: 'What is my expected annual loss?' });
  });

  it('replaces the conversation with the server history (conversation state)', async () => {
    createSession.mockResolvedValue({ session_id: 'sess-1' });
    turn.mockResolvedValue(turnResponse());
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'));

    await act(async () => {
      await result.current.send('Assess a healthcare firm');
    });
    expect(result.current.messages.map((m) => m.content)).toEqual(
      HISTORY.map((m) => m.content),
    );
    // The last assistant message carries the tool trace + safety.
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last.toolTrace).toEqual([]);
    expect(last.safety).toBeNull();
  });

  it('relays a missing-info reply verbatim and stays idle (missing-info detection)', async () => {
    createSession.mockResolvedValue({ session_id: 'sess-1' });
    turn.mockResolvedValue(
      turnResponse({
        content: 'I need a little more information before I can calculate the risk.',
      }),
    );
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'));

    await act(async () => {
      await result.current.send('Assess us');
    });
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant?.content).toBe('I need a little more information before I can calculate the risk.');
    // Client did no local computation — it only relayed the backend's reply.
    expect(turn).toHaveBeenCalledTimes(1);
  });

  it('shows the exact backend-unavailable string when a turn fails', async () => {
    createSession.mockResolvedValue({ session_id: 'sess-1' });
    turn.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'));

    await act(async () => {
      await result.current.send('hello');
    });
    expect(result.current.error).toBe(BACKEND_UNAVAILABLE);
    expect(result.current.messages.some((m) => m.content.includes(BACKEND_UNAVAILABLE))).toBe(true);
  });

  it('endSession issues a DELETE and starts a fresh session (privacy/security)', async () => {
    createSession.mockResolvedValue({ session_id: 'sess-1' });
    turn.mockResolvedValue(turnResponse());
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'));

    await act(async () => {
      await result.current.send('hello');
      await result.current.endSession();
    });
    expect(deleteSession).toHaveBeenCalledWith('sess-1');
    // A new session was requested.
    expect(createSession.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(result.current.messages).toHaveLength(0);
  });

  it('never writes the conversation to storage (privacy/security)', async () => {
    createSession.mockResolvedValue({ session_id: 'sess-1' });
    turn.mockResolvedValue(turnResponse());
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'));

    await act(async () => {
      await result.current.send('private information');
    });
    // No setItem/removeItem was called on localStorage or sessionStorage.
    const { spyL, spyS } = (globalThis as Record<string, unknown>).__storageSpies as {
      spyL: ReturnType<typeof vi.spyOn>;
      spyS: ReturnType<typeof vi.spyOn>;
    };
    expect(spyL).not.toHaveBeenCalled();
    expect(spyS).not.toHaveBeenCalled();
  });
});

// RECOGNITION_FAILURE is part of the exact-string contract even though the
// chat hook itself doesn't emit it — assert the constant matches verbatim so a
// future drift is caught.
describe('exact error strings', () => {
  it('matches the required verbatim strings', () => {
    expect(BACKEND_UNAVAILABLE).toBe(
      'The CyberRisk AI service is currently unavailable. Please try again.',
    );
    expect(RECOGNITION_FAILURE).toBe("I couldn't hear that clearly. Please try again.");
  });
});
