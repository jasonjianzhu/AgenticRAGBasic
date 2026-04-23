import React, { useEffect, useState, useCallback } from 'react';
import { Layout, Button, List, Typography, Popconfirm, Empty, Spin } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import { listSessions, deleteSession, getSession } from '@/api/agent';
import type { SessionItem, AgentMessage } from '@/types/agent';

const { Sider } = Layout;
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
    <Sider
      width={240}
      style={{
        background: '#fafafa',
        borderRight: '1px solid #f0f0f0',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #f0f0f0' }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          block
          onClick={onNewSession}
        >
          新对话
        </Button>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin size="small" />
          </div>
        ) : sessions.length === 0 ? (
          <Empty description="暂无会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <List
            size="small"
            dataSource={sessions}
            renderItem={(item) => (
              <List.Item
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  background:
                    item.id === currentSessionId ? '#e6f4ff' : 'transparent',
                }}
                onClick={() => handleSelect(item.id)}
                actions={[
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
                      style={{ color: '#999', fontSize: 12 }}
                    />
                  </Popconfirm>,
                ]}
              >
                <Text
                  ellipsis
                  style={{ fontSize: 13, maxWidth: 160 }}
                  title={item.title}
                >
                  {item.title}
                </Text>
              </List.Item>
            )}
          />
        )}
      </div>
    </Sider>
  );
};

export default SessionSidebar;
