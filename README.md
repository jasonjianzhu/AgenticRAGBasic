# AgenticRAG - 智能知识库与问答平台

面向储能行业的智能知识库管理平台，支持文档上传、解析、Chunk 构建、向量索引和混合检索调试。

## 技术栈

| 层次 | 选型 |
|------|------|
| 后端 | Python 3.11+, FastAPI, SQLAlchemy 2.x (async), Alembic |
| 数据库 | PostgreSQL 16 |
| 向量库 | Qdrant |
| 队列 | Redis + RQ |
| 文档解析 | Docling (fast/balanced/accurate) |
| Embedding | BGE-M3 via TEI (dense + sparse) |
| 前端 | React 19 + TypeScript + Vite + Ant Design 5 |
| 测试 | pytest, pytest-asyncio, httpx |

## 快速开始

### 1. 环境要求

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose

### 2. 启动基础设施

```bash
cd backend
docker compose up -d
```

这会启动 PostgreSQL、Redis、Qdrant 三个服务。

### 3. 启动 TEI Embedding 服务

```bash
text-embeddings-router --model-id ~/LocalLLMs/bge-m3 --port 8080
```

BGE-M3 同时输出 dense (1024维) + sparse 向量，供索引构建和检索调试使用。

### 4. 后端

```bash
# 创建虚拟环境
python3.11 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e "backend[dev]" aiofiles

# 配置环境变量
cp backend/.env.example backend/.env
# 按需修改 backend/.env

# 数据库迁移
cd backend
alembic upgrade head

# 启动 API 服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动 Worker (另一个终端)
python -m app.jobs.worker
```

### 5. 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000

### 6. 运行测试

```bash
# 单元测试 (不需要外部服务)
.venv/bin/python -m pytest backend/tests/ -v

# 含集成测试 (需要 Docling 模型)
.venv/bin/python -m pytest backend/tests/ -v -m "not integration"
```

## 项目结构

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── core/                      # 配置、日志、依赖注入
│   ├── api/routes/                # API 路由 (health, kb, documents, jobs, search_debug)
│   ├── api/schemas/               # Pydantic 请求/响应模型
│   ├── db/                        # ORM 模型、会话管理、Repository
│   ├── services/                  # 业务逻辑层
│   ├── rag/                       # RAG 管线组件
│   │   ├── parsing/               # 文档解析 (Docling + 兜底)
│   │   ├── chunking/              # Chunk 切分 (4 种策略 + Registry)
│   │   ├── embedding/             # Embedding (TEI BGE-M3)
│   │   ├── vector_store/          # 向量存储 (Qdrant)
│   │   └── classification/        # 文档类型分类
│   ├── jobs/                      # 异步任务 (RQ)
│   └── storage/                   # 文件存储抽象
├── migrations/                    # Alembic 迁移
├── tests/                         # 测试 (unit/contract/integration)
├── docker-compose.yml
└── pyproject.toml

frontend/
├── src/
│   ├── pages/
│   │   ├── KnowledgeBase/         # 知识库管理页
│   │   ├── Documents/             # 文档管理页
│   │   └── SearchDebug/           # 检索调试页
│   ├── api/client.ts              # API 客户端
│   ├── components/AppLayout.tsx   # 布局组件
│   └── types/index.ts             # TypeScript 类型定义
├── package.json
└── vite.config.ts
```

## API 接口

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
| `/documents/{doc_id}/enable` | POST | 启用文档 |
| `/documents/{doc_id}/disable` | POST | 禁用文档 |
| `/documents/{doc_id}/chunks` | GET | Chunk 预览 |
| `/jobs` | GET | 任务列表 |
| `/jobs/{job_id}` | GET | 任务详情 |
| `/jobs/{job_id}/retry` | POST | 重试任务 |

## 文档处理流程

```
上传 PDF → 入队 ingestion → 解析 (Docling/兜底) → Chunk 切分 → 入库
                                                                    ↓
                                                          入队 indexing → Embedding (BGE-M3) → Qdrant 写入 → ready
```

## 配置说明

所有配置项见 `backend/.env.example`，主要包括：

- 数据库连接 (PostgreSQL)
- Redis 连接
- Qdrant 连接
- TEI Embedding 服务地址
- 文件存储路径
- Worker 超时和重试配置
- 日志配置

## License

Private - AgenticRAG Team
