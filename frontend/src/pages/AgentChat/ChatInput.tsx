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
        padding: '16px 32px 20px',
        background: 'rgba(255, 255, 255, 0.6)',
        backdropFilter: 'blur(12px)',
        borderTop: '1px solid rgba(54, 207, 201, 0.1)',
      }}
    >
      {kbs.length > 0 && (
        <div style={{ marginBottom: 10 }}>
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
      )}
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
        <TextArea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入问题，按 Enter 发送..."
          autoSize={{ minRows: 1, maxRows: 5 }}
          disabled={streaming}
          style={{
            flex: 1,
            borderRadius: 12,
            padding: '10px 14px',
            fontSize: 14,
            background: 'rgba(255, 255, 255, 0.9)',
            border: '1px solid rgba(54, 207, 201, 0.2)',
          }}
        />
        {streaming ? (
          <Button
            icon={<StopOutlined />}
            onClick={onStop}
            danger
            size="large"
            style={{ borderRadius: 12, height: 42, width: 42 }}
          />
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!query.trim()}
            size="large"
            style={{ borderRadius: 12, height: 42, width: 42 }}
          />
        )}
      </div>
    </div>
  );
};

export default ChatInput;
