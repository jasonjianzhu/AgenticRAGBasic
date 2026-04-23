import React, { useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card, Spin, Typography, Empty } from 'antd';
import type { AgentMessage } from '@/types/agent';
import ToolCallDisplay from './ToolCallDisplay';
import ChartRenderer from './ChartRenderer';

const { Paragraph, Text } = Typography;

interface Props {
  messages: AgentMessage[];
}

const MessageList: React.FC<Props> = ({ messages }) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div
      style={{
        flex: 1,
        overflow: 'auto',
        padding: '16px',
      }}
    >
      {messages.length === 0 && (
        <Empty
          description="输入问题开始对话（支持知识问答和数据分析）"
          style={{ marginTop: 80 }}
        />
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
              maxWidth: msg.role === 'user' ? '70%' : '85%',
              background: msg.role === 'user' ? '#e6f4ff' : '#fff',
              borderColor: msg.role === 'user' ? '#91caff' : '#f0f0f0',
            }}
          >
            {/* Tool calls */}
            {msg.toolCalls && msg.toolCalls.length > 0 && (
              <ToolCallDisplay toolCalls={msg.toolCalls} />
            )}

            {/* Charts */}
            {msg.charts?.map((chart, i) => (
              <ChartRenderer key={`chart-${i}`} option={chart} />
            ))}

            {/* Content */}
            {msg.loading && !msg.content ? (
              <Spin size="small" />
            ) : msg.role === 'assistant' ? (
              <div>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content
                    .replace(/<think>[\s\S]*?<\/think>/g, '')
                    .replace(/<think>[\s\S]*/g, '')
                    .trim()}
                </ReactMarkdown>
              </div>
            ) : (
              <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                {msg.content}
              </Paragraph>
            )}

            {/* Error */}
            {msg.error && (
              <Text type="danger" style={{ fontSize: 12 }}>
                {msg.error}
              </Text>
            )}
          </Card>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
};

export default MessageList;
