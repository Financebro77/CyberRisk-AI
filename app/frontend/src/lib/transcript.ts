/**
 * Rebuild a chat transcript from the server's authoritative history.
 *
 * Both the consultant page and the voice client hold NO divergent copy of the
 * conversation -- they rebuild it from `ChatTurnResponse.history` after every
 * turn.  Only the final assistant message carries that turn's tool trace /
 * safety banner.
 */

import type { ChatToolTrace, TranscriptMessage } from './types';

export function transcriptFromTurn(
  history: Array<{ role: string; content: string }>,
  toolTrace: ChatToolTrace[],
  safety: TranscriptMessage['safety'],
): TranscriptMessage[] {
  const lastIndex = history.length - 1;
  return history.map((m, i) => {
    const isFinalAssistant = i === lastIndex && m.role === 'assistant';
    return {
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.content,
      toolTrace: isFinalAssistant ? toolTrace : [],
      safety: isFinalAssistant ? safety : null,
    };
  });
}
