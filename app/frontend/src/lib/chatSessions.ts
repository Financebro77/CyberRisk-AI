/**
 * Browser-side ownership of the user's chat conversations.
 *
 * The server persists every conversation; the browser just owns the LIST of
 * session ids it can see (per-browser, no login) plus which one is active, so
 * a reload returns to the same conversation.  The desktop consultant page is
 * the only writer; the voice PWA deliberately keeps no storage.
 */

import type { ChatSession } from './types';

const CONVERSATIONS_KEY = 'cyberrisk-conversations';
const ACTIVE_KEY = 'cyberrisk-active-conversation';

/** The owned session ids, oldest first (new ones append). */
export function loadConversationIds(): string[] {
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

export function saveConversationIds(ids: string[]): void {
  localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(ids));
}

export function addConversationId(id: string): void {
  const next = [...loadConversationIds(), id];
  saveConversationIds(next);
}

export function removeConversationId(id: string): void {
  const next = loadConversationIds().filter((x) => x !== id);
  saveConversationIds(next);
}

/** The session to reopen on the next load (null = none remembered). */
export function loadActiveConversation(): string | null {
  try {
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

export function saveActiveConversation(id: string | null): void {
  if (id === null) {
    localStorage.removeItem(ACTIVE_KEY);
  } else {
    localStorage.setItem(ACTIVE_KEY, id);
  }
}

/** Newest-first copy of the session list (ChatGPT/Doubao-style ordering). */
export function sortByNewest(sessions: ChatSession[]): ChatSession[] {
  return [...sessions].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}
