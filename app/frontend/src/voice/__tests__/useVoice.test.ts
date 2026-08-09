/**
 * useVoice hook tests.  The engine is real here — `speech.test.ts` asserts its
 * internals, and these tests drive it via the hook through faked browser
 * globals.  Scenarios: mic-permission path, speech-to-text → transcript →
 * send callback, text-to-speech, interrupt/cancel, and the derived state
 * machine.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useVoice, deriveVoiceState } from '../useVoice';

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
  get instance(): this {
    return this;
  }
}

let instances: FakeRecognition[] = [];

function installRecognition() {
  instances = [];
  const Ctor = class extends FakeRecognition {
    constructor() {
      super();
      instances.push(this);
    }
  } as unknown as SpeechRecognitionConstructor;
  Object.defineProperty(window, 'SpeechRecognition', { value: Ctor, configurable: true });
}

function installNoRecognition() {
  Object.defineProperty(window, 'SpeechRecognition', { value: undefined, configurable: true });
  Object.defineProperty(window, 'webkitSpeechRecognition', { value: undefined, configurable: true });
}

function installPermissions() {
  Object.defineProperty(navigator, 'permissions', {
    value: {
      query: vi.fn(() => Promise.resolve({ state: 'granted', onchange: null })),
    },
    configurable: true,
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  installPermissions();
});

describe('useVoice', () => {
  it('reports mic status granted from the permissions API', async () => {
    installRecognition();
    const onTranscript = vi.fn();
    const onError = vi.fn();
    const { result } = renderHook(() => useVoice({ onTranscript, onError }));
    await waitFor(() => expect(result.current.micStatus).toBe('granted'));
  });

  it('starts listening on startListening and stops on stopListening', async () => {
    installRecognition();
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useVoice({ onTranscript, onError: vi.fn() }));
    await waitFor(() => expect(result.current.micStatus).toBe('granted'));

    await act(async () => {
      result.current.startListening();
      // The browser fires the recognizer's onstart once it begins listening.
      instances[0].onstart?.(new Event('start'));
    });
    await waitFor(() => expect(result.current.listening).toBe(true));

    await act(async () => {
      result.current.stopListening();
    });
    await waitFor(() => expect(result.current.listening).toBe(false));
  });

  it('delivers a transcript through the onTranscript callback (speech-to-text)', async () => {
    installRecognition();
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useVoice({ onTranscript, onError: vi.fn() }));
    await act(async () => {
      result.current.startListening();
    });
    await act(async () => {
      const rec = instances[0];
      rec.onstart?.(new Event('start'));
      rec.onresult?.({
        resultIndex: 0,
        results: { length: 1, 0: { isFinal: true, length: 1, 0: { transcript: 'hello' }, item: () => ({ transcript: 'hello' }) } },
      } as never);
      rec.onend?.(new Event('end'));
    });
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith('hello'));
    await waitFor(() => expect(result.current.listening).toBe(false));
  });

  it('starts speech synthesis on speak() and reflects speaking state (text-to-speech)', async () => {
    installRecognition();
    const utterances: string[] = [];
    Object.defineProperty(window, 'speechSynthesis', {
      value: {
        speak: (u: { text: string }) => utterances.push(u.text),
        cancel: vi.fn(),
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

    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onError: vi.fn() }));
    await act(async () => {
      result.current.engine.speak('Your risk is high');
    });
    await waitFor(() => expect(result.current.speaking).toBe(true));
    expect(utterances).toEqual(['Your risk is high']);

    await act(async () => {
      result.current.cancelSpeech();
    });
    await waitFor(() => expect(result.current.speaking).toBe(false));
  });

  it('reports a recognition error via onError (mic permission / recognition failure)', async () => {
    installRecognition();
    const onError = vi.fn();
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onError }));
    await act(async () => {
      result.current.startListening();
    });
    await act(async () => {
      instances[0].onerror?.({ error: 'not-allowed', message: 'denied' } as never);
    });
    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith('mic-denied', 'not-allowed'),
    );
  });

  it('handles an unsupported browser gracefully (no mic button reliance)', () => {
    installNoRecognition();
    const onError = vi.fn();
    const { result } = renderHook(() => useVoice({ onTranscript: vi.fn(), onError }));
    expect(result.current.engine.supported).toBe(false);
    act(() => result.current.startListening());
    expect(onError).toHaveBeenCalled();
  });
});

describe('deriveVoiceState', () => {
  it('prioritises speaking > listening > thinking > idle', () => {
    expect(deriveVoiceState({ listening: false, speaking: false, thinking: false })).toBe('idle');
    expect(deriveVoiceState({ listening: false, speaking: false, thinking: true })).toBe('thinking');
    expect(deriveVoiceState({ listening: true, speaking: false, thinking: false })).toBe('listening');
    expect(deriveVoiceState({ listening: true, speaking: true, thinking: true })).toBe('speaking');
  });
});
