/**
 * End-to-end render tests for the single-screen voice consultant.
 *
 * The `api` module is mocked (no network) and the speech engine is faked via
 * browser globals.  These tests drive the whole screen: app startup, mic
 * permission path, speech-to-text → user bubble → API call, missing-info reply
 * relayed verbatim (client stays idle), result generation (markdown + tool
 * trace), text-to-speech on an assistant reply, backend failure (exact
 * string), invalid input, and privacy (no storage writes, no API keys).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { api } from '../../lib/api';
import { VoiceConsultant } from '../VoiceConsultant';

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

// ---------------------------------------------------------------------------
// Speech fakes
// ---------------------------------------------------------------------------
class FakeRecognition implements ISpeechRecognition {
  lang = '';
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  onstart: ((this: ISpeechRecognition, ev: Event) => void) | null = null;
  onend: ((this: ISpeechRecognition, ev: Event) => void) | null = null;
  onresult: ((this: ISpeechRecognition, ev: any) => void) | null = null;
  onerror: ((this: ISpeechRecognition, ev: any) => void) | null = null;
  onaudiostart: ((this: ISpeechRecognition, ev: Event) => void) | null = null;
  onaudioend: ((this: ISpeechRecognition, ev: Event) => void) | null = null;
  onnomatch: ((this: ISpeechRecognition, ev: any) => void) | null = null;
  onsoundstart: ((this: ISpeechRecognition, ev: Event) => void) | null = null;
  onsoundend: ((this: ISpeechRecognition, ev: Event) => void) | null = null;
  onspeechstart: ((this: ISpeechRecognition, ev: Event) => void) | null = null;
  onspeechend: ((this: ISpeechRecognition, ev: Event) => void) | null = null;
  start() {}
  stop() {}
  abort() {}
}

let instances: FakeRecognition[] = [];
const spokenUtterances: string[] = [];
const synthCancel = vi.fn();

function installRecognition() {
  instances = [];
  spokenUtterances.length = 0;
  synthCancel.mockClear();
  const Ctor = class extends FakeRecognition {
    constructor() {
      super();
      instances.push(this);
    }
  } as unknown as SpeechRecognitionConstructor;
  Object.defineProperty(window, 'SpeechRecognition', { value: Ctor, configurable: true });
  Object.defineProperty(window, 'webkitSpeechRecognition', { value: undefined, configurable: true });
  Object.defineProperty(window, 'speechSynthesis', {
    value: {
      speak: (u: { text: string }) => spokenUtterances.push(u.text),
      cancel: synthCancel,
    },
    configurable: true,
  });
  (globalThis as Record<string, unknown>).SpeechSynthesisUtterance = class {
    text: string;
    onend: ((this: SpeechSynthesisUtterance, ev: Event) => void) | null = null;
    onerror: ((this: SpeechSynthesisUtterance, ev: Event) => void) | null = null;
    constructor(text: string) {
      this.text = text;
    }
  };
}

function installNoSpeech() {
  Object.defineProperty(window, 'SpeechRecognition', { value: undefined, configurable: true });
  Object.defineProperty(window, 'webkitSpeechRecognition', { value: undefined, configurable: true });
  Object.defineProperty(window, 'speechSynthesis', { value: undefined, configurable: true });
}

function installPermissions(state: 'granted' | 'denied' = 'granted') {
  Object.defineProperty(navigator, 'permissions', {
    value: {
      query: vi.fn(() => Promise.resolve({ state, onchange: null })),
    },
    configurable: true,
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function turnResponse(overrides: Record<string, unknown> = {}) {
  return {
    session_id: 'sess-1',
    role: 'assistant',
    content: 'Your risk score is 59.9 / 100 — High.',
    tool_trace: [],
    history: [
      { role: 'user', content: 'assess my risk' },
      { role: 'assistant', content: 'Your risk score is 59.9 / 100 — High.' },
    ],
    safety: null,
    model: 'deepseek-chat',
    privacy_notice: '',
    ...overrides,
  };
}

async function renderReady() {
  const view = render(<VoiceConsultant />);
  await waitFor(() => expect(createSession).toHaveBeenCalled());
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  createSession.mockResolvedValue({ session_id: 'sess-1' });
  turn.mockResolvedValue(turnResponse());
  deleteSession.mockResolvedValue({ status: 'ok' });
  installPermissions('granted');
});

afterEach(() => {
  vi.restoreAllMocks();
  cleanup();
});

describe('VoiceConsultant single screen', () => {
  it('renders the title, prompt and microphone button on open (app startup)', async () => {
    installNoSpeech();
    await renderReady();
    expect(screen.getByText('CyberRisk AI')).toBeInTheDocument();
    expect(
      screen.getByText('How can I help you assess your cyber risk?'),
    ).toBeInTheDocument();
    // The mic button is present.
    expect(screen.getByRole('button', { name: /speak to the consultant/i })).toBeInTheDocument();
    // No navigation, no extra screens.
    expect(screen.queryByText('Landing')).not.toBeInTheDocument();
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });

  it('sends a recognised transcript as a user message via the API (speech-to-text)', async () => {
    installRecognition();
    await renderReady();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /speak to the consultant/i }));
    });
    // The recognizer is created lazily by engine.start() on the click.
    const rec = instances[0];
    await act(async () => {
      // The browser fires the recognizer's onstart once it begins listening.
      rec.onstart?.(new Event('start'));
    });
    // The recognizer fired 'start' → listening state.
    await waitFor(() => expect(screen.getByText('Listening…')).toBeInTheDocument());
    await act(async () => {
      rec.onresult?.({
        resultIndex: 0,
        results: { length: 1, 0: { isFinal: true, length: 1, 0: { transcript: 'assess my risk' }, item: () => ({ transcript: 'assess my risk' }) } },
      } as never);
      rec.onend?.(new Event('end'));
    });
    await waitFor(() =>
      expect(turn).toHaveBeenCalledWith('sess-1', { message: 'assess my risk' }),
    );
    // The user bubble appeared and the assistant reply rendered.
    await waitFor(() => expect(screen.getByText('assess my risk')).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByText('Your risk score is 59.9 / 100 — High.')).toBeInTheDocument(),
    );
  });

  it('relays a missing-info reply verbatim and does no local computation', async () => {
    installNoSpeech();
    turn.mockResolvedValue(
      turnResponse({
        content: 'I need a little more information before I can calculate the risk.',
        history: [
          { role: 'user', content: 'assess us' },
          { role: 'assistant', content: 'I need a little more information before I can calculate the risk.' },
        ],
      }),
    );
    await renderReady();
    const input = screen.getByRole('textbox', { name: /type a message/i });
    await userEvent.type(input, 'assess us');
    await userEvent.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() =>
      expect(screen.getByText('I need a little more information before I can calculate the risk.')).toBeInTheDocument(),
    );
    // Exactly one API turn; no client-side risk fetch.
    expect(turn).toHaveBeenCalledTimes(1);
  });

  it('renders an assistant markdown reply (result generation)', async () => {
    installNoSpeech();
    turn.mockResolvedValue(
      turnResponse({
        content: '**High risk** — EAL $3.6M.',
        history: [
          { role: 'user', content: 'model it' },
          { role: 'assistant', content: '**High risk** — EAL $3.6M.' },
        ],
      }),
    );
    await renderReady();
    await userEvent.type(screen.getByRole('textbox', { name: /type a message/i }), 'model it');
    await userEvent.click(screen.getByRole('button', { name: /send message/i }));
    // The markdown is rendered (strong tag present, not raw asterisks).
    await waitFor(() => {
      const strong = screen.getAllByText('High risk');
      expect(strong.length).toBeGreaterThan(0);
      // The full sentence is present somewhere in the transcript.
      expect(document.body.textContent).toContain('High risk — EAL $3.6M.');
    });
  });

  it('speaks the assistant reply aloud (text-to-speech)', async () => {
    installRecognition();
    await renderReady();
    await userEvent.type(screen.getByRole('textbox', { name: /type a message/i }), 'what is my risk?');
    await userEvent.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => expect(spokenUtterances).toContain('Your risk score is 59.9 / 100 — High.'));
  });

  it('shows the exact backend-unavailable string when the API fails', async () => {
    installNoSpeech();
    turn.mockRejectedValue(new Error('network'));
    await renderReady();
    await userEvent.type(screen.getByRole('textbox', { name: /type a message/i }), 'hello');
    await userEvent.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() =>
      expect(
        screen.getByText('The CyberRisk AI service is currently unavailable. Please try again.'),
      ).toBeInTheDocument(),
    );
  });

  it('does not send empty input (invalid input)', async () => {
    installNoSpeech();
    await renderReady();
    const input = screen.getByRole('textbox', { name: /type a message/i });
    await userEvent.type(input, '   ');
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled();
    expect(turn).not.toHaveBeenCalled();
  });

  it('shows the mic status and handles permission denial gracefully', async () => {
    installRecognition();
    installPermissions('denied');
    await renderReady();
    await waitFor(() =>
      expect(screen.getByText('Microphone denied — enable access to use voice')).toBeInTheDocument(),
    );
    // The mic button remains available.
    expect(screen.getByRole('button', { name: /speak to the consultant/i })).toBeInTheDocument();
  });

  it('clears the conversation and ends the session (privacy controls)', async () => {
    installNoSpeech();
    await renderReady();
    // Type + send one message.
    await userEvent.type(screen.getByRole('textbox', { name: /type a message/i }), 'hello');
    await userEvent.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => expect(turn).toHaveBeenCalled());
    // Clear conversation.
    await userEvent.click(screen.getByRole('button', { name: /clear conversation/i }));
    expect(screen.queryByText('hello')).not.toBeInTheDocument();
    // End session → DELETE called.
    await userEvent.click(screen.getByRole('button', { name: /end session/i }));
    await waitFor(() => expect(deleteSession).toHaveBeenCalledWith('sess-1'));
  });

  it('never writes the conversation to storage (privacy/security)', async () => {
    installRecognition();
    const setSpy = vi.spyOn(Storage.prototype, 'setItem');
    const remSpy = vi.spyOn(Storage.prototype, 'removeItem');
    await renderReady();
    await userEvent.type(screen.getByRole('textbox', { name: /type a message/i }), 'private info');
    await userEvent.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => expect(turn).toHaveBeenCalled());
    expect(setSpy).not.toHaveBeenCalled();
    expect(remSpy).not.toHaveBeenCalled();
  });

  it('contains no API keys or LLM credentials in the rendered DOM', async () => {
    installNoSpeech();
    await renderReady();
    const html = document.body.innerHTML;
    expect(html).not.toMatch(/sk-[a-zA-Z0-9]{20,}/); // OpenAI-style key
    expect(html).not.toMatch(/openai|deepseek/i);
  });
});
