/**
 * Thin chat-shell hook for the voice consultant.
 *
 * The client holds NO risk logic — every turn is relayed to the backend
 * `/api/chat/*` endpoints and the transcript is rebuilt from the server's
 * authoritative `history`.  State lives only in React memory: conversations
 * are never written to localStorage/sessionStorage, and "End session" issues
 * a DELETE so the in-memory backend session is discarded too.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import type { ChatToolTrace } from '../lib/types';

/** Exact user-facing error strings — exported so UI and tests share them. */
export const BACKEND_UNAVAILABLE =
  'The CyberRisk AI service is currently unavailable. Please try again.';
export const RECOGNITION_FAILURE = "I couldn't hear that clearly. Please try again.";
export const INSUFFICIENT_MODEL_INFO =
  'I need a little more information before I can calculate the risk.';

/** A chat message the voice client renders. */
export interface VoiceMessage {
  role: 'user' | 'assistant';
  content: string;
  toolTrace: ChatToolTrace[];
  safety?: { class_name: string; response: string } | null;
}

/** ChatTurnResponse plus the backend's `privacy_notice` (absent from lib types). */
export interface VoiceTurnResponse {
  session_id: string;
  role: string;
  content: string;
  tool_trace: ChatToolTrace[];
  history: Array<{ role: string; content: string }>;
  safety: { class_name: string; response: string } | null;
  model: string;
  privacy_notice?: string;
}

export function useChat() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<VoiceMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState<string>('');
  const [privacyNotice, setPrivacyNotice] = useState<string>('');
  const [inputValue, setInputValue] = useState('');

  // A monotonically-increasing ref so late-arriving responses can't overwrite
  // a newer turn (defends against out-of-order network completion).
  const turnSeq = useRef(0);

  const createSession = useCallback(async () => {
    try {
      const s = await api.chat.createSession();
      setSessionId(s.session_id);
      return true;
    } catch {
      setError(BACKEND_UNAVAILABLE);
      return false;
    }
  }, []);

  // Create the session once on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ok = await createSession();
      if (!ok && !cancelled) {
        setError(BACKEND_UNAVAILABLE);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [createSession]);

  /** Send one user turn.  Returns true if it reached the backend. */
  const send = useCallback(
    async (raw: string): Promise<boolean> => {
      const text = raw.trim();
      if (!text || !sessionId || sending) return false;

      const seq = ++turnSeq.current;
      setSending(true);
      setError(null);
      setInputValue('');
      // Optimistic user bubble; the server history is authoritative and will
      // replace the whole transcript on success.
      setMessages((prev) => [...prev, { role: 'user', content: text, toolTrace: [] }]);

      try {
        const res = (await api.chat.turn(sessionId, { message: text })) as VoiceTurnResponse;
        if (seq !== turnSeq.current) return true; // superseded by a newer turn
        setModel(res.model);
        setPrivacyNotice(res.privacy_notice ?? '');
        // Rebuild the transcript from the server so the client never holds a
        // divergent copy of the conversation.
        setMessages(
          res.history.map((m) => ({
            role: m.role === 'user' ? 'user' : 'assistant',
            content: m.content,
            toolTrace: m.role === 'assistant' ? res.tool_trace : [],
          })),
        );
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === 'assistant') {
            next[next.length - 1] = { ...last, toolTrace: res.tool_trace, safety: res.safety };
          }
          return next;
        });
        return true;
      } catch {
        if (seq === turnSeq.current) {
          setError(BACKEND_UNAVAILABLE);
          // Surface the failure inside the transcript so the user can retry.
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: `⚠️ ${BACKEND_UNAVAILABLE}`, toolTrace: [] },
          ]);
        }
        return false;
      } finally {
        if (seq === turnSeq.current) setSending(false);
      }
    },
    [sessionId, sending],
  );

  /** Clear the visible conversation (transcript + error).  Session is kept. */
  const clearConversation = useCallback(() => {
    setMessages([]);
    setError(null);
    setPrivacyNotice('');
    setInputValue('');
  }, []);

  /** End the session: DELETE on the backend, then start a fresh one. */
  const endSession = useCallback(async () => {
    const prevId = sessionId;
    if (prevId) {
      try {
        await api.chat.deleteSession(prevId);
      } catch {
        /* backend session already gone — best-effort */
      }
    }
    setMessages([]);
    setError(null);
    setPrivacyNotice('');
    setInputValue('');
    turnSeq.current += 1;
    await createSession();
  }, [sessionId, createSession]);

  return {
    sessionId,
    messages,
    sending,
    error,
    model,
    privacyNotice,
    inputValue,
    setInputValue,
    send,
    clearConversation,
    endSession,
  };
}
