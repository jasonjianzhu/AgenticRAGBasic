import axios from 'axios';
import type {
  AgentChatRequest,
  AgentSSEEvent,
  SessionListResponse,
  SessionDetailResponse,
} from '@/types/agent';

const agentApi = axios.create({
  baseURL: '/agent-api',
  timeout: 60000,
});

// ─── Sessions ───

export async function listSessions(skip = 0, limit = 20) {
  const res = await agentApi.get<SessionListResponse>('/agent/sessions', {
    params: { skip, limit },
  });
  return res.data;
}

export async function getSession(sessionId: string) {
  const res = await agentApi.get<SessionDetailResponse>(
    `/agent/sessions/${sessionId}`,
  );
  return res.data;
}

export async function deleteSession(sessionId: string) {
  await agentApi.delete(`/agent/sessions/${sessionId}`);
}

// ─── Chat (SSE) ───

export function agentChatStream(
  body: AgentChatRequest,
  onEvent: (event: AgentSSEEvent) => void,
): AbortController {
  const controller = new AbortController();

  fetch('/agent-api/agent/chat', {
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
      let currentEvent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ') && currentEvent) {
            try {
              const data = JSON.parse(line.slice(6));
              onEvent({ event: currentEvent as AgentSSEEvent['event'], data });
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

// ─── DB Admin ───

export async function getDbSchema() {
  const res = await agentApi.get('/agent/db/schema');
  return res.data;
}

export async function testDbConnection() {
  const res = await agentApi.post('/agent/db/test');
  return res.data;
}
