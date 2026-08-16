/**
 * Shared chat transcript for the consultant and the voice client.
 *
 * Renders the user/assistant bubbles, tool-result charts and the typing
 * indicator.  The empty state, error banners and the input box stay with
 * each page — only the message list is shared here so both surfaces render
 * identically.
 */

import { memo } from 'react';
import { Bot } from 'lucide-react';
import type { TranscriptMessage } from '../lib/types';
import { ChatMarkdown } from './ChatMarkdown';
import { ChatToolCharts, ToolTraceFooter } from './ChatToolCharts';

interface ChatTranscriptProps {
  messages: TranscriptMessage[];
  sending?: boolean;
  /** Max width of the message bubbles (the mobile voice client is narrower). */
  bubbleWidth?: string;
  /** Entrance animation on each row (desktop consultant only). */
  animateRows?: boolean;
  /** Label shown beside the typing dots while the model is thinking. */
  typingLabel?: string;
}

/** Three-dot typing indicator; the label is optional (voice client omits it). */
function TypingDots({ label }: { label?: string }) {
  const dots = (
    <span className="flex gap-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-500 [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-500 [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-500 [animation-delay:300ms]" />
    </span>
  );
  if (!label) return dots;
  return (
    <div className="flex items-center gap-3">
      {dots}
      <span className="text-xs font-medium text-ink-500">{label}</span>
    </div>
  );
}

/** The consultant avatar shown beside every assistant bubble. */
function BotAvatar() {
  return (
    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink-950 text-brand-400">
      <Bot className="h-4.5 w-4.5" />
    </div>
  );
}

export const ChatTranscript = memo(function ChatTranscript({
  messages,
  sending = false,
  bubbleWidth = 'max-w-[82%]',
  animateRows = false,
  typingLabel,
}: ChatTranscriptProps) {
  const rowClass = animateRows ? 'panel-in flex gap-3' : 'flex gap-3';

  return (
    <>
      {messages.map((m, i) => (
        <div key={i} className={`${rowClass} ${m.role === 'user' ? 'justify-end' : ''}`}>
          {m.role === 'assistant' && <BotAvatar />}
          <div className={`${bubbleWidth} ${m.role === 'user' ? 'order-first' : ''}`}>
            {m.role === 'user' ? (
              <div className="rounded-2xl rounded-tr-sm bg-ink-900 px-4 py-2.5 text-sm text-ink-50">
                {m.content}
              </div>
            ) : (
              <div className="rounded-2xl rounded-tl-sm border border-ink-200 bg-ink-100 px-4 py-3 shadow-sm">
                <ChatMarkdown content={m.content} />
                {m.toolTrace && m.toolTrace.length > 0 && (
                  <>
                    <div className="mt-3">
                      <ChatToolCharts trace={m.toolTrace} />
                    </div>
                    <ToolTraceFooter trace={m.toolTrace} />
                  </>
                )}
                {m.safety && (
                  <div className="mt-3 rounded-lg border border-risk-med/30 bg-risk-med/10 px-3 py-2 text-xs text-risk-med">
                    {m.safety.response}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      ))}

      {sending && (
        <div className="flex gap-3">
          <BotAvatar />
          <div className="rounded-2xl rounded-tl-sm border border-ink-200 bg-ink-100 px-4 py-3 shadow-sm">
            <TypingDots label={typingLabel} />
          </div>
        </div>
      )}
    </>
  );
});
