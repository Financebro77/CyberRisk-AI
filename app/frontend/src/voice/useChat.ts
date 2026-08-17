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
import { transcriptFromTurn } from '../lib/transcript';
import type { ChatToolTrace, TranscriptMessage } from '../lib/types';

/** Exact user-facing error strings — exported so UI and tests share them. */
export const BACKEND_UNAVAILABLE =
  'The Armageddon service is currently unavailable. Please try again.';
export const RECOGNITION_FAILURE = "I couldn't hear that clearly. Please try again.";
export const INSUFFICIENT_MODEL_INFO =
  'I need a little more information before I can calculate the risk.';

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
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
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

  // Create the session once on mount.  createSession sets the error itself on
  // failure, so no duplicate error here.
  useEffect(() => {
    void createSession();
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
        setMessages(transcriptFromTurn(res.history, res.tool_trace, res.safety));
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

  /** End the session: reset the UI now, discard the backend session in the
   *  background, then start a fresh one.  The DELETE is fire-and-forget so a
   *  slow backend cannot block the reset or the new session. */
  const endSession = useCallback(async () => {
    const prevId = sessionId;
    if (prevId) {
      // Fire-and-forget; Promise.resolve() tolerates a non-Promise return.
      Promise.resolve(api.chat.deleteSession(prevId)).catch(() => {
        /* backend session already gone — best-effort */
      });
    }
    setMessages([]);
    setError(null);
    setPrivacyNotice('');
    setInputValue('');
    // Invalidate any in-flight turn (its finally will skip setSending(false)
    // because the seq no longer matches), so clear `sending` here or the
    // voice client wedges on "thinking" forever.
    turnSeq.current += 1;
    setSending(false);
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
