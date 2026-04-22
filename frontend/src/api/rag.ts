import axios from 'axios';
import type {
  RAGSearchRequest,
  RAGSearchResponse,
  RAGAnswerRequest,
  SSEEvent,
} from '@/types';

// RAG service runs on port 8001
const ragApi = axios.create({
  baseURL: '/rag-api',
  timeout: 60000,
});

export async function ragSearch(body: RAGSearchRequest) {
  const res = await ragApi.post<RAGSearchResponse>('/rag/search', body);
  return res.data;
}

/**
 * Stream RAG answer via SSE. Returns an AbortController to cancel.
 *
 * @param body - Answer request payload
 * @param onEvent - Callback for each SSE event
 * @returns AbortController to cancel the stream
 */
export function ragAnswerStream(
  body: RAGAnswerRequest,
  onEvent: (event: SSEEvent) => void,
): AbortController {
  const controller = new AbortController();

  fetch('/rag-api/rag/answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok || !response.body) {
        onEvent({
          event: 'error',
          data: { message: `HTTP ${response.status}: ${response.statusText}` },
        });
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        let currentEvent = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ') && currentEvent) {
            try {
              const data = JSON.parse(line.slice(6));
              onEvent({ event: currentEvent as SSEEvent['event'], data });
            } catch {
              // skip malformed data
            }
            currentEvent = '';
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onEvent({ event: 'error', data: { message: String(err) } });
      }
    });

  return controller;
}
