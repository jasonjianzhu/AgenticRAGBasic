import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AppLayout from '@/components/AppLayout';
import KnowledgeBasePage from '@/pages/KnowledgeBase';
import DocumentsPage from '@/pages/Documents';
import SearchDebugPage from '@/pages/SearchDebug';

const App: React.FC = () => (
  <ConfigProvider locale={zhCN}>
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/kb" element={<KnowledgeBasePage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/search" element={<SearchDebugPage />} />
          <Route path="*" element={<Navigate to="/kb" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </ConfigProvider>
);

export default App;
