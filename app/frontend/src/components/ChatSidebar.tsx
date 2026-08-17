/**
 * Conversation sidebar for the desktop consultant — a ChatGPT/Doubao-style
 * list of the browser's saved chats.  Renders only; the page owns the data
 * (which sessions exist, which is active) and the localStorage persistence.
 */

import { MessageSquarePlus, Trash2 } from 'lucide-react';
import type { ChatSession } from '../lib/types';
import { sortByNewest } from '../lib/chatSessions';

export interface ChatSidebarProps {
  sessions: ChatSession[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
}

/** "just now" / "5m ago" / "3h ago" / "4d ago" for the conversation list. */
export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const mins = Math.floor((Date.now() - then) / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function ChatSidebar({
  sessions,
  activeId,
  onSelect,
  onNewChat,
  onDelete,
}: ChatSidebarProps) {
  // Newest first, matching ChatGPT/Doubao ordering.
  const ordered = sortByNewest(sessions);

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-ink-200 bg-ink-100">
      <div className="p-3">
        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-600 px-3 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/60"
        >
          <MessageSquarePlus className="h-4 w-4" />
          New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2">
        <div className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-ink-500">
          Conversations
        </div>
        {ordered.length === 0 && (
          <div className="px-2 py-6 text-center text-xs text-ink-500">
            No conversations yet. Start a new chat.
          </div>
        )}
        <ul className="space-y-0.5">
          {ordered.map((s) => {
            const active = s.session_id === activeId;
            return (
              <li key={s.session_id}>
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(s.session_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelect(s.session_id);
                    }
                  }}
                  aria-current={active ? 'true' : undefined}
                  className={`group flex w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-left transition-colors ${
                    active
                      ? 'bg-ink-200 text-ink-900'
                      : 'text-ink-400 hover:bg-ink-200/50 hover:text-ink-900'
                  }`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{s.title}</span>
                    <span className="block text-[11px] text-ink-500">
                      {relativeTime(s.updated_at)}
                    </span>
                  </span>
                  <button
                    type="button"
                    aria-label={`Delete conversation ${s.title}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(s.session_id);
                    }}
                    className="shrink-0 rounded-md p-1 text-ink-500 opacity-0 transition-opacity hover:bg-risk-high/10 hover:text-risk-high focus:opacity-100 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="border-t border-ink-200 p-3">
        <div className="flex items-center gap-2 text-[11px] text-ink-500">
          <span className="h-1.5 w-1.5 rounded-full bg-risk-low" />
          Saved on this device
        </div>
      </div>
    </aside>
  );
}
