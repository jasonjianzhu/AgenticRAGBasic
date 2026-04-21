# AgenticRAG

储能产品文档问答平台。

当前仓库已经具备第一阶段的核心骨架：

- `FastAPI` 主服务
- `Postgres` 元数据与任务记录
- `Redis + RQ` 异步任务
- `Qdrant` 向量检索
- `TEI` embedding 服务
- 本地 reranker：`bge-reranker-v2-m3`
- `MiniMax` 答案生成与 query rewrite
- 文档管理页与 RAG 问答页

## 规划文档

- [IMPLEMENTATION_PLAN.md](/Users/zhujian/Code/AgenticRAG/IMPLEMENTATION_PLAN.md)
- [PHASE_TASKS.md](/Users/zhujian/Code/AgenticRAG/PHASE_TASKS.md)

## 本地环境

必须使用项目根目录下的 `.venv`，不要污染系统 Python。

创建虚拟环境：

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
```

安装依赖：

```bash
./.venv/bin/pip install -e ".[dev]"
```

复制环境变量：

```bash
cp .env.example .env
```

## 组件说明

### 1. Postgres

用途：

- 保存知识库、文档、版本、chunk、任务日志、查询日志等元数据

默认连接：

- `postgresql+psycopg://postgres:postgres@localhost:5432/agenticrag`

Docker 启动：

```bash
docker compose up -d postgres
```

验证：

```bash
docker ps
```

看到 `postgres` 容器处于 `Up` 状态即可。

### 2. Redis

用途：

- 给 `RQ` 提供任务队列连接

默认连接：

- `redis://localhost:6379/0`

Docker 启动：

```bash
docker compose up -d redis
```

验证：

```bash
docker ps
```

看到 `redis` 容器处于 `Up` 状态即可。

### 3. Qdrant

用途：

- 保存 dense / sparse 向量索引
- 支持混合检索

默认连接：

- `http://localhost:6333`

Docker 启动：

```bash
docker compose up -d qdrant
```

验证：

```bash
curl http://127.0.0.1:6333
```

能返回 Qdrant 服务信息即可。

### 4. FastAPI 主服务

用途：

- 提供文档上传、管理、RAG API、页面 UI

启动：

```bash
./.venv/bin/python main.py
```

验证：

- 健康检查：`http://127.0.0.1:8000/health`
- API 文档：`http://127.0.0.1:8000/docs`
- 文档管理页：`http://127.0.0.1:8000/`
- RAG 页面：`http://127.0.0.1:8000/ui/rag`

### 5. TEI Embedding 服务

用途：

- 提供真实 dense embedding
- 替代当前开发阶段的 mock embedding

推荐启动方式：

```bash
docker run --rm \
  -p 8080:80 \
  -v /Users/zhujian/.cache/huggingface:/data \
  ghcr.io/huggingface/text-embeddings-inference:cpu-arm64-latest \
  --model-id BAAI/bge-m3
```

说明：

- 当前项目默认走 `OpenAI-compatible /v1/embeddings` 接口
- 默认配置地址：`http://127.0.0.1:8080`
- `BAAI/bge-m3` 的默认向量维度应配置为 `1024`

验证：

```bash
curl -X POST http://127.0.0.1:8080/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "BAAI/bge-m3",
    "input": ["battery alarm", "pcs manual"]
  }'
```

### 6. RQ Worker

用途：

- 执行 ingestion 与 indexing 异步任务

启动：

```bash
./.venv/bin/python -m app.jobs.worker
```

验证：

- 启动后终端会进入 worker 监听状态
- 上传文档后，worker 终端应出现任务执行日志

### 7. MiniMax

用途：

- 提供 query rewrite
- 提供最终答案生成

相关配置：

```env
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
ANTHROPIC_AUTH_TOKEN=your-token
ANTHROPIC_MODEL=MiniMax-M2.7
```

说明：

- `/rag/answer` 与 RAG 页面提交问答时必须配置
- 未配置时，系统会明确报错，不再使用占位答案

### 8. 本地 reranker

用途：

- 对检索结果进行可选重排

当前使用：

- `BAAI/bge-reranker-v2-m3`

本地模型目录：

- `/Users/zhujian/LocalLLMs/bge-reranker-v2-m3`

相关配置：

```env
RERANKER_ENABLED=true
RERANKER_BACKEND=local
RERANKER_MODEL_NAME=/Users/zhujian/LocalLLMs/bge-reranker-v2-m3
```

说明：

- reranker 是 lazy load
- 第一次真正启用 rerank 时才会加载模型
- 当前环境探测不到 `mps` 时会自动回退 `cpu`

## 推荐启动顺序

1. 启动全部基础设施

```bash
docker compose up -d
```

2. 启动 TEI embedding 服务

```bash
docker run --rm \
  -p 8080:80 \
  -v /Users/zhujian/.cache/huggingface:/data \
  ghcr.io/huggingface/text-embeddings-inference:cpu-arm64-latest \
  --model-id BAAI/bge-m3
```

3. 执行数据库迁移

```bash
./.venv/bin/alembic upgrade head
```

4. 配置 MiniMax

确认 `.env` 中至少设置了：

```env
ANTHROPIC_BASE_URL=
ANTHROPIC_AUTH_TOKEN=
ANTHROPIC_MODEL=MiniMax-M2.7
```

5. 启动 FastAPI 主服务

```bash
./.venv/bin/python main.py
```

6. 新开一个终端启动 worker

```bash
./.venv/bin/python -m app.jobs.worker
```

## 首次测试建议

### 1. 测文档上传和索引

打开：

- `http://127.0.0.1:8000/`

上传一个 PDF 后：

- 文档应出现在管理页
- 可直接在管理页上传表单提交 PDF
- worker 终端应看到 ingestion / indexing 任务执行

### 2. 测 RAG 问答

打开：

- `http://127.0.0.1:8000/ui/rag`

输入问题后提交。

如果要测试重排：

- 勾选“启用 rerank”
- 第一次请求会慢一些，因为会首次加载本地模型

### 3. 测 API

检索接口：

```bash
curl -X POST http://127.0.0.1:8000/rag/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "E101 告警怎么处理",
    "top_k": 5,
    "use_reranker": true
  }'
```

回答接口：

```bash
curl -X POST http://127.0.0.1:8000/rag/answer \
  -H "Content-Type: application/json" \
  -d '{
    "query": "E101 告警怎么处理",
    "top_k": 5,
    "use_reranker": true
  }'
```

## 测试

运行全部测试：

```bash
./.venv/bin/pytest
```

运行局部测试：

```bash
./.venv/bin/pytest tests/test_rag_api.py tests/test_web_pages.py tests/test_reranker.py
```

## 当前目录结构

```text
AgenticRAG/
├── .env.example
├── docker-compose.yml
├── main.py
├── pyproject.toml
├── README.md
├── IMPLEMENTATION_PLAN.md
├── PHASE_TASKS.md
├── app/
│   ├── api/
│   ├── core/
│   ├── db/
│   ├── jobs/
│   ├── rag/
│   └── services/
├── migrations/
├── templates/
├── static/
├── tests/
├── var/
└── agentic_rag/
```

## 说明

- `agentic_rag/` 下仍保留早期 demo 代码，后续会逐步迁移或替换
- 本地 reranker 已接入，但首次加载本地大模型会比较慢
- 生产链路不再回退 `mock embedding` 或占位答案，缺少真实依赖时会直接报错

## 第一阶段对照

已完成：

- 上传、解析、chunk、索引、混合检索、引用答案主链路
- 文档列表、详情、chunk 预览、启用/禁用、重建索引、失败重试
- 评测数据、评测脚本、回归测试基础

仍待补齐：

- `/documents/upload` 直接上传入口仍主要通过管理页提供
- 第一阶段评测集还不够大，当前是最小可执行版本
