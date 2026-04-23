# AgenticRAG - 智能知识库与问答平台

面向储能行业的智能知识库管理与 RAG 问答平台。系统分为三个独立服务，按需启动：

- **知识库管理** — 文档上传、解析、Chunk 构建、向量索引
- **RAG 问答** — 混合检索、Query 改写、带引用的流式答案生成
- **Agent 对话** — 多轮对话、意图路由、SQL 数据分析、图表生成、知识问答

## 技术栈

| 层次 | 选型 |
|------|------|
| 后端 | Python 3.11+, FastAPI, SQLAlchemy 2.x (async), Alembic |
| 数据库 | PostgreSQL 16（主库 + 业务库） |
| 向量库 | Qdrant |
| 队列 | Redis + RQ（仅知识库管理需要） |
| 文档解析 | Docling (fast/balanced/accurate) |
| Embedding | BGE-M3 本地加载（FlagEmbedding，dense + sparse 一次推理） |
| LLM | MiniMax M2.7（OpenAI-compatible API） |
| Agent 框架 | PydanticAI（工具调用编排、多轮对话） |
| SQL 校验 | sqlparse + 白名单（只读、表白名单、行数限制） |
| 图表渲染 | ECharts（前端） |
| Reranker | BGE-Reranker-v2-M3 本地 / TEI（可选） |
| 观测 | Langfuse（可选） |
| 前端 | React 19 + TypeScript + Vite + Ant Design 5 |

## 项目结构

```
backend/
├── app/
│   ├── main.py                    # 共享 app 工厂
│   ├── main_knowledge.py          # 知识库服务入口 (port 8000)
│   ├── main_rag.py                # RAG 服务入口 (port 8001)
│   ├── main_agent.py              # Agent 服务入口 (port 8002)
│   ├── common/                    # 共享层
│   │   ├── core/                  # 配置、日志、依赖注入
│   │   ├── db/                    # ORM 模型、会话管理、Repository
│   │   ├── rag/
│   │   │   ├── embedding/         # Embedding (BGE-M3 本地 + TEI 备选)
│   │   │   └── vector_store/      # 向量存储 (Qdrant)
│   │   └── storage/               # 文件存储抽象
│   ├── knowledge/                 # 知识库管理服务
│   │   ├── api/                   # 路由 + Schema
│   │   ├── services/              # 业务逻辑 (ingestion, indexing)
│   │   ├── jobs/                  # 异步任务 (RQ worker)
│   │   └── rag/                   # 解析、切片、分类
│   ├── rag/                       # RAG 问答服务
│   │   ├── api/                   # 路由 + Schema
│   │   ├── services/              # RAG 编排 (search → rerank → generate)
│   │   ├── generation/            # LLM 客户端 (MiniMax)
│   │   ├── query/                 # Query 处理
│   │   └── reranking/             # Reranker
│   └── agent/                     # Agent 对话服务
│       ├── api/                   # 路由 (chat SSE, sessions, db_admin)
│       ├── core/                  # PydanticAI Agent 定义 + system prompt
│       ├── tools/                 # 工具 (rag_search, sql_query, generate_chart)
│       ├── sql/                   # SQL 校验、执行、schema 加载
│       └── services/              # 对话编排、会话管理
├── migrations/                    # Alembic 迁移
├── scripts/
│   └── init_business_db.sql       # 业务库建表 + mock 数据
├── docker-compose.yml
└── pyproject.toml

frontend/
├── src/
│   ├── pages/
│   │   ├── KnowledgeBase/         # 知识库管理页
│   │   ├── Documents/             # 文档管理页
│   │   ├── SearchDebug/           # 检索调试页
│   │   ├── RAGChat/               # RAG 问答页
│   │   └── AgentChat/             # Agent 对话页（含图表、数据表格）
│   ├── api/
│   │   ├── client.ts              # 知识库 API 客户端
│   │   ├── rag.ts                 # RAG API 客户端
│   │   └── agent.ts               # Agent API 客户端 (含 SSE)
│   ├── types/
│   │   ├── index.ts               # 通用类型
│   │   └── agent.ts               # Agent 类型定义
│   └── components/AppLayout.tsx   # 布局 + 导航
├── package.json
└── vite.config.ts
```

## 快速开始

### 1. 环境要求

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- BGE-M3 模型（本地路径，如 `~/LocalLLMs/bge-m3`）

### 2. 安装依赖

```bash
# Python 虚拟环境（在项目根目录）
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e "backend[dev]"

# 前端（在项目根目录）
cd ../frontend
npm install
```

### 3. 配置

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，必须配置：
- `EMBEDDING_MODEL_PATH` — BGE-M3 模型本地路径
- `LLM_BASE_URL` + `LLM_API_KEY` — MiniMax API

### 4. 数据库迁移

```bash
cd backend
../.venv/bin/alembic upgrade head
```

## 启动方式

> 以下命令中，后端命令在 `backend/` 目录下执行，前端命令在 `frontend/` 目录下执行。

### 场景 A：Agent 对话（数据分析 + 知识问答）

最常用的场景：

```bash
# 1. 基础设施（PG 主库 + Qdrant + 业务库）
cd backend
docker compose up -d

# 2. 数据库迁移（首次）
../.venv/bin/alembic upgrade head

# 3. 知识库服务（Agent 页面需要获取知识库列表）
../.venv/bin/uvicorn app.main_knowledge:app --port 8000 --reload

# 4. Agent 服务（另一个终端，不加 --reload，模型加载慢）
../.venv/bin/uvicorn app.main_agent:app --port 8002

# 5. 前端（另一个终端）
cd ../frontend
npm run dev
```

访问 http://localhost:3000/agent

> 业务库（port 5433）首次启动时自动执行 `scripts/init_business_db.sql`，创建设备、指标、告警、维护记录表并灌入 mock 数据。

### 场景 B：RAG 问答（独立验证检索效果）

不需要 Agent，直接测试 RAG 检索和问答：

```bash
# 1. 基础设施（PG + Qdrant）
cd backend
docker compose up -d

# 2. 数据库迁移（首次）
../.venv/bin/alembic upgrade head

# 3. RAG 服务
../.venv/bin/uvicorn app.main_rag:app --port 8001 --reload

# 4. 前端（另一个终端）
cd ../frontend
npm run dev
```

访问 http://localhost:3000/chat（RAG 问答）或 http://localhost:3000/search（检索调试）

> 需要 Qdrant 里已有向量数据。如果还没有，先走场景 C 上传文档。

### 场景 C：知识库管理（上传/解析/索引）

需要额外启动 Redis 和 Worker：

```bash
# 1. 基础设施（含 Redis）
cd backend
docker compose --profile knowledge up -d

# 2. 数据库迁移（首次）
../.venv/bin/alembic upgrade head

# 3. 知识库服务
../.venv/bin/uvicorn app.main_knowledge:app --port 8000 --reload

# 4. Worker（另一个终端）
../.venv/bin/python -m app.knowledge.jobs.worker

# 5. 前端（另一个终端）
cd ../frontend
npm run dev
```

访问 http://localhost:3000/kb

### 场景 D：全部功能

```bash
# 1. 基础设施
cd backend
docker compose --profile all up -d

# 2. 数据库迁移（首次）
../.venv/bin/alembic upgrade head

# 3. 终端1：知识库服务
../.venv/bin/uvicorn app.main_knowledge:app --port 8000 --reload

# 4. 终端2：Agent 服务（不加 --reload，模型加载慢）
../.venv/bin/uvicorn app.main_agent:app --port 8002

# 5. 终端3：Worker
../.venv/bin/python -m app.knowledge.jobs.worker

# 6. 终端4：前端
cd ../frontend
npm run dev
```

> Agent 服务内部直接调用 RAG 代码（import，非 HTTP），不需要单独启动 RAG 服务（port 8001）。
> 如果需要独立使用 RAG 问答页（/chat），才需要 `uvicorn app.main_rag:app --port 8001`。

## API 接口

### 知识库管理 (port 8000)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/kb` | POST/GET | 创建/列表知识库 |
| `/kb/{kb_id}` | GET/PUT/DELETE | 知识库详情/更新/删除 |
| `/kb/{kb_id}/build` | POST | 触发索引重建 |
| `/kb/{kb_id}/search_debug` | POST | 检索调试 |
| `/documents/upload` | POST | 上传文档 |
| `/documents` | GET | 文档列表 |
| `/documents/{doc_id}` | GET/DELETE | 文档详情/删除 |
| `/documents/{doc_id}/chunks` | GET | Chunk 预览 |
| `/jobs` | GET | 任务列表 |
| `/jobs/{job_id}` | GET | 任务详情 |
| `/jobs/{job_id}/retry` | POST | 重试任务 |

### RAG 问答 (port 8001)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/rag/search` | POST | 检索（hybrid search + rerank） |
| `/rag/answer` | POST | 问答（SSE 流式，含引用） |
| `/rag/config` | GET/PUT | RAG 运行时配置 |

### Agent 对话 (port 8002)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/agent/chat` | POST | 对话（SSE 流式，支持工具调用） |
| `/agent/sessions` | GET | 会话列表 |
| `/agent/sessions/{id}` | GET/DELETE | 会话详情/删除 |
| `/agent/db/schema` | GET | 业务库表结构 |
| `/agent/db/test` | POST | 业务库连接测试 |

#### Agent SSE 事件类型

| 事件 | 说明 |
|------|------|
| `tool_start` | 工具调用开始（工具名 + 参数摘要） |
| `tool_result` | 工具调用结果（摘要） |
| `data_table` | SQL 查询结果（列名 + 行数据） |
| `chart` | ECharts 图表配置 JSON |
| `citation` | 知识库引用来源 |
| `token` | 流式文本 token |
| `done` | 对话完成（含 session_id） |
| `error` | 错误信息 |

## Agent 工具

| 工具 | 说明 | 触发场景 |
|------|------|----------|
| `rag_search` | 检索知识库 | 技术问题、产品参数、告警处理方法 |
| `sql_query` | 查询业务数据库 | 运行数据、统计分析、设备状态、告警记录 |
| `generate_chart` | 生成 ECharts 图表 | 数据适合可视化时自动调用 |

Agent 由 LLM 自主决策使用哪些工具，支持单工具、多工具协同、混合查询。

### SQL 安全策略

- 只允许 SELECT 语句
- 表白名单（通过 `BUSINESS_DB_ALLOWED_TABLES` 配置）
- 自动注入 LIMIT（默认 500 行）
- 查询超时控制（默认 30s）
- 只读数据库用户

## 配置说明

所有配置项见 `backend/.env.example`，按功能分组：

| 分组 | 说明 | 必需场景 |
|------|------|----------|
| Database | PostgreSQL 主库连接 | 全部 |
| Qdrant | 向量库连接 | 全部 |
| Redis | 任务队列 | 知识库管理 |
| Embedding | BGE-M3 模型路径 | 全部 |
| LLM | MiniMax API | RAG 问答 / Agent |
| Business DB | 业务数据库（只读） | Agent 数据分析 |
| Agent | 上下文窗口、会话过期 | Agent |
| Reranker | BGE-Reranker（默认开启） | 可选 |
| RAG | 检索参数（top_k、阈值等） | RAG 问答 |
| Langfuse | LLM 观测（默认关闭） | 可选 |

### 业务数据库配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `BUSINESS_DB_URL` | `postgresql+asyncpg://readonly:readonly@localhost:5433/energy_business` | 只读连接串 |
| `BUSINESS_DB_ALLOWED_TABLES` | `*` | 允许查询的表（逗号分隔，`*` 全部） |
| `BUSINESS_DB_QUERY_TIMEOUT` | `30` | 查询超时（秒） |
| `BUSINESS_DB_MAX_ROWS` | `500` | 单次查询最大行数 |

## Docker 服务

| 服务 | 端口 | Profile | 说明 |
|------|------|---------|------|
| postgres | 5432 | 默认 | 主数据库 |
| qdrant | 6333 | 默认 | 向量库 |
| business-db | 5433 | 默认 | 业务数据库（含 mock 数据） |
| redis | 6379 | knowledge / all | 任务队列 |

## License

Private - AgenticRAG Team
