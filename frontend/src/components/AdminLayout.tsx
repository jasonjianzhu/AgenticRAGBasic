/**
 * 管理后台布局 — 知识库管理、文档管理、检索调试、RAG 问答
 * 深色侧边栏 + 白色内容区
 */
import React from 'react';
import { Layout, Menu, Typography } from 'antd';
import {
  DatabaseOutlined,
  FileTextOutlined,
  SearchOutlined,
  MessageOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';

const { Sider, Header, Content } = Layout;
const { Text } = Typography;

const menuItems = [
  { key: '/admin/kb', icon: <DatabaseOutlined />, label: '知识库管理' },
  { key: '/admin/documents', icon: <FileTextOutlined />, label: '文档管理' },
  { key: '/admin/search', icon: <SearchOutlined />, label: '检索调试' },
  { key: '/admin/chat', icon: <MessageOutlined />, label: 'RAG 问答' },
];

const AdminLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey =
    menuItems.find((m) => location.pathname.startsWith(m.key))?.key ?? '/admin/kb';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} breakpoint="lg" collapsedWidth={60} theme="dark">
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
          }}
        >
          <Text strong style={{ color: '#36cfc9', fontSize: 18, letterSpacing: 1 }}>
            AgenticRAG
          </Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
        <div style={{ position: 'absolute', bottom: 16, width: '100%', textAlign: 'center' }}>
          <a
            onClick={() => navigate('/agent')}
            style={{ color: '#36cfc9', fontSize: 13, cursor: 'pointer' }}
          >
            <RobotOutlined /> 切换到 Agent 对话
          </a>
        </div>
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            height: 56,
          }}
        >
          <Text strong style={{ fontSize: 16 }}>管理后台</Text>
        </Header>
        <Content
          style={{
            margin: 20,
            padding: 24,
            background: '#fff',
            borderRadius: 12,
            overflow: 'auto',
            minHeight: 280,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AdminLayout;
