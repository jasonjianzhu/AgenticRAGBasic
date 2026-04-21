# 第一阶段任务书：知识库平台

## 概述

本任务书对应 PRD 第四章，目标是交付一个完整的知识库管理平台，包含文档上传、解析、chunk 构建、索引入库、检索调试和后台管理页面。

里程碑：
- **M1**：知识库 CRUD、文档上传、任务系统、解析、chunk 打通
- **M2**：索引构建打通、检索调试接口可用、管理页面可用

---

## 技术栈

| 层次 | 选型 |
|------|------|
| 后端 | Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic |
| 数据库 | PostgreSQL 16 |
| 向量库 | Qdrant |
| 队列 | Redis + RQ |
| 文档解析 | Docling |
| Embedding | BGE-M3 via TEI |
| 前端 | React + TypeScript + Vite（或按团队偏好） |
| 测试 | pytest, pytest-asyncio, httpx |

---

## 目录结构

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── core/
│   │   ├── config.py              # 配置管理
│   │   ├── logging.py             # 日志配置
│   │   └── dependencies.py        # 依赖注入
│   ├── api/
│   │   ├── routes/
│   │   │   ├── health.py
│   │   │   ├── kb.py              # 知识库接口
│   │   │   ├── documents.py       # 文档接口
│   │   │   ├── jobs.py            # 任务接口
│   │   │   └── search_debug.py    # 检索调试接口
│   │   └── schemas/
│   │       ├── kb.py
│   │       ├── documents.py
│   │       ├── jobs.py
│   │       └── search.py
│   ├── db/
│   │   ├── base.py                # SQLAlchemy Base
│   │   ├── models.py              # ORM 模型
│   │   ├── session.py             # 会话管理
│   │   └── repositories/
│   │       ├── kb.py
│   │       ├── documents.py
│   │       ├── chunks.py
│   │       └── jobs.py
│   ├── services/
│   │   ├── kb.py                  # 知识库业务逻辑
│   │   ├── ingestion.py           # 文档摄入（解析+chunk）
│   │   ├── indexing.py            # 索引构建（embed+写入）
│   │   └── search_debug.py        # 检索调试
│   ├── rag/
│   │   ├── parsing/
│   │   │   ├── base.py            # 解析器接口
│   │   │   ├── docling_parser.py  # Docling 实现
│   │   │   └── fallback.py        # 兜底解析
│   │   ├── chunking/
│   │   │   ├── base.py            # Chunker 接口
│   │   │   ├── registry.py        # Chunker 注册器
│   │   │   ├── docling_hybrid.py
│   │   │   ├── markdown_header.py
│   │   │   ├── recursive_token.py
│   │   │   └── table.py
│   │   ├── embedding/
│   │   │   ├── base.py            # Embedding 接口
│   │   │   └── tei.py             # TEI BGE-M3 实现
│   │   └── vector_store/
│   │       ├── base.py            # VectorStore 接口
│   │       └── qdrant.py          # Qdrant 实现
│   ├── jobs/
│   │   ├── queue.py               # RQ 队列封装
│   │   ├── worker.py              # Worker 入口
│   │   └── tasks.py               # 任务函数
│   └── storage/
│       ├── base.py                # 文件存储接口
│       └── local.py               # 本地文件系统实现
├── migrations/                    # Alembic 迁移
├── tests/
│   ├── unit/
│   ├── contract/
│   └── integration/
├── docker-compose.yml
├── pyproject.toml
└── .env.example

frontend/
├── src/
│   ├── pages/
│   │   ├── KnowledgeBase/         # 知识库管理页
│   │   ├── Documents/             # 文档管理页
│   │   └── SearchDebug/           # 检索调试页
│   ├── api/                       # API client
│   ├── components/                # 通用组件
│   └── App.tsx
├── package.json
└── vite.config.ts
```

---

## 任务清单

### Sprint 1：工程初始化与基础设施（M1 前置）

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| S1-01 | 初始化后端工程骨架 | FastAPI 应用 + 配置 + 日志 + health check | `GET /health` 返回 200 |
| S1-02 | 编写 docker-compose | Postgres + Redis + Qdrant 三服务 | `docker compose up` 三服务可连接 |
| S1-03 | 初始化数据库模型与 Alembic | ORM 模型 + 首版迁移 | `alembic upgrade head` 成功建表 |
| S1-04 | 初始化测试框架 | pytest 配置 + 测试目录 + smoke test | `pytest` 通过 |
| S1-05 | 初始化前端工程 | React + Vite + 路由 + 基础布局 | 前端可启动，三个页面占位可访问 |
| S1-06 | 封装文件存储抽象层 | `StorageBackend` 接口 + `LocalStorage` 实现 | 文件可写入/读取/删除 |

### Sprint 2：知识库管理（M1）

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| S2-01 | 实现知识库 CRUD API | POST/GET/PUT/DELETE /kb | 可创建、查询、更新、删除知识库 |
| S2-02 | 实现知识库配置管理 | 知识库 settings 字段（chunker、profile） | 配置可保存和读取 |
| S2-03 | 实现知识库统计接口 | GET /kb/{kb_id} 含统计信息 | 返回文档数、chunk 数、各状态文档数 |
| S2-04 | 知识库管理前端页面 | 列表 + 创建/编辑弹窗 + 统计卡片 | 页面可完成知识库 CRUD |

### Sprint 3：文档上传与管理（M1）

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| S3-01 | 实现文档上传接口 | POST /documents/upload | PDF 可上传，文件保存到本地，DB 记录生成 |
| S3-02 | 实现文件 SHA-256 去重 | 上传时计算 hash 并检查 | 重复文件返回已存在文档信息 |
| S3-03 | 实现 MIME 校验与大小限制 | 上传前校验 | 非 PDF 或超 50MB 返回 400 |
| S3-04 | 实现文档列表与详情接口 | GET /documents + GET /documents/{id} | 支持按 kb_id、status 筛选 |
| S3-05 | 实现文档启用/禁用接口 | POST enable/disable | 状态正确切换 |
| S3-06 | 实现文档删除接口 | DELETE /documents/{id} | 软删除标记，返回成功 |
| S3-07 | 实现 chunk 预览接口 | GET /documents/{id}/chunks | 返回 chunk 列表（分页） |
| S3-08 | 文档管理前端页面 | 上传 + 列表 + 状态 + 操作按钮 | 页面可完成上传和状态查看 |

### Sprint 4：异步任务系统（M1）

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| S4-01 | 封装 Redis 连接与 RQ 队列 | ingestion + indexing 两个队列 | 可向队列入队任务 |
| S4-02 | 实现 Worker 启动入口 | worker.py 可独立运行 | worker 启动后消费队列 |
| S4-03 | 实现 JobLog 模型与状态同步 | 任务状态写入 DB | API 可查询任务状态 |
| S4-04 | 实现失败重试逻辑 | retry 接口 + 自动重试 2 次 | 失败任务可手动/自动重试 |
| S4-05 | 实现任务超时控制 | 300s 超时 | 超时任务标记 failed |
| S4-06 | 实现任务列表与详情 API | GET /jobs + GET /jobs/{id} | 可查看任务列表和错误信息 |

### Sprint 5：文档解析（M1）

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| S5-01 | 定义解析器接口 | `DocumentParser` 抽象基类 | 接口定义清晰 |
| S5-02 | 实现 DoclingParser | 三种 profile（fast/balanced/accurate） | 给定 PDF 可输出结构化解析结果 |
| S5-03 | 实现兜底解析器 | 纯文本抽取 fallback | Docling 失败时可回退 |
| S5-04 | 实现解析产物持久化 | 解析 JSON 保存到 parsed 目录 | 文件可读取 |
| S5-05 | 接通上传→入队→解析链路 | 上传后自动入队 ingestion 任务 | 上传文档后 worker 自动完成解析 |
| S5-06 | 文档状态流转 | uploaded → parsing → chunked/failed | 状态正确更新 |

### Sprint 6：Chunk 构建（M1）

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| S6-01 | 定义 Chunker 接口与 Registry | `BaseChunker` + `ChunkerRegistry` | 可按名称获取 chunker |
| S6-02 | 实现 docling_hybrid chunker | 结构感知 + token 限制 | 输出 chunk 在 300-600 tokens |
| S6-03 | 实现 markdown_header chunker | 按标题层级切分 | 标题边界正确 |
| S6-04 | 实现 recursive_token chunker | 兜底切块 | 任意文本可切分 |
| S6-05 | 实现 table_chunker | 表格保留表头 | 表格 chunk 含完整表头 |
| S6-06 | 实现 chunk metadata 组装 | 每个 chunk 带完整 metadata | metadata 字段齐全 |
| S6-07 | 实现 chunk 持久化 | chunk 写入 DB | chunks 表有数据 |
| S6-08 | 实现文档类型识别 | 规则分类 + 人工指定 | 文档类型字段正确 |
| S6-09 | 接通解析→chunk 链路 | ingestion 任务完成解析后自动 chunk | 解析完成后 chunk 自动生成 |

### Sprint 7：Embedding 与索引构建（M2）

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| S7-01 | 定义 EmbeddingProvider 接口 | `EmbeddingProvider` 抽象基类 | 接口支持返回 dense + sparse |
| S7-02 | 实现 TEI BGE-M3 客户端 | 调用 TEI 获取 dense + sparse 向量 | 给定文本返回两种向量 |
| S7-03 | 定义 VectorStore 接口 | `VectorStore` 抽象基类 | 支持 upsert/delete/search |
| S7-04 | 实现 Qdrant VectorStore | 创建 collection + 写入 + 搜索 | 向量可写入和检索 |
| S7-05 | 实现批量 embedding + 写入 | 32 chunks/batch embed, 100 points/batch write | 大文档可完成索引 |
| S7-06 | 实现索引构建任务 | indexing 队列任务 | chunk → embed → Qdrant 链路打通 |
| S7-07 | 实现文档状态流转 | chunked → indexing → ready/failed | 状态正确更新 |
| S7-08 | 实现索引重建接口 | POST /kb/{kb_id}/build | 可触发整个知识库重建索引 |
| S7-09 | 实现文档删除清理 | 删除时清理 Qdrant points | 删除后向量库无残留 |

### Sprint 8：检索调试（M2）

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| S8-01 | 实现 hybrid search 逻辑 | dense search + sparse search + RRF 融合 | 给定 query 返回融合排序结果 |
| S8-02 | 实现 metadata filter | 按 kb/文档状态/类型/语言/型号过滤 | 过滤条件生效 |
| S8-03 | 实现检索调试 API | POST /kb/{kb_id}/search_debug | 返回 top-k chunks + score |
| S8-04 | 检索调试前端页面 | 输入框 + 结果列表（chunk 内容 + score + metadata） | 可在页面验证检索效果 |

### Sprint 9：集成联调与收尾（M2）

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| S9-01 | 端到端联调 | 上传→解析→chunk→索引→检索调试全链路 | 一个 PDF 走完全流程 |
| S9-02 | 前端页面联调 | 三个页面与后端 API 对接 | 页面操作全部可用 |
| S9-03 | 补充单元测试 | 核心逻辑覆盖 | 覆盖率 > 70% |
| S9-04 | 补充集成测试 | 关键链路测试 | 上传→就绪、检索调试 |
| S9-05 | 编写 README | 启动说明 + 环境要求 + 开发指南 | 新人可按文档启动 |
| S9-06 | 编写 .env.example | 所有配置项说明 | 配置项完整 |

---

## 数据库表设计

### knowledge_bases

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| name | VARCHAR(200) UNIQUE | 知识库名称 |
| description | TEXT | 描述 |
| is_active | BOOLEAN | 是否启用 |
| settings | JSONB | 配置（chunker、profile 等） |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

### documents

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| knowledge_base_id | UUID FK | 所属知识库 |
| title | VARCHAR(300) | 文档标题 |
| source_filename | VARCHAR(500) | 原始文件名 |
| storage_path | VARCHAR(1000) | 存储路径 |
| content_hash | VARCHAR(128) | SHA-256 hash |
| mime_type | VARCHAR(100) | MIME 类型 |
| file_size_bytes | BIGINT | 文件大小 |
| document_type | VARCHAR(50) | 文档类型（manual/faq/qa/spec/unknown） |
| status | VARCHAR(50) | 文档状态 |
| is_enabled | BOOLEAN | 是否启用 |
| is_deleted | BOOLEAN | 软删除标记 |
| metadata | JSONB | 扩展元数据 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

唯一约束：(knowledge_base_id, content_hash)

### document_versions

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| document_id | UUID FK | 所属文档 |
| version_number | INT | 版本号 |
| parser_profile | VARCHAR(50) | 解析 profile |
| parsed_path | VARCHAR(1000) | 解析产物路径 |
| status | VARCHAR(50) | 版本状态 |
| metadata | JSONB | 扩展元数据 |
| created_at | TIMESTAMPTZ | 创建时间 |

唯一约束：(document_id, version_number)

### chunks

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| knowledge_base_id | UUID FK | 所属知识库 |
| document_id | UUID FK | 所属文档 |
| document_version_id | UUID FK | 所属版本 |
| ordinal | INT | 序号 |
| chunk_type | VARCHAR(50) | 类型（text/table/image_caption） |
| section_path | TEXT | 章节路径 |
| content | TEXT | chunk 内容 |
| content_hash | VARCHAR(128) | 内容 hash |
| token_count | INT | token 数 |
| page_start | INT | 起始页 |
| page_end | INT | 结束页 |
| language | VARCHAR(20) | 语言 |
| product_model | VARCHAR(200) | 产品型号 |
| qdrant_point_id | VARCHAR(128) | Qdrant point ID |
| metadata | JSONB | 扩展元数据 |
| created_at | TIMESTAMPTZ | 创建时间 |

唯一约束：(document_version_id, ordinal)

### job_logs

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| rq_job_id | VARCHAR(200) | RQ 任务 ID |
| queue_name | VARCHAR(100) | 队列名 |
| job_type | VARCHAR(100) | 任务类型（ingest/index） |
| status | VARCHAR(50) | 任务状态 |
| document_id | UUID FK | 关联文档 |
| attempts | INT | 已尝试次数 |
| error_message | TEXT | 错误信息 |
| started_at | TIMESTAMPTZ | 开始时间 |
| finished_at | TIMESTAMPTZ | 完成时间 |
| payload | JSONB | 任务参数 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

---

## 接口契约摘要

### POST /kb

```json
// Request
{
  "name": "储能产品知识库",
  "description": "储能产品手册和FAQ",
  "settings": {
    "default_chunker": "docling_hybrid",
    "default_parser_profile": "balanced"
  }
}

// Response 201
{
  "id": "uuid",
  "name": "储能产品知识库",
  "description": "...",
  "settings": {...},
  "created_at": "2026-04-21T10:00:00Z"
}
```

### POST /documents/upload

```
Content-Type: multipart/form-data
Fields:
  - file: PDF 文件
  - knowledge_base_id: UUID
  - document_type: string (optional, 默认 "unknown")
  - parser_profile: string (optional, 使用知识库默认)
```

```json
// Response 201
{
  "id": "uuid",
  "title": "产品手册.pdf",
  "status": "uploaded",
  "content_hash": "sha256...",
  "job_id": "uuid"
}
```

### POST /kb/{kb_id}/search_debug

```json
// Request
{
  "query": "电池过温告警处理",
  "top_k": 10,
  "filters": {
    "document_type": "manual",
    "language": "zh"
  }
}

// Response 200
{
  "query": "电池过温告警处理",
  "results": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "document_title": "储能系统维护手册",
      "content": "当出现E003过温告警时...",
      "score": 0.87,
      "chunk_type": "text",
      "page_start": 42,
      "page_end": 42,
      "section_path": "第五章 > 告警处理 > 温度告警",
      "metadata": {...}
    }
  ],
  "trace": {
    "dense_hits": 15,
    "sparse_hits": 12,
    "fused_total": 20,
    "returned": 10
  }
}
```

---

## 开发顺序建议

```
Sprint 1 (工程初始化)
    ↓
Sprint 2 (知识库管理) + Sprint 4 (任务系统) 可并行
    ↓
Sprint 3 (文档上传) 依赖 Sprint 2
    ↓
Sprint 5 (解析) 依赖 Sprint 3 + Sprint 4
    ↓
Sprint 6 (Chunk) 依赖 Sprint 5
    ↓
Sprint 7 (索引) 依赖 Sprint 6
    ↓
Sprint 8 (检索调试) 依赖 Sprint 7
    ↓
Sprint 9 (联调收尾) 依赖全部
```

---

## 完成标准

- [ ] 知识库 CRUD 和配置管理可用
- [ ] 上传 PDF → 解析 → chunk → 索引全链路自动完成
- [ ] 管理页面可操作（知识库管理 + 文档管理）
- [ ] chunk 预览可用
- [ ] 检索调试接口可验证索引质量
- [ ] 文档启用/禁用/删除功能正常
- [ ] 异步任务失败可重试、可追踪
- [ ] 单元测试覆盖核心逻辑
- [ ] 集成测试覆盖关键链路
- [ ] README 和 .env.example 完整
