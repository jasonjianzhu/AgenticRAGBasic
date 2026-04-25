# 第三阶段 Backlog：Agent 构建

## 已完成

### 核心功能

| 项目 | 说明 | 状态 |
|------|------|------|
| PydanticAI Agent 框架 | Agent 定义、工具注册、system prompt | ✅ |
| 意图路由 | LLM 自主决策调用 rag_search / sql_query / generate_chart | ✅ |
| rag_search 工具 | 调用 RAG 服务检索知识库，返回带引用的结果 | ✅ |
| sql_query 工具 | LLM 生成 SQL → 校验 → 执行 → 返回结果 | ✅ |
| generate_chart 工具 | 根据数据生成 ECharts 配置 JSON | ✅ |
| SQL 安全校验 | 只读检查、表白名单、LIMIT 注入、超时控制 | ✅ |
| 业务数据库连接 | 独立只读连接池，schema 自动加载注入 prompt | ✅ |
| 会话管理 | 创建、列表、详情、删除（chat_sessions + chat_messages） | ✅ |
| 多轮对话 | 历史消息传入 Agent，支持追问 | ✅ |
| SSE 流式输出 | event_stream_handler 实现真正 token 级流式 | ✅ |
| Thinking 过程展示 | ThinkingPartDelta 实时展示，回答完成后清除 | ✅ |
| 工具调用次数限制 | UsageLimits 硬限制 6 次 + prompt 软约束（rag 3/sql 2/chart 1） | ✅ |
| Agent 对话 API | POST /agent/chat（SSE）、GET/DELETE /agent/sessions | ✅ |
| 业务库管理 API | GET /agent/db/schema、POST /agent/db/test | ✅ |
| Mock 业务数据库 | Docker 自动建表灌数据（devices/metrics/alarms/maintenance） | ✅ |
| Alembic 迁移 003 | chat_sessions + chat_messages 表 | ✅ |
| MiniMax Anthropic API | Agent + RAG 统一使用 Anthropic-compatible API，thinking 从根源分离 | ✅ |

### 前端

| 项目 | 说明 | 状态 |
|------|------|------|
| 首页入口 | 5 个功能方块（知识库/文档/检索/RAG/Agent），点击跳转 | ✅ |
| Agent 对话页 | 全屏布局、会话侧边栏、消息列表、输入框 | ✅ |
| 工具调用展示 | ToolCallDisplay（工具名 + 参数 + 结果） | ✅ |
| ECharts 图表渲染 | ChartRenderer（ResizeObserver + React.memo） | ✅ |
| 引用来源展示 | CitationPanel 折叠面板（文档名 + 页码 + 摘要） | ✅ |
| Thinking 展示 | 灰色斜体实时显示思考过程，回答完成后清除 | ✅ |
| 会话侧边栏 | 新建、切换、删除会话 | ✅ |
| 会话持久化 | localStorage 记住 sessionId，切回自动恢复，断连重试加载 | ✅ |
| 知识库选择器 | 选择知识库用于 rag_search | ✅ |
| 管理后台/用户端分离 | /admin/*（管理后台）、/agent（用户端）独立路由和主题 | ✅ |
| 浅绿科技风 UI | agentTheme/adminTheme、毛玻璃效果、渐变气泡 | ✅ |
| 平台改名 | 知识管理智能问答测试平台 | ✅ |

### Bug 修复

| 问题 | 修复 | 状态 |
|------|------|------|
| PydanticAI v1.86 API 不兼容 | system_prompt→instructions, result_type→output_type, result.data→result.response.text | ✅ |
| SQL 表白名单失效 | _extract_tables 跳过 Whitespace token | ✅ |
| SSE 事件丢失导致白屏 | currentEvent 提到 while 循环外 | ✅ |
| Decimal 序列化崩溃 | SQL executor Decimal→float | ✅ |
| 切换页面对话丢失 | localStorage 持久化 + 独立 DB session 保存 assistant 消息 | ✅ |
| 图表不渲染 | ResizeObserver 监听容器尺寸 + React.memo 防重渲染 | ✅ |
| run_stream 回答中断 | 改回 agent.run() + event_stream_handler | ✅ |
| thinking 内容泄漏 | Anthropic API: ThinkingPartDelta 类型识别；OpenAI API: buffer 状态机过滤 | ✅ |
| 工具调用无限循环 | UsageLimits(tool_calls_limit=6) 硬限制 + prompt 软约束 | ✅ |
| AnthropicModel provider 传参 | 用 AnthropicModel 对象传入 Agent 而非 provider 参数 | ✅ |
| transformers 版本冲突 | 升级到 4.57.6 兼容 tokenizers 0.22 | ✅ |
| 前端白屏 | 删除残留的 Layout 引用 | ✅ |

### 文档与配置

| 项目 | 说明 | 状态 |
|------|------|------|
| README 更新 | 4 种启动场景、Agent 不加 --reload、前端路径修正 | ✅ |
| PRD 全面完善 | 6.5.1 会话持久化、6.7.1 工具扩展、6.11-6.13 多语言/反馈/导出、7.6 并发控制、7.8 LLM 可替换、7.10 完成标准 17 条 | ✅ |
| .env 配置 | Agent + Business DB + Anthropic API 端点 | ✅ |
| Agent 启动预热 | lifespan 预加载 Embedding、Reranker、Agent 单例 | ✅ |
| RAG MiniMaxClient | 改用 Anthropic Messages API，统一 Agent 一致 | ✅ |
| PHASE3_BACKLOG | 已完成项 + 待办事项整理 | ✅ |

---

## 待完成 / 已知问题

### 中优先级

| 项目 | 说明 | 优先级 |
|------|------|--------|
| Agent 回答质量对比 | 同一问题 Agent 和 RAG 回答可能不同，需对比排查 rag_search 参数传递 | P2 |
| 图表 prompt 优化 | system prompt 增加图表生成示例，提高 LLM 选图表类型准确性 | P2 |
| 工具调用失败降级 | 单个工具失败时 Agent 返回错误说明，不中断对话 | P2 |
| 多轮对话上下文优化 | 工具调用结果纳入历史消息，后续对话可引用之前的查询结果 | P2 |
| 会话标题智能生成 | 当前取首条消息前 50 字，可用 LLM 生成更好的标题 | P2 |
| 管理后台样式适配 | 管理后台页面（知识库/文档/检索/RAG）适配新主题色 | P2 |

### 低优先级

| 项目 | 说明 | 优先级 |
|------|------|--------|
| 会话过期清理 | 超过 24 小时的会话自动归档 | P3 |
| 混合查询联调 | 同时调用 SQL + RAG 的复杂场景端到端验证 | P3 |
| DataTable 可选展示 | SQL 查询结果表格作为可选功能，用户可展开查看 | P3 |
| Embedding 进度条关闭 | FlagEmbedding encode 时 show_progress=False | P3 |
| debug 日志清理 | 移除调试日志 | P3 |
| 前端单元测试 | Agent 组件测试 | P3 |
| 后端单元测试 | SQL validator、chart tool、session service 测试 | P3 |

---

## 分支信息

- **分支**: `feature/phase3-agent`（基于 `feature/phase2-rag`）
- **Commit 数**: 40+
- **涉及文件**: 后端 Agent 模块、RAG MiniMaxClient、前端 AgentChat 页面、首页、主题、路由、PRD、README
