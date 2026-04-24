/**
 * Agent 用户端布局 — 全屏对话界面，科技风浅绿色调
 */
import React from 'react';
import { Layout, Typography, Button, Tooltip } from 'antd';
import { SettingOutlined, RobotOutlined } from '@ant-design/icons';
import { useNavigate, Outlet } from 'react-router-dom';

const { Header, Content } = Layout;
const { Text } = Typography;

const AgentLayout: React.FC = () => {
  const navigate = useNavigate();

  return (
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: 'linear-gradient(135deg, #36cfc9, #13c2c2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 2px 8px rgba(54, 207, 201, 0.3)',
            }}
          >
            <RobotOutlined style={{ color: '#fff', fontSize: 20 }} />
          </div>
          <div>
            <Text strong style={{ fontSize: 17, color: '#08979c', letterSpacing: 0.5 }}>
              晶科智能运维
            </Text>
            <Text style={{ fontSize: 12, color: '#8c8c8c', marginLeft: 8 }}>
              储能智能助手
            </Text>
          </div>
        </div>
        <Tooltip title="返回首页">
          <Button
            type="text"
            icon={<SettingOutlined />}
            onClick={() => navigate('/')}
            style={{ color: '#8c8c8c' }}
          >
            返回首页
          </Button>
        </Tooltip>
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
};

export default AgentLayout;
