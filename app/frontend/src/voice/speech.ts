/**
 * Thin bridge over the Web Speech API (speech recognition + synthesis).
 *
 * This is the ONLY module that touches `SpeechRecognition` / `speechSynthesis`,
 * so every other file in the voice client can be tested against a mock.  It is
 * deliberately a dumb bridge — it exposes listening/speaking flags and event
 * callbacks and holds NO UI state machine.  The component derives the displayed
 * state from those flags, which avoids races between recognition `onend` and an
 * in-flight assistant reply.
 *
 * No recognition logic, no risk-model knowledge — it just maps browser speech
 * events to callbacks.
 */

/**
 * Web Speech typing.  TypeScript's DOM lib already ships the *event/result*
 * types (`SpeechRecognitionEvent`, `SpeechRecognitionErrorEvent`,
 * `SpeechRecognitionResult`, …) but NOT the recognizer interface or its
 * `window` property.  We declare only those missing pieces here (in a module,
 * because tsc -b drops unreferenced sibling .d.ts files from the program).
 */
declare global {
  /** The subset of the browser SpeechRecognition API the voice client uses. */
  interface ISpeechRecognition {
    lang: string;
    continuous: boolean;
    interimResults: boolean;
    maxAlternatives: number;
    start(): void;
    stop(): void;
    abort(): void;
    onstart: ((this: ISpeechRecognition, ev: Event) => void) | null;
    onend: ((this: ISpeechRecognition, ev: Event) => void) | null;
    onresult: ((this: ISpeechRecognition, ev: SpeechRecognitionEvent) => void) | null;
    onerror: ((this: ISpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null;
    onaudiostart: ((this: ISpeechRecognition, ev: Event) => void) | null;
    onaudioend: ((this: ISpeechRecognition, ev: Event) => void) | null;
    onnomatch: ((this: ISpeechRecognition, ev: SpeechRecognitionEvent) => void) | null;
    onsoundstart: ((this: ISpeechRecognition, ev: Event) => void) | null;
    onsoundend: ((this: ISpeechRecognition, ev: Event) => void) | null;
    onspeechstart: ((this: ISpeechRecognition, ev: Event) => void) | null;
    onspeechend: ((this: ISpeechRecognition, ev: Event) => void) | null;
  }

  interface SpeechRecognitionConstructor {
    new (): ISpeechRecognition;
  }

  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

export type MicStatus = 'granted' | 'denied' | 'unknown';

export type VoiceErrorKind = 'mic-denied' | 'recognition-failed';

export interface VoiceCallbacks {
  /** True while the recognizer is listening for a user utterance. */
  onListeningChange?: (listening: boolean) => void;
  /** True while text is being read aloud by speech synthesis. */
  onSpeakingChange?: (speaking: boolean) => void;
  /** Fired with a FINAL speech recognition transcript (a full utterance). */
  onTranscript?: (text: string) => void;
  /** Fired when the async microphone permission query settles. */
  onMicStatusChange?: (status: MicStatus) => void;
  /**
   * Fired on recognition failure.  `code` is the raw browser error code.
   *   - kind 'mic-denied'          → permission rejected
   *   - kind 'recognition-failed'  → could not hear / network / no audio
   */
  onError?: (kind: VoiceErrorKind, code: string) => void;
}

/** Categorise a raw SpeechRecognition error code into a stable kind. */
function classifyError(code: string): VoiceErrorKind {
  if (code === 'not-allowed' || code === 'service-not-allowed') return 'mic-denied';
  return 'recognition-failed';
}

function getRecognitionCtor(): SpeechRecognitionConstructor | undefined {
  if (typeof window === 'undefined') return undefined;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition;
}

function synth(): SpeechSynthesis | undefined {
  return typeof window !== 'undefined' ? window.speechSynthesis : undefined;
}

export class VoiceEngine {
  /** Recognition available (gates the microphone path). */
  readonly supported: boolean;

  private readonly callbacks: VoiceCallbacks;
  private recognizer: ISpeechRecognition | null = null;
  private micStatus: MicStatus = 'unknown';
  private utterance: SpeechSynthesisUtterance | null = null;
  private listening = false;

  constructor(callbacks: VoiceCallbacks = {}) {
    this.callbacks = callbacks;
    this.supported = Boolean(getRecognitionCtor());
    if (
      typeof navigator !== 'undefined' &&
      navigator.permissions &&
      typeof navigator.permissions.query === 'function'
    ) {
      void navigator.permissions
        .query({ name: 'microphone' as PermissionName })
        .then((status) => {
          this.micStatus =
            status.state === 'granted' ? 'granted' : status.state === 'denied' ? 'denied' : 'unknown';
          this.callbacks.onMicStatusChange?.(this.micStatus);
        })
        .catch(() => {
          /* Permissions API rejected the query — leave micStatus 'unknown'. */
        });
    }
  }

  getMicStatus(): MicStatus {
    return this.micStatus;
  }

  /**
   * Start listening.  Call from a user gesture so the browser allows the
   * microphone prompt (iOS requires this).
   */
  start(): void {
    if (!this.supported) {
      this.callbacks.onError?.('recognition-failed', 'unsupported');
      return;
    }
    this.cancelSpeech();
    const rec = this.ensureRecognizer();
    if (!rec) {
      this.callbacks.onError?.('recognition-failed', 'unsupported');
      return;
    }
    try {
      rec.start();
    } catch {
      /* Already started or browser refused — report as recognition failure. */
      this.callbacks.onError?.('recognition-failed', 'not-started');
    }
  }

  /** Stop listening (abort recognition; cancel any TTS). */
  stop(): void {
    this.cancelSpeech();
    if (this.recognizer) {
      try {
        this.recognizer.abort();
      } catch {
        /* ignore */
      }
    }
    // The browser fires onend after abort() in practice, but we clear the flag
    // deterministically so the UI never wedges in a listening state.
    if (this.listening) {
      this.listening = false;
      this.callbacks.onListeningChange?.(false);
    }
  }

  /** Read `text` aloud.  Fires onSpeakingChange(true), then false on end. */
  speak(text: string): void {
    const s = synth();
    if (!s || !text.trim()) return;
    this.cancelSpeech();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;
    this.utterance = utterance;
    this.callbacks.onSpeakingChange?.(true);
    const finish = () => {
      this.utterance = null;
      this.callbacks.onSpeakingChange?.(false);
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    s.speak(utterance);
  }

  /** Interrupt any in-progress speech immediately. */
  cancelSpeech(): void {
    const s = synth();
    if (s) s.cancel();
    if (this.utterance) {
      this.utterance = null;
      this.callbacks.onSpeakingChange?.(false);
    }
  }

  private ensureRecognizer(): ISpeechRecognition | null {
    if (this.recognizer) return this.recognizer;
    const Ctor = getRecognitionCtor();
    if (!Ctor) return null;

    const rec = new Ctor();
    rec.lang = 'en-US';
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      this.listening = true;
      this.callbacks.onListeningChange?.(true);
    };
    rec.onend = () => {
      if (this.listening) {
        this.listening = false;
        this.callbacks.onListeningChange?.(false);
      }
    };
    rec.onresult = (event) => {
      // Only final transcripts are sent upstream — interim results are
      // discarded so the user sees one clean message per utterance.
      let finalText = '';
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal && result.length > 0) {
          finalText += result[0].transcript;
        }
      }
      const trimmed = finalText.trim();
      if (trimmed) this.callbacks.onTranscript?.(trimmed);
    };
    rec.onerror = (event) => {
      // 'aborted' is our own stop() — not a user-facing failure.
      if (event.error === 'aborted') return;
      const kind = classifyError(event.error);
      if (kind === 'mic-denied') this.micStatus = 'denied';
      this.callbacks.onError?.(kind, event.error);
    };

    this.recognizer = rec;
    return rec;
  }
}
