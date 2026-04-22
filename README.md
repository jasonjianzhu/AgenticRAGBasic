# AgenticRAG - 智能知识库与问答平台

面向储能行业的智能知识库管理与 RAG 问答平台。系统分为三个独立服务，按需启动：

- **知识库管理** — 文档上传、解析、Chunk 构建、向量索引
- **RAG 问答** — 混合检索、Query 改写、带引用的流式答案生成
- **Agent 对话** — 多轮对话、工具调用（Phase 3）

## 技术栈

| 层次 | 选型 |
|------|------|
| 后端 | Python 3.11+, FastAPI, SQLAlchemy 2.x (async), Alembic |
| 数据库 | PostgreSQL 16 |
| 向量库 | Qdrant |
| 队列 | Redis + RQ（仅知识库管理需要） |
| 文档解析 | Docling (fast/balanced/accurate) |
| Embedding | BGE-M3 本地加载（FlagEmbedding，dense + sparse 一次推理） |
| LLM | MiniMax M2.7（OpenAI-compatible API） |
| Reranker | TEI Reranker（可选，默认关闭） |
| 观测 | Langfuse（可选） |
| 前端 | React 19 + TypeScript + Vite + Ant Design 5 |
| 测试 | pytest, pytest-asyncio, httpx |

## 项目结构

```
backend/
├── app/
│   ├── main.py                    # 共享 app 工厂
│   ├── main_knowledge.py          # 知识库服务入口 (port 8000)
│   ├── main_rag.py                # RAG 服务入口 (port 8001)
│   ├── main_agent.py              # Agent 服务入口 (port 8002, Phase 3)
│   ├── common/                    # 共享层
│   │   ├── core/                  # 配置、日志、依赖注入
│   │   ├── db/                    # ORM 模型、会话管理、Repository
│   │   ├── rag/
│   │   │   ├── embedding/         # Embedding (BGE-M3 本地 + TEI 备选)
│   │   │   └── vector_store/      # 向量存储 (Qdrant)
│   │   └── storage/               # 文件存储抽象
│   ├── knowledge/                 # 知识库管理服务
│   │   ├── api/                   # 路由 + Schema (kb, documents, jobs, search_debug)
│   │   ├── services/              # 业务逻辑 (ingestion, indexing, kb, jobs)
│   │   ├── jobs/                  # 异步任务 (RQ worker)
│   │   └── rag/
│   │       ├── parsing/           # 文档解析 (Docling + 兜底)
│   │       ├── chunking/          # Chunk 切分 (4 种策略 + Registry)
│   │       └── classification/    # 文档类型分类
│   └── rag/                       # RAG 问答服务
│       ├── api/                   # 路由 + Schema (search, answer, config)
│       ├── services/              # RAG 编排 (search → rerank → generate)
│       ├── generation/            # LLM 客户端 (MiniMax)
│       ├── query/                 # Query 处理 (标准化、改写、context 提取)
│       ├── reranking/             # Reranker (TEI, 可选)
│       └── observability/         # Langfuse tracing (可选)
├── migrations/                    # Alembic 迁移
├── tests/                         # 测试 (unit/contract/integration)
├── docker-compose.yml
└── pyproject.toml

frontend/
├── src/
│   ├── pages/
│   │   ├── KnowledgeBase/         # 知识库管理页
│   │   ├── Documents/             # 文档管理页
│   │   ├── SearchDebug/           # 检索调试页
│   │   └── RAGChat/               # RAG 问答页
│   ├── api/
│   │   ├── client.ts              # 知识库 API 客户端
│   │   └── rag.ts                 # RAG API 客户端 (含 SSE)
│   ├── components/AppLayout.tsx   # 布局 + 导航
│   └── types/index.ts             # TypeScript 类型定义
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
# Python 虚拟环境
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e "backend[dev]"

# 前端
cd frontend && npm install
```

### 3. 配置

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，必须配置：
- `EMBEDDING_MODEL_PATH` — BGE-M3 模型本地路径
- `LLM_BASE_URL` + `LLM_API_KEY` — MiniMax API（RAG 问答需要）

### 4. 数据库迁移

先确保 PG 已启动（任意场景的 docker compose up 之后），再执行：

```bash
cd backend
alembic upgrade head
```

## 启动方式

### 场景 A：只跑 RAG 问答（知识库已有数据）

```bash
# 1. 基础设施（PG + Qdrant）
cd backend && docker compose up -d

# 2. 数据库迁移（首次或重建数据库后）
.venv/bin/alembic upgrade head

# 3. RAG 服务
.venv/bin/uvicorn app.main_rag:app --port 8001

# 4. 前端
cd frontend && npm run dev
```

访问 http://localhost:3000/chat

### 场景 B：知识库管理（上传/解析/索引）

```bash
# 1. 基础设施（PG + Qdrant + Redis）
cd backend && docker compose --profile knowledge up -d

# 2. 数据库迁移（首次或重建数据库后）
.venv/bin/alembic upgrade head

# 3. 知识库服务
.venv/bin/uvicorn app.main_knowledge:app --port 8000

# 4. Worker（处理解析和索引任务）
.venv/bin/python -m app.knowledge.jobs.worker

# 5. 前端
cd frontend && npm run dev
```

访问 http://localhost:3000/kb

### 场景 C：全部功能

```bash
# 1. 基础设施
cd backend && docker compose --profile all up -d

# 2. 数据库迁移（首次或重建数据库后）
.venv/bin/alembic upgrade head

# 3. 终端1：知识库服务
.venv/bin/uvicorn app.main_knowledge:app --port 8000

# 4. 终端2：RAG 服务
.venv/bin/uvicorn app.main_rag:app --port 8001

# 5. 终端3：Worker
.venv/bin/python -m app.knowledge.jobs.worker

# 6. 终端4：前端
cd frontend && npm run dev
```

## API 接口

### 知识库管理 (port 8000)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/kb` | POST/GET | 创建/列表知识库 |
| `/kb/{kb_id}` | GET/PUT/DELETE | 知识库详情/更新/删除 |
| `/kb/{kb_id}/build` | POST | 触发索引重建 |
| `/kb/{kb_id}/search_debug` | POST | 检索调试（不含 LLM） |
| `/documents/upload` | POST | 上传文档 |
| `/documents` | GET | 文档列表 |
| `/documents/{doc_id}` | GET/DELETE | 文档详情/删除 |
| `/documents/{doc_id}/enable` | POST | 启用文档 |
| `/documents/{doc_id}/disable` | POST | 禁用文档 |
| `/documents/{doc_id}/chunks` | GET | Chunk 预览 |
| `/jobs` | GET | 任务列表 |
| `/jobs/{job_id}` | GET | 任务详情 |
| `/jobs/{job_id}/retry` | POST | 重试任务 |

### RAG 问答 (port 8001)

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/rag/search` | POST | 检索（含 query 改写、hybrid search、rerank） |
| `/rag/answer` | POST | 问答（SSE 流式，含引用） |
| `/rag/config` | GET/PUT | RAG 运行时配置 |

## 文档处理流程

```
上传 PDF → 入队 ingestion → 解析 (Docling) → Chunk 切分 → 持久化
                                                                ↓
                                                      入队 indexing → Embedding (BGE-M3 dense+sparse) → Qdrant → ready
```

## RAG 问答流程

```
用户提问 → 标准化 → Context 提取 → Query 改写 (LLM)
                                        ↓
                              Embedding → Dense Search + Sparse Search → RRF 融合
                                        ↓
                              Rerank (可选) → Context Packing → 流式答案生成 (LLM)
                                        ↓
                              SSE 输出: trace → citations → tokens → done
```

## 运行测试

```bash
# 单元测试（不需要外部服务）
.venv/bin/python -m pytest backend/tests/ -v

# 跳过集成测试
.venv/bin/python -m pytest backend/tests/ -v -m "not integration"
```

## 配置说明

所有配置项见 `backend/.env.example`，按功能分组：

| 分组 | 说明 | 必需场景 |
|------|------|----------|
| Database | PostgreSQL 连接 | 全部 |
| Qdrant | 向量库连接 | 全部 |
| Redis | 任务队列 | 知识库管理 |
| Embedding | BGE-M3 模型路径 | 全部 |
| LLM | MiniMax API | RAG 问答 |
| Reranker | TEI Reranker（默认关闭） | 可选 |
| RAG | 检索参数（top_k、阈值等） | RAG 问答 |
| Langfuse | LLM 观测（默认关闭） | 可选 |

## License

Private - AgenticRAG Team
