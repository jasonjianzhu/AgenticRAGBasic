import React from 'react';
import { Tag, Space, Typography, Spin } from 'antd';
import {
  SearchOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import type { ToolCallInfo } from '@/types/agent';

const { Text } = Typography;

const toolIcons: Record<string, React.ReactNode> = {
  rag_search: <SearchOutlined />,
  sql_query: <DatabaseOutlined />,
  generate_chart: <BarChartOutlined />,
};

const toolLabels: Record<string, string> = {
  rag_search: '知识检索',
  sql_query: '数据查询',
  generate_chart: '生成图表',
};

interface Props {
  toolCalls: ToolCallInfo[];
}

const ToolCallDisplay: React.FC<Props> = ({ toolCalls }) => {
  if (!toolCalls.length) return null;

  return (
    <div style={{ marginBottom: 8 }}>
      {toolCalls.map((tc, idx) => (
        <div
          key={idx}
          style={{
            padding: '6px 10px',
            marginBottom: 4,
            background: '#f6f8fa',
            borderRadius: 6,
            fontSize: 12,
          }}
        >
          <Space size={4}>
            {tc.status === 'running' ? (
              <Spin indicator={<LoadingOutlined style={{ fontSize: 12 }} />} />
            ) : (
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
            )}
            {toolIcons[tc.tool] || <DatabaseOutlined />}
            <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>
              {toolLabels[tc.tool] || tc.tool}
            </Tag>
            <Text type="secondary">{tc.argsSummary}</Text>
          </Space>
          {tc.result && (
            <div style={{ marginTop: 2, paddingLeft: 20 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                → {tc.result}
              </Text>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

export default ToolCallDisplay;
