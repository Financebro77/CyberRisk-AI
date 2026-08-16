/**
 * The single-screen, voice-first AI consultant.
 *
 * On open the user sees only: the "CyberRisk AI" title, the prompt
 * "How can I help you assess your cyber risk?", and a microphone button.
 * The conversation is a thin chat shell over the backend agent — this screen
 * NEVER computes risk, holds LLM credentials, or persists the conversation.
 * All conversation state lives in React memory (no localStorage).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, MicOff, Send, ShieldCheck, Eraser, CircleStop, Bot, Sparkles } from 'lucide-react';
import { ChatTranscript } from '../components/ChatTranscript';
import { useChat, RECOGNITION_FAILURE } from './useChat';
import { useVoice, deriveVoiceState, voiceStateLabel, micStatusLabel } from './useVoice';
import type { VoiceErrorKind } from './speech';

/** Map a voice-engine error kind to the exact user-facing string. */
function voiceErrorMessage(kind: VoiceErrorKind): string {
  return kind === 'mic-denied' ? 'Microphone denied — enable access to use voice' : RECOGNITION_FAILURE;
}

export function VoiceConsultant() {
  const chat = useChat();
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const lastAssistantRef = useRef<string>('');

  const handleTranscript = useCallback(
    (text: string) => {
      setVoiceError(null);
      void chat.send(text);
    },
    [chat],
  );

  const handleVoiceError = useCallback((kind: VoiceErrorKind) => {
    setVoiceError(voiceErrorMessage(kind));
  }, []);

  const voice = useVoice({ onTranscript: handleTranscript, onError: handleVoiceError });

  // Speak the newest assistant message aloud, and remember it so re-renders
  // (e.g. error-state flips) don't re-read it.
  const latestAssistant = chat.messages.findLast((m) => m.role === 'assistant');
  const latestText = latestAssistant?.content ?? '';
  useEffect(() => {
    if (
      latestText &&
      latestText !== lastAssistantRef.current &&
      !chat.sending &&
      voice.engine.supported
    ) {
      lastAssistantRef.current = latestText;
      voice.engine.speak(latestText);
    }
  }, [latestText, chat.sending, voice.engine]);

  // Displayed state is derived (see useVoice): `sending` is the 'thinking'
  // input, so no extra state mirror is needed here.
  const voiceState = deriveVoiceState({
    listening: voice.listening,
    speaking: voice.speaking,
    thinking: chat.sending,
  });

  const micActive = voiceState === 'listening';
  const isBusy = voiceState === 'thinking' || voiceState === 'speaking';
  const canSend = chat.sessionId !== null && !isBusy;

  const onMicClick = () => {
    if (voiceState === 'listening') {
      voice.stopListening();
      return;
    }
    if (voiceState === 'speaking') {
      voice.cancelSpeech();
    }
    setVoiceError(null);
    voice.startListening();
  };

  const displayError = chat.error ?? voiceError;

  return (
    <div className="flex h-dvh flex-col bg-ink-50 text-ink-900">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-ink-200 bg-white px-5 pb-3 pt-[max(env(safe-area-inset-top),0.75rem)]">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink-950 text-brand-400">
            <ShieldCheck className="h-4.5 w-4.5" />
          </div>
          <div>
            <div className="text-sm font-semibold leading-tight text-ink-900">CyberRisk AI</div>
            <div className="flex items-center gap-1.5 text-[11px] text-ink-500">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  micActive ? 'bg-risk-high' : voice.micStatus === 'denied' ? 'bg-risk-med' : 'bg-ink-300'
                }`}
              />
              {voiceState === 'idle' && voice.micStatus === 'denied'
                ? micStatusLabel('denied')
                : voiceStateLabel(voiceState)}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            voice.cancelSpeech();
            void chat.endSession();
          }}
          aria-label="End session"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-ink-300 px-3 py-1.5 text-xs font-medium text-ink-600 transition-colors hover:border-brand-500 hover:text-brand-600"
        >
          <CircleStop className="h-3.5 w-3.5" />
          End session
        </button>
      </header>

      {/* Transcript */}
      <main className="flex-1 overflow-y-auto px-5 py-4">
        <div aria-live="polite" className="space-y-4">
          {chat.messages.length === 0 && !chat.sending && (
            <div className="mx-auto max-w-sm pt-12 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-ink-950 text-brand-400">
                <Bot className="h-7 w-7" />
              </div>
              <h2 className="mt-4 text-lg font-semibold text-ink-900">
                How can I help you assess your cyber risk?
              </h2>
              <p className="mt-1.5 text-sm text-ink-500">
                Ask about a company, get a loss model, or test an insurance structure — just
                speak, or type. I'll ask for whatever I need before I model your exposure.
              </p>
            </div>
          )}

          <ChatTranscript messages={chat.messages} sending={chat.sending} bubbleWidth="max-w-[84%]" />

          {displayError && (
            <div
              role="alert"
              className="card panel-in border-risk-high/30 bg-risk-high/5 px-4 py-3 text-sm text-ink-700"
            >
              {displayError}
            </div>
          )}

          {chat.privacyNotice && (
            <div className="rounded-lg border border-ink-200 bg-white px-3 py-2 text-xs text-ink-500">
              {chat.privacyNotice}
            </div>
          )}
        </div>
      </main>

      {/* Input */}
      <footer className="shrink-0 border-t border-ink-200 bg-white px-5 pb-[max(env(safe-area-inset-bottom),1rem)] pt-3">
        <div className="flex items-end gap-3">
          <button
            type="button"
            onClick={onMicClick}
            disabled={!voice.engine.supported || isBusy}
            aria-label={micActive ? 'Stop listening' : 'Speak to the consultant'}
            className={`tappable relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
              micActive
                ? 'bg-risk-high text-white'
                : 'bg-ink-950 text-brand-400 hover:bg-ink-800'
            }`}
          >
            {micActive ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
          </button>
          <input
            value={chat.inputValue}
            onChange={(e) => chat.setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                const text = chat.inputValue.trim();
                if (text) void chat.send(text);
              }
            }}
            aria-label="Type a message"
            placeholder="Or type a question…"
            className="min-h-11 flex-1 rounded-xl border border-ink-300 bg-white px-4 py-2.5 text-sm text-ink-900 outline-none transition-colors placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
          />
          <button
            type="button"
            onClick={() => {
              const text = chat.inputValue.trim();
              if (text) void chat.send(text);
            }}
            disabled={!canSend || !chat.inputValue.trim()}
            aria-label="Send message"
            className="inline-flex h-11 shrink-0 items-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            Send
          </button>
        </div>

        <div className="mt-2.5 flex items-center justify-between gap-2 text-[11px] text-ink-400">
          <span className="flex items-center gap-1">
            <Sparkles className="h-3 w-3" />
            Powered by the CyberRisk engine — no figures are invented.
          </span>
          <button
            type="button"
            onClick={() => {
              voice.cancelSpeech();
              chat.clearConversation();
            }}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 font-medium text-ink-500 transition-colors hover:bg-ink-100 hover:text-ink-700"
            aria-label="Clear conversation"
          >
            <Eraser className="h-3 w-3" />
            Clear
          </button>
        </div>

        {voiceError && (
          <p role="alert" className="mt-2 text-xs text-risk-high">
            {voiceError}
          </p>
        )}
      </footer>
    </div>
  );
}
