# 第三阶段 Backlog：Agent 构建

## 已完成

### 核心功能

| 项目 | 说明 | 状态 |
|------|------|------|
| PydanticAI Agent 框架 | Agent 定义、工具注册、system prompt | ✅ |
| 意图路由 | LLM 自主决策调用 rag_search / sql_query / generate_chart | ✅ |
| rag_search 工具 | 调用 RAG 服务检索知识库，返回带引用的结果 | ✅ |
| sql_query 工具 | LLM 生成 SQL → 校验 → 执行 → 返回摘要（不返回原始表格） | ✅ |
| generate_chart 工具 | 根据数据生成 ECharts 配置 JSON | ✅ |
| SQL 安全校验 | 只读检查、表白名单、LIMIT 注入、超时控制 | ✅ |
| 业务数据库连接 | 独立只读连接池，schema 自动加载注入 prompt | ✅ |
| 会话管理 | 创建、列表、详情、删除（chat_sessions + chat_messages） | ✅ |
| 多轮对话 | 历史消息传入 Agent，支持追问，上下文窗口 20 条 | ✅ |
| SSE 流式输出 | event_stream_handler 实现 thinking 实时展示 + 完整文本输出 | ✅ |
| Thinking 过程展示 | ThinkingPartDelta 实时展示，回答完成后清除 | ✅ |
| 工具调用次数限制 | UsageLimits 硬限制 6 次 + prompt 软约束（rag 3/sql 2/chart 1） | ✅ |
| Agent 对话 API | POST /agent/chat（SSE）、GET/DELETE /agent/sessions | ✅ |
| 业务库管理 API | GET /agent/db/schema、POST /agent/db/test | ✅ |
| Mock 业务数据库 | Docker 自动建表灌数据（devices/metrics/alarms/maintenance） | ✅ |
| Alembic 迁移 003 | chat_sessions + chat_messages 表 | ✅ |
| MiniMax Anthropic API | Agent + RAG 统一使用 Anthropic-compatible API，thinking 从根源分离 | ✅ |
| 图表配置持久化 | chart 数据保存到 message metadata，切换页面后图表可恢复 | ✅ |
| 会话数据及时提交 | session + user 消息创建后立即 commit，解决后台 task 外键约束 | ✅ |

### 前端

| 项目 | 说明 | 状态 |
|------|------|------|
| 首页入口 | 5 个功能方块（知识库/文档/检索/RAG/Agent），点击跳转 | ✅ |
| Agent 对话页 | 全屏布局、会话侧边栏、消息列表、输入框 | ✅ |
| 工具调用展示 | ToolCallDisplay（工具名 + 参数 + 结果） | ✅ |
| ECharts 图表渲染 | ChartRenderer（setTimeout 100ms 确保 DOM 就绪） | ✅ |
| 引用来源展示 | CitationPanel 折叠面板（文档名 + 页码 + 摘要） | ✅ |
| Thinking 展示 | 灰色斜体实时显示思考过程，回答完成后清除 | ✅ |
| 会话侧边栏 | 新建、切换、删除会话 | ✅ |
| 会话持久化 | localStorage 记住 sessionId，切回自动恢复（含图表），断连重试 | ✅ |
| 知识库选择器 | 选择知识库用于 rag_search | ✅ |
| 管理后台/用户端分离 | /admin/*（管理后台）、/agent（用户端）独立路由和主题 | ✅ |
| 浅绿科技风 UI | agentTheme/adminTheme、毛玻璃效果、渐变气泡 | ✅ |
| 平台改名 | 知识管理智能问答测试平台 | ✅ |
| LLM 垃圾内容过滤 | ReactMarkdown components 拦截 img + URL 编码段落 | ✅ |
| think 标签清理统一 | utils/content.ts stripThinkTags() 消除重复正则 | ✅ |
| 回答气泡宽度 | 从 75% 调到 90% | ✅ |

### Bug 修复

| 问题 | 修复 | 状态 |
|------|------|------|
| PydanticAI v1.86 API 不兼容 | system_prompt→instructions, result_type→output_type, result.data→result.response.text | ✅ |
| SQL 表白名单失效 | _extract_tables 跳过 Whitespace token | ✅ |
| SSE 事件丢失导致白屏 | currentEvent 提到 while 循环外 | ✅ |
| Decimal 序列化崩溃 | SQL executor Decimal→float | ✅ |
| 切换页面对话丢失 | localStorage 持久化 + 独立 DB session 保存 + 图表 metadata 持久化 | ✅ |
| assistant 消息外键约束失败 | session + user 消息创建后立即 commit | ✅ |
| 图表不渲染 | 简化 ChartRenderer，去掉 React.memo/ResizeObserver，用 setTimeout | ✅ |
| run_stream 回答中断 | 改回 agent.run() + event_stream_handler | ✅ |
| 文本内容截断 | 文本输出改用 result.response.text 完整输出 | ✅ |
| thinking 内容泄漏 | Anthropic API ThinkingPartDelta 类型识别 | ✅ |
| 工具调用无限循环 | UsageLimits(tool_calls_limit=6) + prompt 软约束 | ✅ |
| LLM 输出管道符原始数据 | sql_query to_text() 改为返回摘要 | ✅ |
| LLM 输出破碎图片/URL 编码 | ReactMarkdown img→null + p 过滤 URL 编码段落 | ✅ |
| 意图识别被历史上下文污染 | prompt 加独立判断意图指引 | ✅ |
| max_tokens 2048 不够 | 调到 8192 | ✅ |
| AnthropicModel provider 传参 | 用 AnthropicModel 对象传入 Agent | ✅ |
| transformers 版本冲突 | 升级到 4.57.6 兼容 tokenizers 0.22 | ✅ |
| 前端白屏 | 删除残留的 Layout 引用 | ✅ |
| Agent RAG检索结果与RAG问答不一致 | 双重改写（Agent改query + RAG rewrite）导致语义偏移，Agent侧关闭RAG rewrite，prompt约束直接用原始问题 | ✅ |
| RAG pipeline过滤排序职责混乱 | RRF threshold移到rerank之前，去掉reranker内部硬编码过滤，reranker只排序不过滤 | ✅ |
| Agent检索内容被截断500字符 | to_text()去掉content[:500]截断，与RAG问答保持一致 | ✅ |
| 引用来源显示不相关内容 | citation改为Agent回答后解析[1][2]标记，只发送被实际引用的来源 | ✅ |
| Agent用通用知识回答而非知识库内容 | prompt新增"回答原则"，强制知识问答基于检索结果，禁止用自身知识替代 | ✅ |
| RRF score threshold过低形同虚设 | 从0.01调整为0.012，过滤单列表排名20+的噪音 | ✅ |
| LLM编造数据（电压电流等数值） | prompt新增总则禁止编造，数据必须来自sql_query，去掉"数据查询不受限制" | ✅ |
| LLM过度补充用户没问的参数 | prompt约束只回答用户问的问题，不列出"未找到XXX" | ✅ |
| minimax.py stream方法缩进错误导致500 | 加日志时async for循环体缩进丢失，修复缩进 | ✅ |
| HTTP请求日志中间件导致SSE 500 | BaseHTTPMiddleware缓冲StreamingResponse，暂时移除中间件 | ✅ |
| LLM数据编造（错误计算/换算） | harness模块：数值校验+LLM重跑修正+降级展示原始数据 | ✅ |
| LLM不调工具直接编造数值 | harness check_no_tool_fabrication检测 | ✅ |
| LLM过度推断（预计/趋势表明） | harness check_speculation模式匹配检测 | ✅ |
| harness内联在chat.py中 | 抽象为独立模块 app/agent/harness/（checks.py + correction.py） | ✅ |
| harness阈值/正则误伤正常问答 | 方案A（LLM验证）→ 验证LLM也会误判 → 方案C（纯prompt约束+轻量硬约束） | ✅ |
| harness强制重跑干扰闲聊 | 去掉强制重跑，harness模块保留为扩展点，当前不拦截 | ✅ |
| 引用编号[1][2]容易搞混 | 改为【文档名 第X页】语义标识，代码做确定性字符串匹配 | ✅ |
| SQL查询timedelta类型JSON序列化报错 | executor._serialize_row增加timedelta→str转换 | ✅ |

### 文档与配置

| 项目 | 说明 | 状态 |
|------|------|------|
| README 更新 | 4 种启动场景、Agent 不加 --reload、前端路径修正 | ✅ |
| PRD 全面完善 | 会话持久化、工具扩展、多语言/反馈/导出、并发控制、LLM 可替换、完成标准 17 条 | ✅ |
| .env 配置 | Agent + Business DB + Anthropic API + max_tokens 8192 | ✅ |
| Agent 启动预热 | lifespan 预加载 Embedding、Reranker、Agent 单例 | ✅ |
| RAG MiniMaxClient | 改用 Anthropic Messages API，统一 Agent 一致 | ✅ |
| Prompt 优化 | 意图独立判断、工具调用限制、禁止图片/重复数据、SQL 合并查询 | ✅ |

---

## 待完成 / 已知问题

### 中优先级

| 项目 | 说明 | 优先级 |
|------|------|--------|
| HTTP请求日志 | 用纯ASGI中间件实现请求日志和request_id串联，BaseHTTPMiddleware与SSE不兼容 | P2 |
| 图表 prompt 优化 | system prompt 增加图表生成示例 | P2 |
| 工具调用失败降级 | 单个工具失败时返回错误说明，不中断对话 | P2 |
| 多轮对话上下文优化 | 工具调用结果纳入历史消息 | P2 |
| 会话标题智能生成 | 用 LLM 生成更好的标题 | P2 |
| 管理后台样式适配 | 管理后台页面适配新主题色 | P2 |
| debug 日志清理 | 移除 agent_result / agent_save_start 等调试日志 | P2 |

### 低优先级

| 项目 | 说明 | 优先级 |
|------|------|--------|
| 会话过期清理 | 超过 24 小时的会话自动归档 | P3 |
| 混合查询联调 | SQL + RAG 复杂场景端到端验证 | P3 |
| DataTable 可选展示 | SQL 结果表格作为可选功能 | P3 |
| Embedding 进度条关闭 | show_progress=False | P3 |
| 前端单元测试 | Agent 组件测试 | P3 |
| 后端单元测试 | SQL validator、chart tool、session service 测试 | P3 |

---

## 分支信息

- **分支**: `feature/phase3-agent`（基于 `feature/phase2-rag`）
- **Commit 数**: 50+
- **涉及文件**: 后端 Agent 模块、RAG MiniMaxClient、前端 AgentChat 页面、首页、主题、路由、PRD、README
