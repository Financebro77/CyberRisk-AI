import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { transcriptFromSession, transcriptFromTurn } from '../lib/transcript';
import type { ChatSession, TranscriptMessage } from '../lib/types';
import { ChatTranscript } from '../components/ChatTranscript';
import ChatSidebar from '../components/ChatSidebar';
import { InlineSpinner } from '../components/Spinner';
import { ErrorBanner } from '../components/ErrorBanner';
import {
  addConversationId,
  loadActiveConversation,
  loadConversationIds,
  removeConversationId,
  saveActiveConversation,
  sortByNewest,
} from '../lib/chatSessions';
import { Bot, Send, ShieldCheck, Sparkles } from 'lucide-react';

/** Suggested opening questions — each prompts the consultant to use the tools. */
const SUGGESTED_QUESTIONS = [
  'Assess a manufacturing company with $250M revenue, 120k customer records, partial MFA and basic segmentation',
  'What is the expected annual loss for a healthcare firm with 10M patient records and weak controls?',
  'Run the loss model and show me EAL, VaR 95 and Expected Shortfall',
  'Model the impact of implementing strong MFA and network segmentation',
  'Test a $10M limit with a $250k retention against my exposure',
  'What are the top risk drivers for a financial services firm with high third-party dependency?',
];

/**
 * Sidebar auto-title, mirroring the backend's rule (first user message,
 * collapsed, capped at 48 chars) so the list reads correctly between reloads
 * (the server's authoritative title wins on the next mount).
 */
function titleFor(history: Array<{ role: string; content: string }>): string {
  const first = history.find((m) => m.role === 'user')?.content;
  if (!first) return 'New conversation';
  const collapsed = first.split(/\s+/).join(' ').trim();
  return collapsed ? collapsed.slice(0, 48) : 'New conversation';
}

function EmptyState({ onSend }: { onSend: (text: string) => void }) {
  return (
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
            onClick={() => onSend(q)}
            className="tappable rounded-lg border border-ink-200 bg-ink-100 px-3.5 py-2.5 text-left text-sm text-ink-700 transition-colors hover:border-accent/40 hover:bg-accent/10 hover:text-accent"
          >
            <span className="flex items-start gap-2">
              <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-500" />
              {q}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function Consultant() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState('deepseek-chat');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // Guards StrictMode's double-mount so a fresh page never creates two sessions.
  const creatingRef = useRef(false);

  // Auto-resize the input as the user types.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  }, [input]);

  const scrollToEnd = useCallback(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, []);

  useEffect(() => {
    scrollToEnd();
  }, [messages, sending, scrollToEnd]);

  /** Create a fresh backend session and make it the active one. */
  const createNewSession = useCallback(async () => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const s = await api.chat.createSession();
      const entry: ChatSession = {
        session_id: s.session_id,
        title: 'New conversation',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        history: [],
      };
      setSessions((prev) => [...prev, entry]);
      addConversationId(s.session_id);
      saveActiveConversation(s.session_id);
      setSessionId(s.session_id);
      setMessages([]);
    } catch {
      setError('Could not start a consultant session. Is the API running?');
    } finally {
      creatingRef.current = false;
      setLoading(false);
    }
  }, []);

  /** Open a persisted conversation: fetch its full history and render it. */
  const openSession = useCallback(
    async (sid: string) => {
      setLoading(true);
      setError(null);
      try {
        const s = await api.chat.getSession(sid);
        setSessionId(s.session_id);
        setMessages(transcriptFromSession(s));
        saveActiveConversation(s.session_id);
        setSessions((prev) => {
          const others = prev.filter((x) => x.session_id !== s.session_id);
          return [...others, s];
        });
      } catch (err) {
        const status = err instanceof Error ? (err as { status?: number }).status : undefined;
        if (status === 404) {
          // Session vanished server-side — drop it from the owned list.
          removeConversationId(sid);
          setSessions((prev) => prev.filter((x) => x.session_id !== sid));
          if (sid === sessionId) {
            setSessionId(null);
            setMessages([]);
          }
        } else {
          // Transient failure (network/engine): keep the session so a blip
          // never prunes a healthy conversation; let the user retry.
          setError('Could not open this conversation. Please try again.');
        }
      } finally {
        setLoading(false);
      }
    },
    [sessionId],
  );

  // Restore on mount: the active conversation if owned, else the most recent,
  // else a brand-new session.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ids = loadConversationIds();
      if (ids.length === 0) {
        await createNewSession();
        return;
      }
      try {
        const { sessions: list } = await api.chat.listSessions(ids);
        if (cancelled) return;
        const active = loadActiveConversation();
        const target =
          list.find((s) => s.session_id === active) ?? sortByNewest(list)[0];
        if (target) {
          setSessions(list);
          setSessionId(target.session_id);
          setMessages(transcriptFromSession(target));
          saveActiveConversation(target.session_id);
        } else {
          // Every known id is stale server-side; start clean.
          await createNewSession();
        }
      } catch {
        if (!cancelled) await createNewSession();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [createNewSession]);

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
        // Refresh the sidebar row: the server auto-titles from the first user
        // message (mirrored here); the authoritative title re-syncs on reload.
        const title = titleFor(res.history);
        setSessions((prev) =>
          prev.map((s) =>
            s.session_id === sessionId
              ? { ...s, title, updated_at: new Date().toISOString() }
              : s,
          ),
        );
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

  /** Start a brand-new chat.  The previous conversation is KEPT (persisted +
   *  listed in the sidebar) — "New chat" never deletes history. */
  const newChat = useCallback(async () => {
    setError(null);
    await createNewSession();
  }, [createNewSession]);

  /** Delete a conversation server-side and from the owned list. */
  const handleDelete = useCallback(
    async (sid: string) => {
      Promise.resolve(api.chat.deleteSession(sid)).catch(() => {
        /* server-side session already gone — best-effort */
      });
      removeConversationId(sid);
      const remaining = sessions.filter((s) => s.session_id !== sid);
      setSessions(remaining);
      if (sid === sessionId) {
        setSessionId(null);
        setMessages([]);
        if (remaining.length > 0) {
          await openSession(sortByNewest(remaining)[0].session_id);
        } else {
          await createNewSession();
        }
      }
    },
    [sessionId, sessions, openSession, createNewSession],
  );

  const handleSelect = useCallback(
    (sid: string) => {
      if (sid === sessionId) return;
      void openSession(sid);
    },
    [sessionId, openSession],
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  const activeTitle = sessions.find((s) => s.session_id === sessionId)?.title;

  return (
    <div className="flex h-full">
      <ChatSidebar
        sessions={sessions}
        activeId={sessionId}
        onSelect={handleSelect}
        onNewChat={() => void newChat()}
        onDelete={(sid) => void handleDelete(sid)}
      />

      <div className="flex min-w-0 flex-1 flex-col bg-ink-50">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-ink-200 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-ink-950 text-brand-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-semibold text-ink-900">
                {activeTitle || 'Cyber Risk Consultant'}
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-ink-500">
                <span className="h-1.5 w-1.5 rounded-full bg-risk-low" />
                Senior consultant · {model}
              </div>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
          {error && <ErrorBanner message={error} onRetry={() => setError(null)} />}
          {loading ? (
            <div className="flex justify-center py-16 text-ink-400">
              <InlineSpinner />
            </div>
          ) : messages.length === 0 ? (
            <EmptyState onSend={send} />
          ) : (
            <ChatTranscript
              messages={messages}
              sending={sending}
              animateRows
              typingLabel="Consultant is working…"
            />
          )}
          <div ref={endRef} />
        </div>

        {/* Input */}
        <form onSubmit={onSubmit} className="border-t border-ink-200 bg-ink-50 px-6 py-4">
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
                className="field max-h-32 resize-none px-4 py-2.5 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
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
            The consultant uses the Armageddon Monte Carlo engine for every figure — it never invents results.
          </p>
        </form>
      </div>
    </div>
  );
}
