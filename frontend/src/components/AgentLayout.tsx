/**
 * Agent 用户端布局 — 全屏对话界面，科技风浅绿色调
 */
import React from 'react';
import { Layout } from 'antd';
import { Outlet } from 'react-router-dom';

const { Header, Content } = Layout;

const AgentLayout: React.FC = () => (

    <Layout
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #e6fffb 0%, #f0faf9 40%, #e8f7f6 100%)',
      }}
    >
      {/* 顶部导航栏 */}
      <Header
        style={{
          background: 'rgba(255, 255, 255, 0.72)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid rgba(54, 207, 201, 0.15)',
          padding: '0 24px',
          height: 56,
          lineHeight: '56px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        <span style={{ fontSize: 20, fontWeight: 700, color: '#008544', letterSpacing: 1 }}>
          储能Agent问答平台
        </span>
        <img
          src="/assets/jinko-logo-cn.png"
          alt="晶科储能"
          style={{ height: 35, objectFit: 'contain' }}
        />
      </Header>

      {/* 内容区 */}
      <Content
        style={{
          flex: 1,
          display: 'flex',
          overflow: 'hidden',
          height: 'calc(100vh - 56px)',
        }}
      >
        <Outlet />
      </Content>
    </Layout>
);

export default AgentLayout;
