import React, { useEffect, useState, useCallback } from 'react';
import { Button, List, Typography, Popconfirm, Empty, Spin } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { listSessions, deleteSession, getSession } from '@/api/agent';
import type { SessionItem, AgentMessage } from '@/types/agent';

const { Text } = Typography;

interface Props {
  currentSessionId?: string;
  onNewSession: () => void;
  onSelectSession: (sessionId: string, messages: AgentMessage[]) => void;
}

const SessionSidebar: React.FC<Props> = ({
  currentSessionId,
  onNewSession,
  onSelectSession,
}) => {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listSessions(0, 50);
      setSessions(res.items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions, currentSessionId]);

  const handleSelect = async (sid: string) => {
    try {
      const detail = await getSession(sid);
      const msgs: AgentMessage[] = detail.messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          toolCalls: [],
          citations: [],
          dataTables: [],
          charts: [],
        }));
      onSelectSession(sid, msgs);
    } catch {
      // ignore
    }
  };

  const handleDelete = async (sid: string) => {
    try {
      await deleteSession(sid);
      loadSessions();
      if (sid === currentSessionId) onNewSession();
    } catch {
      // ignore
    }
  };

  return (
    <div
      style={{
        width: 260,
        background: 'rgba(255, 255, 255, 0.65)',
        backdropFilter: 'blur(10px)',
        borderRight: '1px solid rgba(54, 207, 201, 0.12)',
        display: 'flex',
        flexDirection: 'column',
        borderRadius: '16px 0 0 16px',
      }}
    >
      <div style={{ padding: '16px 16px 12px' }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          block
          size="large"
          style={{
            borderRadius: 10,
            height: 42,
            fontWeight: 500,
          }}
          onClick={onNewSession}
        >
          新对话
        </Button>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '0 8px 8px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin size="small" />
          </div>
        ) : sessions.length === 0 ? (
          <Empty
            description="暂无会话"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            style={{ marginTop: 40 }}
          />
        ) : (
          <List
            size="small"
            dataSource={sessions}
            renderItem={(item) => (
              <div
                style={{
                  padding: '10px 12px',
                  marginBottom: 4,
                  cursor: 'pointer',
                  borderRadius: 10,
                  background:
                    item.id === currentSessionId
                      ? 'rgba(54, 207, 201, 0.12)'
                      : 'transparent',
                  transition: 'background 0.2s',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
                onClick={() => handleSelect(item.id)}
                onMouseEnter={(e) => {
                  if (item.id !== currentSessionId) {
                    e.currentTarget.style.background = 'rgba(54, 207, 201, 0.06)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (item.id !== currentSessionId) {
                    e.currentTarget.style.background = 'transparent';
                  }
                }}
              >
                <Text
                  ellipsis
                  style={{
                    fontSize: 13,
                    maxWidth: 180,
                    color: item.id === currentSessionId ? '#08979c' : '#595959',
                  }}
                  title={item.title}
                >
                  {item.title}
                </Text>
                <Popconfirm
                  title="删除此会话？"
                  onConfirm={(e) => {
                    e?.stopPropagation();
                    handleDelete(item.id);
                  }}
                  onCancel={(e) => e?.stopPropagation()}
                >
                  <DeleteOutlined
                    onClick={(e) => e.stopPropagation()}
                    style={{ color: '#bfbfbf', fontSize: 12 }}
                  />
                </Popconfirm>
              </div>
            )}
          />
        )}
      </div>
    </div>
  );
};

export default SessionSidebar;
