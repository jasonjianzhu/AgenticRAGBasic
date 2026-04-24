import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { agentTheme, adminTheme } from '@/theme';
import AdminLayout from '@/components/AdminLayout';
import AgentLayout from '@/components/AgentLayout';
import HomePage from '@/pages/Home';
import KnowledgeBasePage from '@/pages/KnowledgeBase';
import DocumentsPage from '@/pages/Documents';
import SearchDebugPage from '@/pages/SearchDebug';
import RAGChatPage from '@/pages/RAGChat';
import AgentChatPage from '@/pages/AgentChat';

/** 管理后台 */
const AdminApp: React.FC = () => (
  <ConfigProvider locale={zhCN} theme={adminTheme}>
    <Routes>
      <Route element={<AdminLayout />}>
        <Route path="kb" element={<KnowledgeBasePage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="search" element={<SearchDebugPage />} />
        <Route path="chat" element={<RAGChatPage />} />
        <Route path="*" element={<Navigate to="kb" replace />} />
      </Route>
    </Routes>
  </ConfigProvider>
);

/** Agent 用户端 */
const AgentApp: React.FC = () => (
  <ConfigProvider locale={zhCN} theme={agentTheme}>
    <Routes>
      <Route element={<AgentLayout />}>
        <Route index element={<AgentChatPage />} />
      </Route>
    </Routes>
  </ConfigProvider>
);

const App: React.FC = () => (
  <ConfigProvider locale={zhCN} theme={agentTheme}>
    <BrowserRouter>
      <Routes>
        {/* 首页 — 功能入口 */}
        <Route path="/" element={<HomePage />} />
        {/* Agent 用户端 */}
        <Route path="/agent/*" element={<AgentApp />} />
        {/* 管理后台 */}
        <Route path="/admin/*" element={<AdminApp />} />
        {/* 兜底跳首页 */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </ConfigProvider>
);

export default App;
