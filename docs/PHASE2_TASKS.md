# 第二阶段任务书：RAG 知识问答

## 概述

本任务书对应 PRD 第五章，目标是在第一阶段知识库平台基础上，增加完整的 RAG 问答能力，面向问答用户提供可引用的检索增强生成服务。

里程碑：
- **M3**：hybrid search + rerank + query rewrite 打通
- **M4**：流式 answer + RAG 问答页可用

### 前置条件

- 第一阶段全部功能已交付并可用
- 第一阶段 Backlog 中"留到第二阶段"的 Sparse Embedding 问题需在本阶段优先解决

### 第一阶段遗留项（本阶段需处理）

| 遗留项 | 说明 | 对应 Sprint |
|--------|------|-------------|
| Sparse Embedding 降级 | TEI 不支持 `/embed_sparse`，当前为纯 dense search | Sprint 1 |
| 错误信息透传到 JobLog | Worker 失败时 error_message 未写入 | Sprint 1 |
| 处理进度展示 | 大文档解析无进度反馈 | Sprint 1 |

---

## 技术栈（新增）

| 层次 | 选型 | 说明 |
|------|------|------|
| LLM | MiniMax M2.7 | Anthropic-compatible API，用于 query rewrite 和 answer generation |
| Reranker | TEI Reranker | 默认关闭，按需开启 |
| 可观测性 | Langfuse | LLM 调用 trace、检索链路观测 |
| 流式输出 | SSE (Server-Sent Events) | 流式答案传输 |
| Sparse Embedding | FlagEmbedding / 自建服务 | 替代 TEI 不可用的 sparse 端点 |

---

## 目录结构（新增/修改）

```
backend/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── rag.py                 # [新增] RAG 问答接口（search / answer / config）
│   │   │   └── ...
│   │   └── schemas/
│   │       ├── rag.py                 # [新增] RAG 请求/响应 schema
│   │       └── ...
│   ├── rag/
│   │   ├── embedding/
│   │   │   ├── bge_m3_local.py        # [新增] 本地 BGE-M3 embedding（dense + sparse）
│   │   │   └── ...
│   │   ├── reranking/                 # [新增] 重排模块
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # Reranker 接口
│   │   │   └── tei_reranker.py        # TEI Reranker 实现
│   │   ├── query/                     # [新增] Query 处理模块
│   │   │   ├── __init__.py
│   │   │   ├── normalizer.py          # Query 标准化
│   │   │   ├── rewriter.py            # Query 改写（MiniMax）
│   │   │   └── context_extractor.py   # Retrieval context 提取
│   │   └── generation/                # [新增] 答案生成模块
│   │       ├── __init__.py
│   │       ├── base.py                # LLM 接口
│   │       ├── minimax.py             # MiniMax 客户端
│   │       ├── prompts.py             # System prompt 模板
│   │       └── citation.py            # 引用拼接
│   ├── services/
│   │   ├── rag.py                     # [新增] RAG 业务逻辑（检索 + 生成编排）
│   │   ├── rag_config.py              # [新增] RAG 配置管理
│   │   └── ...
│   └── core/
│       ├── config.py                  # [修改] 新增 LLM / Reranker / Langfuse 配置项
│       └── ...
├── tests/
│   ├── unit/
│   │   ├── test_query_normalizer.py   # [新增]
│   │   ├── test_query_rewriter.py     # [新增]
│   │   ├── test_rrf_fusion.py         # [新增]
│   │   ├── test_reranker.py           # [新增]
│   │   ├── test_citation.py           # [新增]
│   │   └── ...
│   ├── contract/
│   │   ├── test_minimax_client.py     # [新增]
│   │   ├── test_tei_reranker.py       # [新增]
│   │   └── ...
│   └── integration/
│       ├── test_rag_search.py         # [新增]
│       ├── test_rag_answer.py         # [新增]
│       └── ...

frontend/
├── src/
│   ├── pages/
│   │   ├── RAGChat/                   # [新增] RAG 问答页
│   │   │   ├── index.tsx
│   │   │   ├── ChatInput.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── CitationPanel.tsx
│   │   │   └── TracePanel.tsx
│   │   └── ...
│   ├── api/
│   │   ├── rag.ts                     # [新增] RAG API client
│   │   └── ...
│   └── hooks/
│       ├── useSSE.ts                  # [新增] SSE 流式接收 hook
│       └── ...
```

---

## 任务清单

### Sprint 1：Sparse Embedding 补全与遗留修复（M3 前置）

解决第一阶段遗留的 sparse embedding 降级问题，为 hybrid search 打好基础。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P2-S1-01 | Sparse embedding 方案选型与实现 | `BGE-M3 LocalEmbeddingProvider` 或自建 HTTP 服务 | 给定文本可同时返回 dense + sparse 向量 |
| P2-S1-02 | 替换 TEI sparse 降级逻辑 | 修改 `EmbeddingProvider` 实现 | sparse 向量不再为空，索引构建写入真实 sparse vector |
| P2-S1-03 | 已有索引 sparse 向量回填 | 提供脚本或接口，对已入库文档重建 sparse 索引 | 已有 chunk 的 Qdrant point 包含有效 sparse vector |
| P2-S1-04 | 验证 hybrid search 效果 | 检索调试接口返回 dense + sparse 融合结果 | sparse_hits > 0，融合结果优于纯 dense |
| P2-S1-05 | 修复 JobLog 错误信息透传 | Worker 异常写入 `error_message` | 失败任务可在前端查看具体错误原因 |
| P2-S1-06 | 实现处理进度展示 | JobLog 增加 `progress` 字段 + Worker 阶段更新 | 前端可展示解析/索引进度百分比 |

### Sprint 2：LLM 接入与 Query 处理（M3）

接入 MiniMax LLM，实现 query 标准化和改写能力。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P2-S2-01 | 定义 LLM 客户端接口 | `BaseLLMClient` 抽象基类 | 支持同步/流式调用、统一错误处理 |
| P2-S2-02 | 实现 MiniMax 客户端 | `MiniMaxClient`（Anthropic-compatible API） | 可调用 MiniMax 完成文本生成 |
| P2-S2-03 | 新增 LLM / Reranker 配置项 | `config.py` 扩展 | 配置项可通过 `.env` 管理 |
| P2-S2-04 | 实现 query 标准化 | `QueryNormalizer`（全角转半角、空格清理） | 标准化后 query 格式统一 |
| P2-S2-05 | 实现 query rewrite | `QueryRewriter`（MiniMax 改写 + 扩展） | 给定 query 返回结构化改写结果（改写 query + 扩展关键词） |
| P2-S2-06 | 实现 retrieval context 提取 | `ContextExtractor`（从 query 识别产品型号、语言、故障码、文档类型） | 给定 query 返回结构化 context 字段 |
| P2-S2-07 | 实现 retrieval context 历史继承 | 最近 N 轮检索上下文合并逻辑 | 多轮检索时 context 可累积 |

### Sprint 3：Reranker 与检索增强（M3）

实现可选的 rerank 能力，完善检索链路。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P2-S3-01 | 定义 Reranker 接口 | `BaseReranker` 抽象基类 | 支持 rerank(query, documents) → scored list |
| P2-S3-02 | 实现 TEI Reranker 客户端 | `TEIReranker`（调用 TEI rerank 端点） | 给定 query + candidates 返回重排结果 |
| P2-S3-03 | 实现 rerank 懒加载 | 仅在配置开启时初始化 reranker | 默认关闭时不加载模型、不报错 |
| P2-S3-04 | 集成 rerank 到检索链路 | hybrid search → top-20 候选 → rerank → top-5 | rerank 开启时结果经过重排 |
| P2-S3-05 | 实现多知识库联合检索 | 支持指定多个 kb_id 联合检索 + 统一 RRF 融合 | 跨知识库检索结果正确融合排序 |
| P2-S3-06 | 实现 metadata filter 增强 | 支持按文档状态、文档类型、语言、产品型号组合过滤 | 过滤条件与 retrieval context 联动 |
| P2-S3-07 | 实现 RAG 检索 API | `POST /rag/search` | 返回命中 chunk + trace 摘要（含 query rewrite 信息） |

### Sprint 4：答案生成与流式输出（M4）

实现带引用的流式答案生成。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P2-S4-01 | 实现 context packing | 将命中 chunk 组装为 LLM 输入上下文 | 上下文格式清晰，含来源标记 |
| P2-S4-02 | 编写 system prompt 模板 | grounded answer prompt（约束基于检索内容回答） | prompt 可配置、支持中英文 |
| P2-S4-03 | 实现流式答案生成 | MiniMax 流式调用 + SSE 封装 | 答案 token 逐步输出 |
| P2-S4-04 | 实现引用拼接 | 答案中标注引用（文档名 + 页码 + chunk 摘要） | 引用信息准确、格式统一 |
| P2-S4-05 | 实现拒答策略 | 检索结果为空或 score 过低时返回"未找到相关信息" | 无相关内容时不编造答案 |
| P2-S4-06 | 实现 SSE 事件协议 | token / citation / trace / done / error 五种事件 | 客户端可正确解析各事件类型 |
| P2-S4-07 | 实现客户端断开检测 | 客户端断开连接时取消生成 | 断开后服务端停止 LLM 调用 |
| P2-S4-08 | 实现 RAG 问答 API | `POST /rag/answer`（SSE 流式） | 端到端可用：query → rewrite → search → rerank → generate |

### Sprint 5：RAG 配置与 Langfuse 观测（M4）

实现 RAG 运行时配置管理和 LLM 调用链路观测。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P2-S5-01 | 实现 RAG 配置管理 | `GET/PUT /rag/config` | 可动态调整 top-k、rerank 开关、context 窗口等 |
| P2-S5-02 | 定义 RAG 配置项 | 配置 schema（top_k、rerank_enabled、rerank_top_n、context_window、score_threshold、refusal_threshold） | 配置项完整、有合理默认值 |
| P2-S5-03 | 配置持久化 | RAG 配置存入 DB 或配置文件 | 重启后配置不丢失 |
| P2-S5-04 | 接入 Langfuse SDK | LLM 调用自动上报 trace | Langfuse 控制台可查看调用记录 |
| P2-S5-05 | 检索链路 trace 上报 | query rewrite、search、rerank、generation 各步骤 trace | Langfuse 可查看完整 RAG 链路耗时和中间结果 |
| P2-S5-06 | docker-compose 新增服务 | 添加 Langfuse（或配置外部 Langfuse 地址） | Langfuse 服务可用 |

### Sprint 6：RAG 问答前端页面（M4）

实现面向问答用户的 RAG 问答页面。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P2-S6-01 | 实现 SSE 接收 hook | `useSSE` React hook | 可接收和解析 SSE 事件流 |
| P2-S6-02 | 实现问答输入组件 | 输入框 + 知识库选择 + 发送按钮 | 可输入问题并选择目标知识库 |
| P2-S6-03 | 实现流式消息展示 | 消息列表 + 逐字输出效果 | 答案流式展示，体验流畅 |
| P2-S6-04 | 实现引用来源展示 | 引用面板（文档名、页码、chunk 内容摘要） | 点击引用可查看详情 |
| P2-S6-05 | 实现 trace 展示 | 折叠面板展示 query rewrite、检索模式、命中数 | 可选展开查看检索过程 |
| P2-S6-06 | 实现 query rewrite 展示 | 可选显示改写后的 query | 用户可了解系统如何理解问题 |
| P2-S6-07 | 前端路由与导航 | RAG 问答页接入主导航 | 页面可正常访问和切换 |

### Sprint 7：评测体系与集成联调（M4）

建立基线评测能力，完成端到端联调。

| ID | 任务 | 产出 | 验收标准 |
|----|------|------|----------|
| P2-S7-01 | 设计评测数据集格式 | 评测集 schema（query + expected_chunks + expected_answer） | 格式定义清晰，支持多类型问答 |
| P2-S7-02 | 准备基线评测集 | 覆盖产品参数、告警码、安装维护、中英跨语言 | 至少 50 条评测样本 |
| P2-S7-03 | 实现 Hit@K / MRR 评测脚本 | 检索效果评测 | 可自动计算 Hit@5、Hit@10、MRR |
| P2-S7-04 | 实现引用命中率评测 | 答案引用是否命中预期 chunk | 可自动计算引用准确率 |
| P2-S7-05 | 端到端联调 | query → rewrite → search → rerank → answer 全链路 | 一个问题走完全流程，答案带引用 |
| P2-S7-06 | 前端页面联调 | RAG 问答页与后端 API 对接 | 页面操作全部可用 |
| P2-S7-07 | 补充单元测试 | query 处理、RRF 融合、引用拼接、拒答逻辑 | 核心逻辑覆盖 |
| P2-S7-08 | 补充契约测试 | MiniMax 客户端、TEI Reranker 客户端 | 外部服务适配器有契约测试 |
| P2-S7-09 | 更新 README 和 .env.example | 新增配置项说明、RAG 使用说明 | 文档完整 |

---

## 新增 API 接口契约

### POST /rag/search

```json
// Request
{
  "query": "电池过温告警如何处理",
  "kb_ids": ["uuid-1", "uuid-2"],
  "top_k": 10,
  "filters": {
    "document_type": "manual",
    "language": "zh",
    "product_model": "ESS-5000"
  },
  "enable_rewrite": true
}

// Response 200
{
  "query": "电池过温告警如何处理",
  "rewritten_query": "电池过温告警 E003 处理方法 解决方案",
  "results": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "document_title": "储能系统维护手册",
      "content": "当出现E003过温告警时...",
      "score": 0.87,
      "rerank_score": 0.92,
      "chunk_type": "text",
      "page_start": 42,
      "page_end": 42,
      "section_path": "第五章 > 告警处理 > 温度告警",
      "metadata": {}
    }
  ],
  "trace": {
    "query_normalized": "电池过温告警如何处理",
    "query_rewritten": "电池过温告警 E003 处理方法 解决方案",
    "retrieval_context": {
      "product_model": "ESS-5000",
      "language": "zh",
      "fault_code": "E003"
    },
    "dense_hits": 15,
    "sparse_hits": 12,
    "fused_total": 20,
    "reranked": true,
    "returned": 10,
    "latency_ms": {
      "rewrite": 320,
      "search": 45,
      "rerank": 180,
      "total": 550
    }
  }
}
```

### POST /rag/answer

```
Content-Type: text/event-stream

// SSE 事件流
event: trace
data: {"query_rewritten": "...", "search_mode": "hybrid", "hits": 15}

event: citation
data: {"index": 1, "document_title": "储能系统维护手册", "page": 42, "chunk_id": "uuid", "snippet": "当出现E003过温告警时..."}

event: token
data: {"content": "当"}

event: token
data: {"content": "出现"}

event: token
data: {"content": "E003"}

event: token
data: {"content": "过温告警时，"}

event: citation
data: {"index": 2, "document_title": "告警处理指南", "page": 15, "chunk_id": "uuid", "snippet": "处理步骤：1. 检查..."}

event: token
data: {"content": "建议按以下步骤处理[1][2]：..."}

event: done
data: {"total_tokens": 256, "latency_ms": 1200}
```

```json
// Request
{
  "query": "电池过温告警如何处理",
  "kb_ids": ["uuid-1"],
  "top_k": 5,
  "filters": {},
  "enable_rewrite": true,
  "enable_rerank": false
}
```

### GET /rag/config

```json
// Response 200
{
  "search_top_k": 10,
  "answer_top_k": 5,
  "rerank_enabled": false,
  "rerank_top_n": 20,
  "rewrite_enabled": true,
  "context_window_tokens": 4000,
  "score_threshold": 0.3,
  "refusal_threshold": 0.2,
  "rrf_k": 60,
  "llm_model": "minimax-m2.7",
  "llm_temperature": 0.1,
  "llm_max_tokens": 2048
}
```

### PUT /rag/config

```json
// Request（部分更新）
{
  "rerank_enabled": true,
  "answer_top_k": 3
}

// Response 200
{
  // 返回完整配置（同 GET）
}
```

---

## 新增配置项

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| LLM Base URL | `LLM_BASE_URL` | - | MiniMax API 地址 |
| LLM API Key | `LLM_API_KEY` | - | MiniMax API Key |
| LLM Model | `LLM_MODEL` | `minimax-m2.7` | 模型名称 |
| LLM Temperature | `LLM_TEMPERATURE` | `0.1` | 生成温度 |
| LLM Max Tokens | `LLM_MAX_TOKENS` | `2048` | 最大生成 token 数 |
| LLM Timeout | `LLM_TIMEOUT` | `60` | LLM 调用超时（秒） |
| Reranker Base URL | `RERANKER_BASE_URL` | - | TEI Reranker 地址 |
| Reranker API Key | `RERANKER_API_KEY` | - | Reranker API Key |
| Reranker Enabled | `RERANKER_ENABLED` | `false` | 是否启用 rerank |
| Reranker Top N | `RERANKER_TOP_N` | `20` | rerank 候选数 |
| Langfuse Host | `LANGFUSE_HOST` | - | Langfuse 服务地址 |
| Langfuse Public Key | `LANGFUSE_PUBLIC_KEY` | - | Langfuse 公钥 |
| Langfuse Secret Key | `LANGFUSE_SECRET_KEY` | - | Langfuse 密钥 |
| Score Threshold | `SCORE_THRESHOLD` | `0.3` | 检索结果最低分数阈值 |
| Refusal Threshold | `REFUSAL_THRESHOLD` | `0.2` | 拒答分数阈值 |
| Context Window Tokens | `CONTEXT_WINDOW_TOKENS` | `4000` | 上下文窗口 token 数 |

---

## 数据库变更

### 新增表：rag_configs

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| key | VARCHAR(100) UNIQUE | 配置键 |
| value | JSONB | 配置值 |
| updated_at | TIMESTAMPTZ | 更新时间 |

### 修改表：job_logs

| 字段 | 类型 | 说明 |
|------|------|------|
| progress | INT | [新增] 处理进度（0-100） |

---

## 开发顺序

```
Sprint 1 (Sparse 补全 + 遗留修复)
    ↓
Sprint 2 (LLM 接入 + Query 处理) + Sprint 3 (Reranker + 检索增强) 可并行
    ↓
Sprint 4 (答案生成 + 流式输出) 依赖 Sprint 2 + Sprint 3
    ↓
Sprint 5 (RAG 配置 + Langfuse) 可与 Sprint 4 并行
    ↓
Sprint 6 (前端页面) 依赖 Sprint 4
    ↓
Sprint 7 (评测 + 联调) 依赖全部
```

---

## 完成标准

- [ ] 混合检索可用（dense + sparse + RRF），sparse 向量为真实值
- [ ] query rewrite 生效，改写结果可查看
- [ ] rerank 可配置开启，默认关闭，开启后检索结果经过重排
- [ ] 返回流式答案带引用（SSE 协议）
- [ ] 拒答策略生效（无相关内容时不编造）
- [ ] 多知识库联合检索可用
- [ ] RAG 配置可动态调整
- [ ] 问答页面端到端可用（输入问题 → 流式答案 → 引用展示）
- [ ] 基线评测可重复执行（Hit@K、MRR、引用命中率）
- [ ] Langfuse trace 可查看 LLM 调用链路
- [ ] 第一阶段遗留的 JobLog 错误透传和进度展示已修复
- [ ] 单元测试覆盖核心逻辑，契约测试覆盖外部服务适配器
- [ ] README 和 .env.example 更新完整
