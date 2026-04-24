/**
 * AgenticRAG 浅绿色科技风主题配置
 */
import type { ThemeConfig } from 'antd';

export const agentTheme: ThemeConfig = {
  token: {
    colorPrimary: '#36cfc9',        // 浅绿主色
    colorBgBase: '#f0faf9',          // 页面底色（极浅绿）
    colorBgContainer: '#ffffff',     // 卡片/容器白色
    colorBgLayout: '#e8f7f6',        // 布局背景
    colorBorderSecondary: '#b5f5ec', // 边框浅绿
    colorLink: '#13c2c2',            // 链接色
    colorSuccess: '#52c41a',
    colorError: '#ff4d4f',
    borderRadius: 12,
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#ffffff',
      headerBg: 'transparent',
      bodyBg: 'transparent',
    },
    Menu: {
      itemBg: 'transparent',
      itemSelectedBg: '#e6fffb',
      itemSelectedColor: '#08979c',
      itemHoverBg: '#f0faf9',
    },
    Button: {
      primaryShadow: '0 2px 8px rgba(54, 207, 201, 0.35)',
    },
    Card: {
      borderRadiusLG: 16,
    },
    Input: {
      borderRadius: 10,
    },
  },
};

/** 管理后台主题（同色系，稍微收敛） */
export const adminTheme: ThemeConfig = {
  token: {
    colorPrimary: '#13c2c2',
    colorBgLayout: '#f5f5f5',
    borderRadius: 8,
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#001529',
      headerBg: '#ffffff',
    },
    Menu: {
      darkItemBg: '#001529',
      darkItemSelectedBg: '#0e4d4d',
    },
  },
};
