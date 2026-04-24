import React, { useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Spin, Typography, Empty } from 'antd';
import { RobotOutlined, UserOutlined } from '@ant-design/icons';
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
        padding: '24px 32px',
      }}
    >
      {messages.length === 0 && (
        <div style={{ textAlign: 'center', marginTop: 120 }}>
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: 20,
              background: 'linear-gradient(135deg, #36cfc9, #13c2c2)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 20,
              boxShadow: '0 8px 24px rgba(54, 207, 201, 0.25)',
            }}
          >
            <RobotOutlined style={{ fontSize: 36, color: '#fff' }} />
          </div>
          <div style={{ fontSize: 20, fontWeight: 600, color: '#08979c', marginBottom: 8 }}>
            储能智能助手
          </div>
          <div style={{ color: '#8c8c8c', fontSize: 14, maxWidth: 400, margin: '0 auto' }}>
            支持知识问答、数据查询与分析、图表生成，输入问题开始对话
          </div>
        </div>
      )}

      {messages.map((msg, idx) => (
        <div
          key={idx}
          style={{
            display: 'flex',
            gap: 12,
            marginBottom: 20,
            flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
            alignItems: 'flex-start',
          }}
        >
          {/* Avatar */}
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background:
                msg.role === 'user'
                  ? 'linear-gradient(135deg, #36cfc9, #13c2c2)'
                  : 'rgba(54, 207, 201, 0.1)',
              color: msg.role === 'user' ? '#fff' : '#08979c',
              fontSize: 16,
            }}
          >
            {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
          </div>

          {/* Bubble */}
          <div
            style={{
              maxWidth: '75%',
              padding: '12px 16px',
              borderRadius: msg.role === 'user' ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
              background:
                msg.role === 'user'
                  ? 'linear-gradient(135deg, #36cfc9, #13c2c2)'
                  : 'rgba(255, 255, 255, 0.85)',
              color: msg.role === 'user' ? '#fff' : '#262626',
              backdropFilter: msg.role === 'assistant' ? 'blur(8px)' : undefined,
              boxShadow:
                msg.role === 'user'
                  ? '0 2px 12px rgba(54, 207, 201, 0.25)'
                  : '0 2px 12px rgba(0, 0, 0, 0.04)',
              border: msg.role === 'assistant' ? '1px solid rgba(54, 207, 201, 0.1)' : 'none',
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
              <div className="agent-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content
                    .replace(/<think>[\s\S]*?<\/think>/g, '')
                    .replace(/<think>[\s\S]*/g, '')
                    .trim()}
                </ReactMarkdown>
              </div>
            ) : (
              <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
                {msg.content}
              </div>
            )}

            {/* Error */}
            {msg.error && (
              <Text type="danger" style={{ fontSize: 12 }}>
                {msg.error}
              </Text>
            )}
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
};

export default MessageList;
