import React from 'react';
import { Typography, Collapse } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import type { AgentCitation } from '@/types/agent';

const { Text } = Typography;

interface Props {
  citations: AgentCitation[];
}

const CitationPanel: React.FC<Props> = ({ citations }) => {
  if (!citations.length) return null;

  return (
    <div style={{ marginTop: 8 }}>
      <Collapse
        size="small"
        ghost
        items={[
          {
            key: 'citations',
            label: (
              <Text style={{ fontSize: 12, color: '#08979c' }}>
                <FileTextOutlined /> 引用来源（{citations.length}）
              </Text>
            ),
            children: (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {citations.map((c) => (
                  <div
                    key={c.index}
                    style={{
                      padding: '6px 10px',
                      background: '#f0faf9',
                      borderRadius: 8,
                      borderLeft: '3px solid #36cfc9',
                      fontSize: 12,
                    }}
                  >
                    <div style={{ fontWeight: 500, color: '#08979c', marginBottom: 2 }}>
                      [{c.index}] {c.document_title}
                      {c.page != null && (
                        <span style={{ color: '#8c8c8c', fontWeight: 400 }}>
                          {' '}· 第{c.page}页
                        </span>
                      )}
                    </div>
                    <div style={{ color: '#595959', lineHeight: 1.5 }}>
                      {c.snippet}
                    </div>
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default CitationPanel;
