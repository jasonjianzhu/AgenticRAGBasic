import React from 'react';
import { Layout, Menu } from 'antd';
import {
  DatabaseOutlined,
  FileTextOutlined,
  SearchOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/kb', icon: <DatabaseOutlined />, label: '知识库管理' },
  { key: '/documents', icon: <FileTextOutlined />, label: '文档管理' },
  { key: '/search', icon: <SearchOutlined />, label: '检索调试' },
  { key: '/chat', icon: <MessageOutlined />, label: 'RAG 问答' },
];

const AppLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = menuItems.find((m) =>
    location.pathname.startsWith(m.key),
  )?.key ?? '/kb';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        breakpoint="lg"
        collapsedWidth={60}
        style={{ background: '#fff' }}
      >
        <div
          style={{
            height: 48,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: 16,
            color: '#1677ff',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          AgenticRAG
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            fontSize: 16,
            fontWeight: 600,
          }}
        >
          知识库管理平台
        </Header>
        <Content style={{ margin: 16, padding: 24, background: '#fff', borderRadius: 8, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;
