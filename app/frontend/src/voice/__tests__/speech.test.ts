/**
 * VoiceEngine bridge tests.  No real Web Speech exists in happy-dom, so the
 * browser globals (`webkitSpeechRecognition`, `speechSynthesis`,
 * `navigator.permissions`) are faked and the engine's behaviour is asserted
 * against those fakes.  These cover: feature detection, microphone-permission
 * reporting, recognition start/stop, speech-to-text transcript delivery,
 * text-to-speech speak/cancel, and error classification.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { VoiceEngine } from '../speech';
// `ISpeechRecognition`, `SpeechRecognitionEvent`, `SpeechRecognitionErrorEvent`
// are ambient globals declared in ../speech (via `declare global`) — no import.

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

type FakeHandler = ((ev: Event) => void) | null;

class FakeRecognition implements ISpeechRecognition {
  lang = '';
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  onstart: FakeHandler = null;
  onend: FakeHandler = null;
  onresult: ((this: ISpeechRecognition, ev: SpeechRecognitionEvent) => void) | null = null;
  onerror: ((this: ISpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null = null;
  onaudiostart: FakeHandler = null;
  onaudioend: FakeHandler = null;
  onnomatch: ((this: ISpeechRecognition, ev: SpeechRecognitionEvent) => void) | null = null;
  onsoundstart: FakeHandler = null;
  onsoundend: FakeHandler = null;
  onspeechstart: FakeHandler = null;
  onspeechend: FakeHandler = null;
  started = 0;
  stopped = 0;
  aborted = 0;
  start() {
    this.started += 1;
  }
  stop() {
    this.stopped += 1;
  }
  abort() {
    this.aborted += 1;
  }
  emitStart() {
    this.onstart?.(new Event('start'));
  }
  emitEnd() {
    this.onend?.(new Event('end'));
  }
  emitResult(transcripts: Array<{ text: string; isFinal: boolean }>) {
    const results = transcripts.map((t) => ({
      isFinal: t.isFinal,
      length: 1,
      item: () => ({ transcript: t.text, confidence: 1 }),
      0: { transcript: t.text, confidence: 1 },
    }));
    // The DOM lib's SpeechRecognitionEvent extends Event, so a bare object
    // literal can't satisfy it — assert through unknown.
    const ev = {
      resultIndex: 0,
      results: {
        ...results,
        length: results.length,
        item: (i: number) => results[i],
      },
    } as unknown as SpeechRecognitionEvent;
    this.onresult?.call(this, ev);
  }
  emitError(code: string) {
    const ev = { error: code, message: code } as unknown as SpeechRecognitionErrorEvent;
    this.onerror?.call(this, ev);
  }
}

function installFakes(options: { supported?: boolean; synth?: boolean } = {}) {
  const { supported = true, synth: hasSynth = true } = options;
  const instances: FakeRecognition[] = [];
  const Ctor = class extends FakeRecognition {
    constructor() {
      super();
      instances.push(this);
    }
  } as unknown as SpeechRecognitionConstructor;

  const spoken: string[] = [];
  const cancelled = vi.fn();
  // Loose utterance shape so the test doesn't need lib.dom's full
  // SpeechSynthesisUtterance/SpeechSynthesisEvent interfaces.
  interface FakeUtterance {
    text: string;
    rate: number;
    pitch: number;
    volume: number;
    onend: ((ev: Event) => void) | null;
    onerror: ((ev: Event) => void) | null;
  }
  const utterances: FakeUtterance[] = [];
  const speak = vi.fn((u: FakeUtterance) => {
    spoken.push(u.text);
    // fire onend immediately so 'speaking' returns to idle deterministically
    setTimeout(() => u.onend?.(new Event('end')), 0);
  });

  const fakeSynth = hasSynth
    ? {
        speak,
        cancel: cancelled,
        getUtterances: () => utterances,
      }
    : undefined;

  Object.defineProperty(window, 'SpeechRecognition', { value: supported ? Ctor : undefined, configurable: true });
  Object.defineProperty(window, 'webkitSpeechRecognition', { value: supported ? Ctor : undefined, configurable: true });
  Object.defineProperty(window, 'speechSynthesis', { value: fakeSynth, configurable: true });

  // speechSynthesisUtterance — happy-dom lacks it; construct a fake.
  (globalThis as Record<string, unknown>).SpeechSynthesisUtterance = class {
    text: string;
    rate = 1;
    pitch = 1;
    volume = 1;
    onend: ((ev: Event) => void) | null = null;
    onerror: ((ev: Event) => void) | null = null;
    constructor(text: string) {
      this.text = text;
      utterances.push(this as unknown as FakeUtterance);
    }
  };

  return { instances, spoken, speak, cancelled, utterances };
}

function installPermission(state: 'granted' | 'denied' | 'prompt' | undefined) {
  Object.defineProperty(navigator, 'permissions', {
    value: {
      query: vi.fn(() =>
        Promise.resolve({ state: state ?? 'prompt', onchange: null, addEventListener: vi.fn() }),
      ),
    },
    configurable: true,
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  // Default: no recognizer and no speechSynthesis (the common CI state).
  Object.defineProperty(window, 'SpeechRecognition', { value: undefined, configurable: true });
  Object.defineProperty(window, 'webkitSpeechRecognition', { value: undefined, configurable: true });
  Object.defineProperty(window, 'speechSynthesis', { value: undefined, configurable: true });
});

describe('VoiceEngine feature detection', () => {
  it('reports supported=false when Web Speech is absent', () => {
    const engine = new VoiceEngine();
    expect(engine.supported).toBe(false);
  });

  it('reports supported=true when webkitSpeechRecognition exists', () => {
    installFakes({ supported: true });
    const engine = new VoiceEngine();
    expect(engine.supported).toBe(true);
  });

  it('reports mic-denied when the permissions API says denied', async () => {
    installFakes({ supported: true });
    installPermission('denied');
    const engine = new VoiceEngine();
    await vi.waitFor(() => expect(engine.getMicStatus()).toBe('denied'));
  });

  it('stays unknown when the permissions API is absent', () => {
    installFakes({ supported: true });
    Object.defineProperty(navigator, 'permissions', { value: undefined, configurable: true });
    const engine = new VoiceEngine();
    expect(engine.getMicStatus()).toBe('unknown');
  });
});

describe('VoiceEngine speech-to-text', () => {
  it('delivers a final transcript and emits listening state', () => {
    const fakes = installFakes({ supported: true });
    const transcripts: string[] = [];
    const listening: boolean[] = [];
    const engine = new VoiceEngine({
      onTranscript: (t) => transcripts.push(t),
      onListeningChange: (l) => listening.push(l),
    });
    engine.start();
    const rec = fakes.instances[0];
    expect(rec).toBeDefined();
    expect(rec.lang).toBe('en-US');
    expect(rec.continuous).toBe(false);
    expect(rec.interimResults).toBe(true);
    rec.emitStart();
    expect(listening.at(-1)).toBe(true);
    rec.emitResult([{ text: 'hello there', isFinal: true }]);
    rec.emitEnd();
    expect(transcripts).toEqual(['hello there']);
    expect(listening.at(-1)).toBe(false);
  });

  it('discards interim (non-final) results', () => {
    const fakes = installFakes({ supported: true });
    const transcripts: string[] = [];
    const engine = new VoiceEngine({ onTranscript: (t) => transcripts.push(t) });
    engine.start();
    fakes.instances[0].emitResult([
      { text: 'partial', isFinal: false },
      { text: 'final text', isFinal: true },
    ]);
    expect(transcripts).toEqual(['final text']);
  });

  it('reports recognition failure for no-speech', () => {
    const fakes = installFakes({ supported: true });
    const errors: Array<{ kind: string; code: string }> = [];
    const engine = new VoiceEngine({ onError: (kind, code) => errors.push({ kind, code }) });
    engine.start();
    fakes.instances[0].emitError('no-speech');
    expect(errors).toEqual([{ kind: 'recognition-failed', code: 'no-speech' }]);
  });

  it('reports mic-denied for not-allowed', () => {
    const fakes = installFakes({ supported: true });
    const errors: Array<{ kind: string; code: string }> = [];
    const engine = new VoiceEngine({ onError: (kind, code) => errors.push({ kind, code }) });
    engine.start();
    fakes.instances[0].emitError('not-allowed');
    expect(errors[0].kind).toBe('mic-denied');
  });

  it('ignores aborted errors (our own stop())', () => {
    const fakes = installFakes({ supported: true });
    const errors: string[] = [];
    const engine = new VoiceEngine({ onError: (kind) => errors.push(kind) });
    engine.start();
    fakes.instances[0].emitError('aborted');
    expect(errors).toHaveLength(0);
  });

  it('stop() aborts the recognizer', () => {
    const fakes = installFakes({ supported: true });
    const engine = new VoiceEngine();
    engine.start();
    engine.stop();
    expect(fakes.instances[0].aborted).toBe(1);
  });
});

describe('VoiceEngine text-to-speech', () => {
  it('speaks text and returns to idle on end', async () => {
    const fakes = installFakes({ supported: true, synth: true });
    const speaking: boolean[] = [];
    const engine = new VoiceEngine({ onSpeakingChange: (s) => speaking.push(s) });
    engine.speak('Hello');
    expect(fakes.speak).toHaveBeenCalledTimes(1);
    expect(fakes.spoken).toEqual(['Hello']);
    expect(speaking.at(-1)).toBe(true);
    await vi.waitFor(() => expect(speaking.at(-1)).toBe(false));
  });

  it('cancelSpeech cancels synthesis', () => {
    const fakes = installFakes({ supported: true, synth: true });
    const engine = new VoiceEngine();
    engine.speak('Hello');
    engine.cancelSpeech();
    expect(fakes.cancelled).toHaveBeenCalled();
  });

  it('does nothing when speechSynthesis is absent', () => {
    installFakes({ supported: true, synth: false });
    const speaking: boolean[] = [];
    const engine = new VoiceEngine({ onSpeakingChange: (s) => speaking.push(s) });
    engine.speak('Hello');
    expect(speaking).toHaveLength(0);
  });
});
