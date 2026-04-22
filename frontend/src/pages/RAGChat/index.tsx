import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Input,
  Button,
  Select,
  Card,
  Tag,
  Collapse,
  Typography,
  Space,
  Spin,
  Empty,
  message,
} from 'antd';
import {
  SendOutlined,
  StopOutlined,
  FileTextOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { listKBs } from '@/api/client';
import { ragAnswerStream } from '@/api/rag';
import type {
  KBResponse,
  Citation,
  SSEEvent,
  RAGSearchTrace,
} from '@/types';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  trace?: RAGSearchTrace;
  loading?: boolean;
  error?: string;
}

const RAGChatPage: React.FC = () => {
  const [kbs, setKBs] = useState<KBResponse[]>([]);
  const [selectedKBs, setSelectedKBs] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load knowledge bases
  useEffect(() => {
    listKBs().then((res) => {
      setKBs(res.items);
      if (res.items.length > 0 && selectedKBs.length === 0) {
        setSelectedKBs([res.items[0].id]);
      }
    });
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback(() => {
    if (!query.trim() || streaming) return;
    if (selectedKBs.length === 0) {
      message.warning('请先选择知识库');
      return;
    }

    const userMsg: ChatMessage = { role: 'user', content: query.trim() };
    const assistantMsg: ChatMessage = {
      role: 'assistant',
      content: '',
      citations: [],
      loading: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setQuery('');
    setStreaming(true);

    const controller = ragAnswerStream(
      {
        query: query.trim(),
        kb_ids: selectedKBs,
        top_k: 5,
        enable_rewrite: false,
      },
      (event: SSEEvent) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = { ...updated[updated.length - 1] };

          switch (event.event) {
            case 'trace':
              last.trace = event.data as unknown as RAGSearchTrace;
              break;
            case 'citation':
              last.citations = [
                ...(last.citations ?? []),
                event.data as unknown as Citation,
              ];
              break;
            case 'token': {
              const token = (event.data as { content: string }).content;
              // Track think tag state in content using markers
              const currentContent = last.content;
              const newContent = currentContent + token;
              last.content = newContent;
              break;
            }
            case 'done': {
              last.loading = false;
              // Strip <think>...</think> blocks from final content
              let cleaned = last.content.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
              // Also handle unclosed think tag (streaming may split it)
              if (cleaned.includes('<think>')) {
                cleaned = cleaned.replace(/<think>[\s\S]*/g, '').trim();
              }
              last.content = cleaned;
              // Filter citations: only keep those referenced in the answer [1] [2] etc.
              if (last.citations && last.citations.length > 0) {
                const referencedIndices = new Set<number>();
                const refPattern = /\[(\d+)\]/g;
                let match;
                while ((match = refPattern.exec(cleaned)) !== null) {
                  referencedIndices.add(parseInt(match[1], 10));
                }
                if (referencedIndices.size > 0) {
                  last.citations = last.citations.filter((c) => referencedIndices.has(c.index));
                }
                // If no references found in text, keep top 3 citations as context
                if (referencedIndices.size === 0) {
                  last.citations = last.citations.slice(0, 3);
                }
              }
              break;
            }
            case 'error':
              last.loading = false;
              last.error = (event.data as { message: string }).message;
              break;
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
  }, [query, streaming, selectedKBs]);

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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* KB selector */}
      <div style={{ marginBottom: 12 }}>
        <Select
          mode="multiple"
          placeholder="选择知识库"
          value={selectedKBs}
          onChange={setSelectedKBs}
          style={{ width: '100%' }}
          options={kbs.map((kb) => ({ label: kb.name, value: kb.id }))}
        />
      </div>

      {/* Messages area */}
      <div
        style={{
          flex: 1,
          overflow: 'auto',
          marginBottom: 12,
          padding: '8px 0',
        }}
      >
        {messages.length === 0 && (
          <Empty description="输入问题开始问答" style={{ marginTop: 80 }} />
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: 16,
            }}
          >
            <Card
              size="small"
              style={{
                maxWidth: '80%',
                background: msg.role === 'user' ? '#e6f4ff' : '#fff',
                borderColor: msg.role === 'user' ? '#91caff' : '#f0f0f0',
              }}
            >
              {/* Content */}
              {msg.loading && !msg.content ? (
                <Spin size="small" />
              ) : (
                <Paragraph
                  style={{ marginBottom: msg.citations?.length ? 8 : 0, whiteSpace: 'pre-wrap' }}
                >
                  {msg.role === 'assistant'
                    ? msg.content
                        .replace(/<think>[\s\S]*?<\/think>/g, '')
                        .replace(/<think>[\s\S]*/g, '')
                        .trim() || (msg.loading ? '' : msg.content)
                    : msg.content}
                </Paragraph>
              )}

              {/* Error */}
              {msg.error && (
                <Text type="danger" style={{ fontSize: 12 }}>
                  {msg.error}
                </Text>
              )}

              {/* Citations */}
              {msg.citations && msg.citations.length > 0 && (
                <Collapse
                  size="small"
                  ghost
                  items={[
                    {
                      key: 'citations',
                      label: (
                        <Space size={4}>
                          <FileTextOutlined />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            引用来源 ({msg.citations.length})
                          </Text>
                        </Space>
                      ),
                      children: (
                        <div>
                          {msg.citations.map((cit) => (
                            <div
                              key={cit.index}
                              style={{
                                padding: '4px 0',
                                borderBottom: '1px solid #f5f5f5',
                                fontSize: 12,
                              }}
                            >
                              <Tag color="blue" style={{ fontSize: 11 }}>
                                [{cit.index}]
                              </Tag>
                              <Text strong style={{ fontSize: 12 }}>
                                {cit.document_title}
                              </Text>
                              {cit.page && (
                                <Text type="secondary" style={{ fontSize: 11 }}>
                                  {' '}
                                  p.{cit.page}
                                </Text>
                              )}
                              <Paragraph
                                type="secondary"
                                style={{ fontSize: 11, margin: '2px 0 0 0' }}
                                ellipsis={{ rows: 2 }}
                              >
                                {cit.snippet}
                              </Paragraph>
                            </div>
                          ))}
                        </div>
                      ),
                    },
                  ]}
                />
              )}

              {/* Trace */}
              {msg.trace && (
                <Collapse
                  size="small"
                  ghost
                  items={[
                    {
                      key: 'trace',
                      label: (
                        <Space size={4}>
                          <SearchOutlined />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            检索详情
                          </Text>
                        </Space>
                      ),
                      children: (
                        <div style={{ fontSize: 12 }}>
                          {msg.trace.query_rewritten && (
                            <div>
                              <Text type="secondary">改写: </Text>
                              <Text>{msg.trace.query_rewritten}</Text>
                            </div>
                          )}
                          <div>
                            <Text type="secondary">命中: </Text>
                            dense {msg.trace.dense_hits} / sparse{' '}
                            {msg.trace.sparse_hits} / 融合 {msg.trace.fused_total}{' '}
                            / 返回 {msg.trace.returned}
                          </div>
                          {msg.trace.latency_ms?.total && (
                            <div>
                              <Text type="secondary">耗时: </Text>
                              {msg.trace.latency_ms.total}ms
                            </div>
                          )}
                        </div>
                      ),
                    },
                  ]}
                />
              )}
            </Card>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div style={{ display: 'flex', gap: 8 }}>
        <TextArea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入问题，按 Enter 发送"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={streaming}
          style={{ flex: 1 }}
        />
        {streaming ? (
          <Button icon={<StopOutlined />} onClick={handleStop} danger>
            停止
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!query.trim()}
          >
            发送
          </Button>
        )}
      </div>
    </div>
  );
};

export default RAGChatPage;
