import React, { useState } from 'react';
import { Input, Button, Select, Space } from 'antd';
import { SendOutlined, StopOutlined } from '@ant-design/icons';
import type { KBResponse } from '@/types';

const { TextArea } = Input;

interface Props {
  kbs: KBResponse[];
  selectedKBs: string[];
  onKBChange: (ids: string[]) => void;
  onSend: (query: string) => void;
  onStop: () => void;
  streaming: boolean;
}

const ChatInput: React.FC<Props> = ({
  kbs,
  selectedKBs,
  onKBChange,
  onSend,
  onStop,
  streaming,
}) => {
  const [query, setQuery] = useState('');

  const handleSend = () => {
    if (!query.trim()) return;
    onSend(query);
    setQuery('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      style={{
        padding: '12px 16px',
        borderTop: '1px solid #f0f0f0',
        background: '#fff',
      }}
    >
      <div style={{ marginBottom: 8 }}>
        <Select
          mode="multiple"
          placeholder="选择知识库（可选，用于知识问答）"
          value={selectedKBs}
          onChange={onKBChange}
          style={{ width: '100%' }}
          size="small"
          options={kbs.map((kb) => ({ label: kb.name, value: kb.id }))}
          allowClear
        />
      </div>
      <Space.Compact style={{ width: '100%' }}>
        <TextArea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入问题，按 Enter 发送（支持知识问答和数据分析）"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={streaming}
          style={{ flex: 1 }}
        />
        {streaming ? (
          <Button icon={<StopOutlined />} onClick={onStop} danger>
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
      </Space.Compact>
    </div>
  );
};

export default ChatInput;
