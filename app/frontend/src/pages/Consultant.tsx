import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { transcriptFromTurn } from '../lib/transcript';
import type { TranscriptMessage } from '../lib/types';
import { ChatTranscript } from '../components/ChatTranscript';
import { InlineSpinner } from '../components/Spinner';
import { ErrorBanner } from '../components/ErrorBanner';
import { Bot, Send, ShieldCheck, Sparkles, RotateCcw } from 'lucide-react';

/** Suggested opening questions — each prompts the consultant to use the tools. */
const SUGGESTED_QUESTIONS = [
  'Assess a manufacturing company with $250M revenue, 120k customer records, partial MFA and basic segmentation',
  'What is the expected annual loss for a healthcare firm with 10M patient records and weak controls?',
  'Run the loss model and show me EAL, VaR 95 and Expected Shortfall',
  'Model the impact of implementing strong MFA and network segmentation',
  'Test a $10M limit with a $250k retention against my exposure',
  'What are the top risk drivers for a financial services firm with high third-party dependency?',
];

export default function Consultant() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState('deepseek-chat');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize the input as the user types.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }, [input]);

  // Create the session once on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await api.chat.createSession();
        if (!cancelled) setSessionId(s.session_id);
      } catch {
        if (!cancelled) setError('Could not start a consultant session. Is the API running?');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const scrollToEnd = useCallback(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, []);

  useEffect(() => {
    scrollToEnd();
  }, [messages, sending, scrollToEnd]);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !sessionId || sending) return;
      setSending(true);
      setError(null);
      setInput('');
      setMessages((prev) => [...prev, { role: 'user', content: trimmed, toolTrace: [] }]);

      try {
        const res = await api.chat.turn(sessionId, { message: trimmed });
        setModel(res.model);
        // Rebuild the transcript from the server so the UI never holds a
        // divergent copy of the conversation.
        setMessages(transcriptFromTurn(res.history, res.tool_trace, res.safety));
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Something went wrong';
        setError(msg);
        // Re-add the user message so they can retry.
        setMessages((prev) => [...prev, { role: 'assistant', content: `⚠️ ${msg}`, toolTrace: [] }]);
      } finally {
        setSending(false);
      }
    },
    [sessionId, sending],
  );

  const newSession = useCallback(async () => {
    try {
      if (sessionId) await api.chat.deleteSession(sessionId).catch(() => {});
    } catch {
      /* ignore */
    }
    setMessages([]);
    setError(null);
    setInput('');
    const s = await api.chat.createSession();
    setSessionId(s.session_id);
  }, [sessionId]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-ink-200 bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-ink-950 text-brand-400">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-ink-900">Cyber Risk Consultant</div>
            <div className="flex items-center gap-1.5 text-[11px] text-ink-500">
              <span className="h-1.5 w-1.5 rounded-full bg-risk-low" />
              Senior consultant · {model}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={newSession}
          className="inline-flex items-center gap-1.5 rounded-lg border border-ink-300 px-3 py-1.5 text-xs font-medium text-ink-600 transition-colors hover:border-brand-500 hover:text-brand-600"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          New conversation
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-lg pt-8 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-ink-950 text-brand-400">
              <Bot className="h-6 w-6" />
            </div>
            <h2 className="mt-4 text-lg font-semibold text-ink-900">How can I help with your cyber exposure?</h2>
            <p className="mt-1 text-sm text-ink-500">
              I'm a senior cyber risk consultant. I'll ask a few targeted questions, then run the
              quantitative model to size your loss and structure your insurance.
            </p>

            <div className="mt-6 grid gap-2 text-left">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Suggested questions</div>
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => void send(q)}
                  className="tappable rounded-lg border border-ink-200 bg-white px-3.5 py-2.5 text-left text-sm text-ink-700 transition-colors hover:border-brand-500/50 hover:bg-brand-50 hover:text-ink-900"
                >
                  <span className="flex items-start gap-2">
                    <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-500" />
                    {q}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        <ChatTranscript
          messages={messages}
          sending={sending}
          animateRows
          typingLabel="Consultant is working…"
        />

        {error && (
          <ErrorBanner message={error} onRetry={() => setError(null)} />
        )}

        <div ref={endRef} />
      </div>

      {/* Input */}
      <form onSubmit={onSubmit} className="border-t border-ink-200 bg-white px-6 py-4">
        <div className="flex items-end gap-3">
          <div className="relative flex-1">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              rows={1}
              aria-label="Message the consultant"
              placeholder="Describe a company, ask for a loss model, or test an insurance structure…"
              className="max-h-32 w-full resize-none rounded-xl border border-ink-300 bg-white px-4 py-2.5 text-sm text-ink-900 outline-none transition-colors placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            />
          </div>
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-brand-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {sending ? <InlineSpinner /> : <Send className="h-4 w-4" />}
            Send
          </button>
        </div>
        <p className="mt-2 text-[11px] text-ink-400">
          The consultant uses the CyberRisk Monte Carlo engine for every figure — it never invents results.
        </p>
      </form>
    </div>
  );
}
