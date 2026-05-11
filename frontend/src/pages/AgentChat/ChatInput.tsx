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
        <div style={{ marginBottom: 8 }}>
          <Select
            mode="multiple"
            placeholder="知识库"
            value={selectedKBs}
            onChange={onKBChange}
            style={{ width: 100 }}
            size="small"
            maxTagCount={1}
            options={kbs.map((kb) => ({ label: kb.name, value: kb.id }))}
            allowClear
            tagRender={(props) => {
              const { label, closable, onClose } = props;
              return (
                <span
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    padding: '0 8px', borderRadius: 6, fontSize: 12,
                    background: 'rgba(0,166,81,0.1)', color: '#00A651',
                    border: '1px solid rgba(0,166,81,0.2)',
                    maxWidth: 70, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}
                >
                  {label}
                  {closable && (
                    <span onClick={onClose} style={{ cursor: 'pointer', fontSize: 10 }}>✕</span>
                  )}
                </span>
              );
            }}
          />
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
        <TextArea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="问一问"
          autoSize={{ minRows: 1, maxRows: 5 }}
          disabled={streaming}
          style={{
            flex: 1,
            borderRadius: 12,
            padding: '10px 14px',
            fontSize: 15,
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
