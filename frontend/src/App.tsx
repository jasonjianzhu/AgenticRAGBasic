import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { agentTheme, adminTheme } from '@/theme';
import AdminLayout from '@/components/AdminLayout';
import AgentLayout from '@/components/AgentLayout';
import KnowledgeBasePage from '@/pages/KnowledgeBase';
import DocumentsPage from '@/pages/Documents';
import SearchDebugPage from '@/pages/SearchDebug';
import RAGChatPage from '@/pages/RAGChat';
import AgentChatPage from '@/pages/AgentChat';

/** 管理后台（带 adminTheme） */
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

/** Agent 用户端（带 agentTheme） */
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
  <BrowserRouter>
    <Routes>
      {/* Agent 用户端 — 默认入口 */}
      <Route path="/agent/*" element={<AgentApp />} />
      {/* 管理后台 */}
      <Route path="/admin/*" element={<AdminApp />} />
      {/* 默认跳转到 Agent */}
      <Route path="*" element={<Navigate to="/agent" replace />} />
    </Routes>
  </BrowserRouter>
);

export default App;
