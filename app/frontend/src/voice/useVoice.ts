/**
 * Voice state-machine hook: wires the VoiceEngine to the chat hook.
 *
 * Displayed state (idle / listening / thinking / speaking) is DERIVED from the
 * engine's listening/speaking flags plus the chat `sending` flag, so a
 * recognition `onend` racing an in-flight assistant reply cannot wedge the UI
 * into a wrong state.  TTS is only started by the component (in an effect) so
 * the engine and the React tree never diverge.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { VoiceEngine } from './speech';
import type { MicStatus, VoiceErrorKind } from './speech';

export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface UseVoiceOptions {
  /** Called with a final recognized transcript when the user finishes speaking. */
  onTranscript: (text: string) => void;
  /** Fired when the engine reports a mic-denied or recognition failure. */
  onError: (kind: VoiceErrorKind, code: string) => void;
}

export function useVoice({ onTranscript, onError }: UseVoiceOptions) {
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [micStatus, setMicStatus] = useState<MicStatus>('unknown');

  // Latest callbacks in a ref so the engine's event handlers always see the
  // current closures without being recreated.
  const cbRef = useRef({ onTranscript, onError });
  cbRef.current = { onTranscript, onError };

  const engine = useMemo(
    () =>
      new VoiceEngine({
        onListeningChange: (v) => setListening(v),
        onSpeakingChange: (v) => setSpeaking(v),
        onTranscript: (text) => cbRef.current.onTranscript(text),
        onMicStatusChange: (s) => setMicStatus(s),
        onError: (kind, code) => cbRef.current.onError(kind, code),
      }),
    [],
  );

  // Reflect the engine's mic status after the async permission query settles.
  useEffect(() => {
    setMicStatus(engine.getMicStatus());
  }, [engine]);

  const startListening = () => {
    engine.cancelSpeech();
    setMicStatus(engine.getMicStatus());
    engine.start();
  };

  const stopListening = () => {
    engine.stop();
  };

  const cancelSpeech = () => {
    engine.cancelSpeech();
  };

  useEffect(() => () => engine.stop(), [engine]);

  return {
    engine,
    micStatus,
    listening,
    speaking,
    startListening,
    stopListening,
    cancelSpeech,
  };
}

/** Derive the single display state from listening/speaking/thinking flags. */
export function deriveVoiceState(opts: {
  listening: boolean;
  speaking: boolean;
  thinking: boolean;
}): VoiceState {
  if (opts.speaking) return 'speaking';
  if (opts.listening) return 'listening';
  if (opts.thinking) return 'thinking';
  return 'idle';
}

/** Human-readable label for the status chip / aria-live region. */
export function voiceStateLabel(state: VoiceState): string {
  switch (state) {
    case 'listening':
      return 'Listening…';
    case 'thinking':
      return 'Consultant is thinking…';
    case 'speaking':
      return 'Speaking…';
    default:
      return 'Tap to speak';
  }
}

/** Human-readable mic-status label (overrides the state label when relevant). */
export function micStatusLabel(status: MicStatus): string {
  switch (status) {
    case 'granted':
      return 'Microphone ready';
    case 'denied':
      return 'Microphone denied — enable access to use voice';
    default:
      return 'Tap to speak';
  }
}
