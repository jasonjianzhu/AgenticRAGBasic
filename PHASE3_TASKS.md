# 第三阶段任务书：Agent 构建

## 概述

本任务书对应 PRD 第六章，目标是在第二阶段 RAG 服务基础上增加 Agent 能力，同时具备三条核心链路：

1. **知识问答**：调用 RAG 服务检索知识库，生成带引用答案
2. **数据分析**：连接业务数据库，生成 SQL 查询，返回数据 + 图表
3. **混合查询**：多工具协同，汇总多源结果

里程碑：
- **M5**：Agent 框架 + 会话管理 + RAG 工具调用打通
- **M6**：业务数据库 SQL 查询 + 图表生成 + 多轮对话 + Agent 对话页可用

### 前置条件

- 第二阶段全部功能已交付并可用
- RAG 服务（`/rag/search`、`/rag/answer`）可正常调用
- LLM 客户端（MiniMax）可用

---

## 技术栈（新增）

| 层次 | 选型 | 说明 |
|------|------|------|
| Agent 框架 | PydanticAI | 工具调用编排、多轮对话管理 |
| 业务数据库 | PostgreSQL（只读连接） | 储能设备运行数据、告警记录 |
| 图表渲染 | ECharts (前端) | 折线图、柱状图、饼图、表格、面积图等 |
| SQL 校验 | sqlparse + 白名单 | 只读校验、表白名单、行数限制 |

---

## 目录结构（新增/修改）

```
backend/
├── app/
│   ├── agent/                             # [新增] Agent 模块
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── chat.py               # Agent 对话接口（SSE）
│   │   │   │   └── sessions.py            # 会话管理接口
│   │   │   └── schemas/
│   │   │       ├── __init__.py
│   │   │       ├── chat.py               # 对话请求/响应 schema
│   │   │       └── sessions.py            # 会话 schema
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── agent.py                   # PydanticAI Agent 定义 + system prompt
│   │   │   └── prompts.py                 # Agent system prompt 模板
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── rag_search.py              # rag_search_tool
│   │   │   ├── rag_answer.py              # rag_answer_tool
│   │   │   ├── document_lookup.py         # document_lookup_tool
│   │   │   ├── sql_query.py               # sql_query_tool
│   │   │   └── chart.py                   # chart_tool
│   │   ├── sql/
│   │   │   ├── __init__.py
│   │   │   ├── validator.py               # SQL 安全校验（只读、白名单、行数限制）
│   │   │   ├── executor.py                # SQL 执行器（只读连接、超时控制）
│   │   │   └── schema_loader.py           # 业务数据库 schema 加载（注入 prompt）
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── chat.py                    # 对话业务逻辑（调用 Agent、管理流式输出）
│   │       └── session.py                 # 会话 CRUD
│   ├── common/
│   │   ├── db/
│   │   │   ├── models.py                 # [修改] 新增 ChatSession + ChatMessage 模型
│   │   │   └── repositories/
│   │   │       └── sessions.py            # [新增] 会话 repository
│   │   └── core/
│   │       └── config.py                  # [修改] 新增 Agent / 业务数据库配置项
│   └── main_agent.py                      # [修改] 注册 Agent 路由
├── migrations/
│   └── versions/
│       └── 003_agent_sessions.py          # [新增] 会话表迁移

frontend/
├── src/
│   ├── pages/
│   │   └── AgentChat/                     # [新增] Agent 对话页
│   │       ├── index.tsx                  # 页面主体
│   │       ├── ChatInput.tsx              # 输入组件
│   │       ├── MessageList.tsx            # 消息列表（支持多种内容类型）
│   │       ├── ToolCallDisplay.tsx         # 工具调用过程展示
│   │       ├── DataTable.tsx              # 数据表格组件
│   │       ├── ChartRenderer.tsx          # ECharts 图表渲染组件
│   │       ├── CitationPanel.tsx          # 引用来源展示
│   │       └── SessionSidebar.tsx         # 会话列表侧边栏
│   ├── api/
│   │   └── agent.ts                       # [新增] Agent API client
│   ├── hooks/
│   │   └── useAgentSSE.ts                 # [新增] Agent SSE 流式接收 hook
│   └── types/
│       └── agent.ts                       # [新增] Agent 相关类型定义
```

---

## 任务清单

### Sprint 1：Agent 框架与会话管理（M5 前置）

搭建 Agent 基础框架，实现会话持久化。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P3-S1-01 | 新增 ChatSession + ChatMessage 数据库模型 | ORM 模型 + Alembic 迁移 | 迁移成功，表结构正确 |
| P3-S1-02 | 实现会话 Repository | `SessionRepository`（CRUD + 消息追加 + 历史查询） | 会话可创建、查询、追加消息、删除 |
| P3-S1-03 | 实现会话管理 Service | `SessionService`（创建会话、获取历史、上下文窗口截断） | 上下文窗口 20 条消息，超出截断 |
| P3-S1-04 | 实现会话管理 API | GET/DELETE `/agent/sessions`, GET `/agent/sessions/{id}` | 会话列表、详情、删除可用 |
| P3-S1-05 | 新增 Agent 配置项 | `config.py` 扩展（业务数据库连接、Agent 参数） | 配置项可通过 `.env` 管理 |
| P3-S1-06 | 安装 PydanticAI 依赖 | `pyproject.toml` 新增 pydantic-ai | 依赖可安装，import 正常 |

### Sprint 2：PydanticAI Agent 核心与 RAG 工具（M5）

定义 Agent，接入 RAG 工具，实现知识问答链路。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P3-S2-01 | 定义 Agent system prompt | `prompts.py`（角色定义、工具使用指引、输出格式约束） | prompt 清晰描述 Agent 能力和工具用法 |
| P3-S2-02 | 实现 PydanticAI Agent 定义 | `agent.py`（Agent 实例 + 工具注册） | Agent 可实例化，工具已注册 |
| P3-S2-03 | 实现 `rag_search_tool` | 调用 `RAGService.search()` | 给定 query + kb_ids 返回检索结果 |
| P3-S2-04 | 实现 `rag_answer_tool` | 调用 `RAGService` 生成带引用答案（非流式，收集完整结果） | 返回完整答案文本 + 引用列表 |
| P3-S2-05 | 实现 `document_lookup_tool` | 查询知识库列表、文档信息 | 返回知识库统计或文档元数据 |
| P3-S2-06 | 实现 Agent 对话 Service | `ChatService`（接收消息 → 调用 Agent → 流式输出 SSE 事件） | 知识问答链路端到端可用 |
| P3-S2-07 | 实现 Agent 对话 API | POST `/agent/chat`（SSE 流式） | 发送消息，流式返回答案 + 工具调用过程 |
| P3-S2-08 | 注册 Agent 路由到 main_agent.py | 路由挂载 | Agent 服务可启动，API 可访问 |

### Sprint 3：业务数据库连接与 SQL 工具（M6）

实现数据分析链路的核心：SQL 生成、校验、执行。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P3-S3-01 | 实现业务数据库连接管理 | 只读连接池（独立于主库） | 可连接业务数据库，只读用户 |
| P3-S3-02 | 实现 Schema 加载器 | `SchemaLoader`（读取业务库表结构，生成描述文本） | 可输出表名、字段名、字段类型、注释 |
| P3-S3-03 | 实现 SQL 安全校验器 | `SQLValidator`（只读检查 + 表白名单 + 行数限制注入） | 拒绝非 SELECT 语句，拒绝非白名单表 |
| P3-S3-04 | 实现 SQL 执行器 | `SQLExecutor`（执行查询 + 超时控制 + 结果格式化） | 返回列名 + 行数据，超时 30s |
| P3-S3-05 | 实现 `sql_query_tool` | Agent 工具：LLM 生成 SQL → 校验 → 执行 → 返回结果 | Agent 可自主生成并执行 SQL 查询 |
| P3-S3-06 | Schema 描述注入 Agent prompt | 将表结构描述拼入 system prompt | LLM 能根据 schema 生成正确 SQL |
| P3-S3-07 | 实现管理接口 | GET `/agent/db/schema` + POST `/agent/db/test` | 可查看可用表结构，可测试连接 |

### Sprint 4：图表生成（M6）

实现数据分析的图表输出能力。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P3-S4-01 | 定义图表配置协议 | `ChartConfig` schema（chart_type, title, x_axis, y_axis, series） | 协议支持 line/bar/pie/table/area/stacked_bar |
| P3-S4-02 | 实现 `chart_tool` | Agent 工具：接收数据 + 图表类型 → 输出 ECharts 配置 JSON | 配置可被 ECharts 直接渲染 |
| P3-S4-03 | 图表 prompt 优化 | system prompt 中增加图表生成指引和示例 | LLM 能根据数据选择合适图表类型并生成配置 |
| P3-S4-04 | SSE 事件扩展 | 新增 `tool_start`、`tool_result`、`data_table`、`chart` 事件 | 各事件类型可正确发送和解析 |

### Sprint 5：Agent 对话前端页面（M6）

实现完整的 Agent 对话界面。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P3-S5-01 | 实现 Agent SSE hook | `useAgentSSE`（处理所有事件类型） | 可接收和解析 token/tool_start/tool_result/citation/data_table/chart/done/error |
| P3-S5-02 | 实现会话侧边栏 | `SessionSidebar`（会话列表 + 新建 + 删除） | 可切换会话，新建会话 |
| P3-S5-03 | 实现聊天输入组件 | `ChatInput`（输入框 + 发送按钮） | 可输入消息并发送 |
| P3-S5-04 | 实现消息列表组件 | `MessageList`（支持文本/Markdown/工具调用/表格/图表多种消息类型） | 各类型消息正确渲染 |
| P3-S5-05 | 实现工具调用展示 | `ToolCallDisplay`（折叠面板：工具名 + 参数 + 结果） | 工具调用过程可展开查看 |
| P3-S5-06 | 实现数据表格组件 | `DataTable`（Ant Design Table 渲染 SQL 查询结果） | 表格数据正确展示，支持排序 |
| P3-S5-07 | 实现图表渲染组件 | `ChartRenderer`（ECharts 渲染图表配置） | 折线图/柱状图/饼图/面积图等正确渲染 |
| P3-S5-08 | 实现引用展示 | `CitationPanel`（知识问答场景的引用来源） | 引用信息正确展示 |
| P3-S5-09 | 前端路由与导航 | Agent 对话页接入主导航 | 页面可正常访问和切换 |
| P3-S5-10 | 安装 ECharts 依赖 | `echarts` + `echarts-for-react` | 图表库可用 |

### Sprint 6：多轮对话与集成联调（M6）

完善多轮对话能力，端到端联调。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P3-S6-01 | 多轮对话上下文传递 | 历史消息注入 Agent 调用 | 追问"那 E004 呢？"能继承上文 |
| P3-S6-02 | 工具调用结果纳入历史 | 工具调用和结果作为 assistant/tool 消息存入历史 | 后续对话可引用之前的查询结果 |
| P3-S6-03 | 工具调用失败降级 | 工具异常时 Agent 返回错误说明，不中断对话 | 单个工具失败不影响整体对话 |
| P3-S6-04 | 知识问答链路联调 | 用户提问 → Agent 调用 RAG → 流式答案 + 引用 | 端到端可用 |
| P3-S6-05 | 数据分析链路联调 | 用户提问 → Agent 生成 SQL → 查询 → 表格/图表 | 端到端可用 |
| P3-S6-06 | 混合查询联调 | 用户提问 → Agent 同时调用 SQL + RAG → 汇总 | 多工具协同正确 |
| P3-S6-07 | 前端页面联调 | Agent 对话页与后端 API 对接 | 所有消息类型正确渲染 |
| P3-S6-08 | 更新 README 和 .env.example | 新增配置项说明、Agent 使用说明 | 文档完整 |
| P3-S6-09 | 更新 docker-compose | 如需新增服务（业务数据库 mock） | 开发环境可一键启动 |

---

## 新增数据库表

### chat_sessions

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| title | VARCHAR(200) | 会话标题（取首条消息摘要） |
| status | VARCHAR(50) | 状态（active / archived） |
| metadata | JSONB | 扩展元数据（使用的 kb_ids 等） |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

### chat_messages

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| session_id | UUID FK | 所属会话 |
| role | VARCHAR(50) | 角色（user / assistant / tool） |
| content | TEXT | 消息内容（文本或 JSON） |
| message_type | VARCHAR(50) | 消息类型（text / tool_call / tool_result / chart / data_table） |
| tool_name | VARCHAR(100) | 工具名称（tool 消息时） |
| tool_args | JSONB | 工具参数（tool_call 时） |
| tool_result | JSONB | 工具结果（tool_result 时） |
| metadata | JSONB | 扩展元数据（citations、trace 等） |
| created_at | TIMESTAMPTZ | 创建时间 |

索引：(session_id, created_at)

---

## 新增 API 接口契约

### POST /agent/chat

```json
// Request
{
  "session_id": "uuid (可选，不传则创建新会话)",
  "message": "查一下昨天各站点的故障统计，再告诉我E003告警怎么处理",
  "kb_ids": ["uuid-1"]
}
```

```
// Response: SSE 事件流
Content-Type: text/event-stream

event: tool_start
data: {"tool": "sql_query_tool", "args_summary": "查询昨天各站点故障统计"}

event: tool_result
data: {"tool": "sql_query_tool", "summary": "查询到 5 个站点共 23 条告警记录"}

event: data_table
data: {"columns": ["站点", "告警次数", "最高级别"], "rows": [["站点A", 8, "严重"], ["站点B", 5, "警告"], ...]}

event: chart
data: {"chart_type": "bar", "title": "各站点故障统计", "x_axis": {"label": "站点", "data": ["站点A", "站点B", ...]}, "y_axis": {"label": "告警次数"}, "series": [{"name": "告警次数", "data": [8, 5, ...]}]}

event: tool_start
data: {"tool": "rag_search_tool", "args_summary": "检索 E003 告警处理方法"}

event: tool_result
data: {"tool": "rag_search_tool", "summary": "找到 3 条相关结果"}

event: citation
data: {"index": 1, "document_title": "储能系统维护手册", "page": 42, "chunk_id": "uuid", "snippet": "当出现E003过温告警时..."}

event: token
data: {"content": "## 故障统计\n\n昨天各站点共发生"}

event: token
data: {"content": " 23 条告警..."}

event: token
data: {"content": "\n\n## E003 告警处理\n\n当出现 E003 过温告警时[1]..."}

event: done
data: {"session_id": "uuid", "total_tokens": 350}
```

### GET /agent/sessions

```json
// Response 200
{
  "items": [
    {
      "id": "uuid",
      "title": "查询昨天故障统计",
      "status": "active",
      "created_at": "2026-04-23T10:00:00Z",
      "updated_at": "2026-04-23T10:05:00Z",
      "message_count": 6
    }
  ],
  "total": 15,
  "page": 1,
  "page_size": 20
}
```

### GET /agent/sessions/{session_id}

```json
// Response 200
{
  "id": "uuid",
  "title": "查询昨天故障统计",
  "status": "active",
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "查一下昨天各站点的故障统计",
      "message_type": "text",
      "created_at": "2026-04-23T10:00:00Z"
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "昨天各站点共发生 23 条告警...",
      "message_type": "text",
      "metadata": {
        "tool_calls": ["sql_query_tool"],
        "chart": {"chart_type": "bar", "...": "..."},
        "data_table": {"columns": ["..."], "rows": ["..."]}
      },
      "created_at": "2026-04-23T10:00:05Z"
    }
  ],
  "created_at": "2026-04-23T10:00:00Z",
  "updated_at": "2026-04-23T10:00:05Z"
}
```

### GET /agent/db/schema

```json
// Response 200
{
  "tables": [
    {
      "name": "devices",
      "comment": "设备台账",
      "columns": [
        {"name": "id", "type": "integer", "comment": "主键"},
        {"name": "device_name", "type": "varchar(200)", "comment": "设备名称"},
        {"name": "device_model", "type": "varchar(100)", "comment": "设备型号"},
        {"name": "site_name", "type": "varchar(200)", "comment": "站点名称"},
        {"name": "status", "type": "varchar(50)", "comment": "运行状态"},
        {"name": "installed_at", "type": "timestamptz", "comment": "安装时间"}
      ]
    }
  ]
}
```

---

## 新增配置项

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 业务数据库连接串 | `BUSINESS_DB_URL` | - | 只读连接（postgresql://readonly_user:xxx@host/db） |
| 业务数据库表白名单 | `BUSINESS_DB_ALLOWED_TABLES` | `*` | 逗号分隔的表名，`*` 表示全部 |
| SQL 查询超时 | `BUSINESS_DB_QUERY_TIMEOUT` | `30` | 秒 |
| SQL 最大返回行数 | `BUSINESS_DB_MAX_ROWS` | `500` | 单次查询最大行数 |
| Agent 上下文窗口 | `AGENT_CONTEXT_WINDOW` | `20` | 最近 N 条消息 |
| Agent 会话过期时间 | `AGENT_SESSION_TTL_HOURS` | `24` | 小时 |

---

## 开发顺序

```
Sprint 1 (Agent 框架 + 会话管理)
    ↓
Sprint 2 (PydanticAI Agent + RAG 工具) 依赖 Sprint 1
    ↓
Sprint 3 (业务数据库 + SQL 工具) 可与 Sprint 2 并行
    ↓
Sprint 4 (图表生成) 依赖 Sprint 3
    ↓
Sprint 5 (前端页面) 依赖 Sprint 2 + Sprint 4
    ↓
Sprint 6 (多轮对话 + 联调) 依赖全部
```

---

## 完成标准

- [ ] Agent 对话页面可用（多轮聊天 + 流式输出）
- [ ] 意图路由正确（知识问答 / 数据分析 / 混合查询由 LLM 自主决策）
- [ ] Agent 能调用 RAG 服务进行知识问答（带引用）
- [ ] Agent 能连接业务数据库执行只读 SQL 查询
- [ ] SQL 安全策略生效（只读、白名单、行数限制、超时）
- [ ] 数据查询结果可展示为表格
- [ ] 图表配置可生成，前端 ECharts 渲染正确（折线图/柱状图/饼图等）
- [ ] 多轮对话稳定（上下文继承、追问有效）
- [ ] 工具调用过程可见（tool_start / tool_result 事件）
- [ ] 会话管理可用（创建、列表、详情、删除）
- [ ] 工具调用失败不中断对话（降级处理）
- [ ] 不破坏第二阶段 RAG 功能
- [ ] README 和 .env.example 更新完整
