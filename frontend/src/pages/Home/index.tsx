import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Typography } from 'antd';
import {
  DatabaseOutlined,
  FileTextOutlined,
  SearchOutlined,
  MessageOutlined,
  RobotOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

const modules = [
  {
    key: '/admin/kb',
    icon: <DatabaseOutlined />,
    title: '知识库管理',
    desc: '创建和管理知识库，配置检索策略',
    color: '#36cfc9',
    gradient: 'linear-gradient(135deg, #36cfc9, #13c2c2)',
  },
  {
    key: '/admin/documents',
    icon: <FileTextOutlined />,
    title: '文档管理',
    desc: '上传文档、解析、切片、索引构建',
    color: '#40a9ff',
    gradient: 'linear-gradient(135deg, #69c0ff, #1890ff)',
  },
  {
    key: '/admin/search',
    icon: <SearchOutlined />,
    title: '检索测试',
    desc: '调试检索效果，验证索引质量',
    color: '#9254de',
    gradient: 'linear-gradient(135deg, #b37feb, #722ed1)',
  },
  {
    key: '/admin/chat',
    icon: <MessageOutlined />,
    title: 'RAG 问答',
    desc: '基于知识库的检索增强问答',
    color: '#f5a623',
    gradient: 'linear-gradient(135deg, #ffc53d, #fa8c16)',
  },
  {
    key: '/agent',
    icon: <RobotOutlined />,
    title: 'Agent 对话',
    desc: '智能助手，支持数据分析与图表生成',
    color: '#52c41a',
    gradient: 'linear-gradient(135deg, #73d13d, #389e0d)',
  },
];

const HomePage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #e6fffb 0%, #f0f5ff 50%, #f6ffed 100%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 20px',
      }}
    >
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: 56 }}>
        <div
          style={{
            width: 80,
            height: 80,
            borderRadius: 22,
            background: 'linear-gradient(135deg, #36cfc9, #13c2c2)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: 24,
            boxShadow: '0 12px 32px rgba(54, 207, 201, 0.3)',
          }}
        >
          <RobotOutlined style={{ fontSize: 40, color: '#fff' }} />
        </div>
        <div
          style={{
            fontSize: 28,
            fontWeight: 700,
            color: '#08979c',
            letterSpacing: 1,
            marginBottom: 8,
          }}
        >
          晶科智能运维测试实验平台
        </div>
        <div style={{ fontSize: 15, color: '#8c8c8c' }}>
          知识管理 · 智能检索 · 数据分析 · Agent 对话
        </div>
      </div>

      {/* Module Cards */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 20,
          justifyContent: 'center',
          maxWidth: 900,
        }}
      >
        {modules.map((m) => (
          <div
            key={m.key}
            onClick={() => navigate(m.key)}
            style={{
              width: 160,
              height: 180,
              borderRadius: 16,
              background: 'rgba(255, 255, 255, 0.85)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(0, 0, 0, 0.04)',
              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.05)',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 12,
              padding: '20px 16px',
              transition: 'all 0.3s ease',
              position: 'relative',
              overflow: 'hidden',
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget;
              el.style.transform = 'translateY(-6px)';
              el.style.boxShadow = `0 12px 32px ${m.color}30`;
              el.style.borderColor = `${m.color}40`;
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget;
              el.style.transform = 'translateY(0)';
              el.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.05)';
              el.style.borderColor = 'rgba(0, 0, 0, 0.04)';
            }}
          >
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: 14,
                background: m.gradient,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 26,
                color: '#fff',
                boxShadow: `0 4px 12px ${m.color}40`,
              }}
            >
              {m.icon}
            </div>
            <div style={{ fontWeight: 600, fontSize: 15, color: '#262626' }}>
              {m.title}
            </div>
            <Text
              style={{
                fontSize: 12,
                color: '#8c8c8c',
                textAlign: 'center',
                lineHeight: 1.4,
              }}
            >
              {m.desc}
            </Text>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div style={{ marginTop: 56, color: '#bfbfbf', fontSize: 12 }}>
        Powered by AgenticRAG
      </div>
    </div>
  );
};

export default HomePage;
