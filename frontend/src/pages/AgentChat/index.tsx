import React, { useState, useRef, useEffect, useCallback } from 'react';
import { message } from 'antd';
import { listKBs } from '@/api/client';
import { agentChatStream, getSession } from '@/api/agent';
import { stripThinkTags } from '@/utils/content';
import type { KBResponse } from '@/types';
import type {
  AgentMessage,
  AgentSSEEvent,
  AgentCitation,
  DataTableEvent,
  ChartEvent,
  ToolCallInfo,
  ToolStartEvent,
  ToolResultEvent,
} from '@/types/agent';
import SessionSidebar from './SessionSidebar';
import ChatInput from './ChatInput';
import MessageList from './MessageList';

const STORAGE_KEY = 'agent_current_session';

const AgentChatPage: React.FC = () => {
  const [kbs, setKBs] = useState<KBResponse[]>([]);
  const [selectedKBs, setSelectedKBs] = useState<string[]>([]);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const abortRef = useRef<AbortController | null>(null);
  const blockRestoreRef = useRef(false);

  // Load KBs
  useEffect(() => {
    listKBs().then((res) => {
      setKBs(res.items);
      if (res.items.length > 0) setSelectedKBs([res.items[0].id]);
    }).catch(() => {});
  }, []);

  // Restore last session on mount
  useEffect(() => {
    const savedId = localStorage.getItem(STORAGE_KEY);
    if (!savedId) return;
    let cancelled = false;

    const loadSession = (id: string) => {
      getSession(id)
        .then((detail) => {
          if (cancelled || blockRestoreRef.current) return;
          console.log('[AgentChat] loadSession', id, 'messages:', detail.messages.length);
          const msgs: AgentMessage[] = detail.messages
            .filter((m: { role: string }) => m.role === 'user' || m.role === 'assistant')
            .map((m: { role: string; content: string; metadata: Record<string, unknown> }) => ({
              role: m.role as 'user' | 'assistant',
              content: m.content,
              toolCalls: [],
              citations: [],
              dataTables: [],
              charts: (m.metadata?.charts as ChartEvent[] | undefined) ?? [],
            }));
          console.log('[AgentChat] restored msgs:', msgs.length);
          setSessionId(id);
          setMessages(msgs);

          // If last message is from user (assistant still generating), retry after delay
          const lastMsg = detail.messages[detail.messages.length - 1];
          if (lastMsg && lastMsg.role === 'user' && !cancelled && !blockRestoreRef.current) {
            setTimeout(() => loadSession(id), 3000);
          }
        })
        .catch((err) => {
          if (cancelled || blockRestoreRef.current) return;
          console.error('[AgentChat] loadSession failed', err);
          localStorage.removeItem(STORAGE_KEY);
        });
    };

    loadSession(savedId);

    return () => {
      cancelled = true;
    };
  }, []);

  // Persist sessionId to localStorage
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem(STORAGE_KEY, sessionId);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [sessionId]);

  const handleNewSession = useCallback(() => {
    blockRestoreRef.current = true;
    setSessionId(undefined);
    setMessages([]);
  }, []);

  const handleSelectSession = useCallback((sid: string, msgs: AgentMessage[]) => {
    blockRestoreRef.current = true;
    setSessionId(sid);
    setMessages(msgs);
  }, []);

  const handleSend = useCallback(
    (query: string) => {
      if (!query.trim() || streaming) return;
      blockRestoreRef.current = true;

      const userMsg: AgentMessage = { role: 'user', content: query.trim() };
      const assistantMsg: AgentMessage = {
        role: 'assistant',
        content: '',
        loading: true,
        toolCalls: [],
        citations: [],
        dataTables: [],
        charts: [],
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStreaming(true);

      const controller = agentChatStream(
        {
          session_id: sessionId,
          message: query.trim(),
          kb_ids: selectedKBs,
        },
        (event: AgentSSEEvent) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = { ...updated[updated.length - 1] };

            switch (event.event) {
              case 'tool_start': {
                const ts = event.data as unknown as ToolStartEvent;
                last.toolCalls = [
                  ...(last.toolCalls ?? []),
                  { tool: ts.tool, argsSummary: ts.args_summary, status: 'running' },
                ];
                break;
              }
              case 'tool_result': {
                const tr = event.data as unknown as ToolResultEvent;
                const calls = [...(last.toolCalls ?? [])];
                let idx = -1;
                for (let i = calls.length - 1; i >= 0; i--) {
                  if (calls[i].tool === tr.tool && calls[i].status === 'running') {
                    idx = i;
                    break;
                  }
                }
                if (idx >= 0) {
                  calls[idx] = { ...calls[idx], result: tr.summary, status: 'done' };
                }
                last.toolCalls = calls;
                break;
              }
              case 'citation': {
                const cit = event.data as unknown as AgentCitation;
                last.citations = [...(last.citations ?? []), cit];
                break;
              }
              case 'data_table': {
                const dt = event.data as unknown as DataTableEvent;
                last.dataTables = [...(last.dataTables ?? []), dt];
                break;
              }
              case 'chart': {
                const chart = event.data as unknown as ChartEvent;
                last.charts = [...(last.charts ?? []), chart];
                break;
              }
              case 'token': {
                const token = (event.data as { content: string }).content;
                last.content = (last.content || '') + token;
                break;
              }
              case 'thinking': {
                const thinkToken = (event.data as { content: string }).content;
                last.thinking = (last.thinking || '') + thinkToken;
                break;
              }
              case 'done': {
                last.loading = false;
                last.content = stripThinkTags(last.content);
                // Clear thinking on done
                last.thinking = undefined;
                const sid = (event.data as { session_id?: string }).session_id;
                if (sid) setSessionId(sid);
                break;
              }
              case 'error': {
                last.loading = false;
                last.error = (event.data as { message: string }).message;
                break;
              }
            }

            updated[updated.length - 1] = last;
            return updated;
          });

          if (event.event === 'done' || event.event === 'error') {
            setStreaming(false);
          }
        },
      );

      abortRef.current = controller;
    },
    [streaming, sessionId, selectedKBs],
  );

  const handleStop = () => {
    abortRef.current?.abort();
    setStreaming(false);
    setMessages((prev) => {
      const updated = [...prev];
      if (updated.length > 0) {
        const last = { ...updated[updated.length - 1] };
        last.loading = false;
        updated[updated.length - 1] = last;
      }
      return updated;
    });
  };

  return (
    <div style={{ display: 'flex', flex: 1, padding: 16, gap: 12 }}>
      <SessionSidebar
        currentSessionId={sessionId}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
      />
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
          background: 'rgba(255, 255, 255, 0.45)',
          backdropFilter: 'blur(10px)',
          borderRadius: 16,
          border: '1px solid rgba(0,166,81,0.08)',
          overflow: 'hidden',
        }}
      >
        {messages.length === 0 && !streaming ? (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
            paddingTop: 'calc(33vh - 130px)', position: 'relative', zIndex: 1,
          }}>
            <div style={{ marginBottom: 20 }}>
              <img
                src="/assets/jinko-logo-en.svg"
                alt="Jinko ESS"
                style={{ height: 60, objectFit: 'contain' }}
              />
            </div>
            <div style={{ textAlign: 'center', marginBottom: 18 }}>
              <span style={{ fontSize: 30, fontWeight: 600, color: '#555', letterSpacing: 0.5 }}>
                想了解什么吗
              </span>
            </div>
            <div style={{ width: '66%', minWidth: 600, maxWidth: 900, marginBottom: 20 }}>
              <ChatInput
                kbs={kbs}
                selectedKBs={selectedKBs}
                onKBChange={setSelectedKBs}
                onSend={handleSend}
                onStop={handleStop}
                streaming={streaming}
              />
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              {['💬 知识问答', '📊 数据分析', '📈 图表生成'].map((label) => (
                <div
                  key={label}
                  onClick={() => handleSend(label.replace(/^.\s/, ''))}
                  style={{
                    padding: '10px 20px', borderRadius: 12, cursor: 'pointer', fontSize: 13,
                    fontWeight: 500, color: '#555', transition: 'all 0.2s',
                    background: 'rgba(255,255,255,0.7)', border: '1px solid rgba(0,166,81,0.12)',
                    boxShadow: '0 1px 6px rgba(0,0,0,0.03)',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#00A651';
                    e.currentTarget.style.background = 'rgba(0,166,81,0.04)';
                    e.currentTarget.style.boxShadow = '0 2px 12px rgba(0,166,81,0.08)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'rgba(0,166,81,0.12)';
                    e.currentTarget.style.background = 'rgba(255,255,255,0.7)';
                    e.currentTarget.style.boxShadow = '0 1px 6px rgba(0,0,0,0.03)';
                  }}
                >
                  {label}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <>
            <MessageList messages={messages} />
            <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0' }}>
              <img
                src="/assets/jinko-logo-en.svg"
                alt="Jinko ESS"
                style={{ height: 40, objectFit: 'contain' }}
              />
            </div>
            <ChatInput
              kbs={kbs}
              selectedKBs={selectedKBs}
              onKBChange={setSelectedKBs}
              onSend={handleSend}
              onStop={handleStop}
              streaming={streaming}
            />
          </>
        )}
      </div>
    </div>
  );
};

export default AgentChatPage;
