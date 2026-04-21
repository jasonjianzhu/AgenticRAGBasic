# AgenticRAG 三阶段最终方案

## 1. 目标与最终选型

本项目分三阶段推进：

1. 第一阶段：文档解析、知识库构建、RAG 问答
2. 第二阶段：在现有 RAG 服务之上增加 Agent 能力
3. 第三阶段：完善鉴权、任务调度、观测、评测、版本化与发布能力，形成产品级系统

最终选型结论：

- RAG 核心链路：手搓，不以 `LlamaIndex` 或 `Agno` 作为主骨架
- Agent 框架：第二阶段使用 `PydanticAI`
- PDF 解析：`Docling` 为主，必要时用轻量文本抽取做兜底
- 业务库：`Postgres` 
- 检索库：`Qdrant`
- LLM：`MiniMax-M2.7`，通过 Anthropic-compatible API 接入
- 前端：一个前端工程，三个页面
- 后端：`FastAPI`
- 第一阶段异步任务：先用数据库任务表 + 独立 worker
- 后续高并发任务队列：按需要升级为 `Redis + RQ`

## 2. 总体设计原则

- RAG 是核心产品能力，必须可控、可测、可追踪，因此主链路手搓
- Agent 是上层编排能力，不直接接管底层检索与知识库构建
- 第一阶段就实现混合检索、Query 改写、可选重排，不采用“后面再补”的方式
- 先保证服务边界清晰，再逐步增强能力
- 所有关键功能以 TDD 方式推进，先写失败测试，再补实现

## 3. 总体系统边界

```text
+----------------------+       +----------------------+
| Frontend             |       | Admin Frontend       |
| - RAG 问答页面        |       | - 文档上传            |
| - Agent 对话页面      |       | - 解析/Chunk/索引管理 |
+----------+-----------+       +----------+-----------+
           |                               |
           +---------------+---------------+
                           |
                    +------+------+
                    | FastAPI API |
                    +------+------+
                           |
     +---------------------+---------------------+
     |                     |                     |
     v                     v                     v
+----+-----+        +------+-------+      +------+------+
| RAG Service |      | Agent Service |      | Admin Jobs |
+----+-----+        +------+-------+      +------+------+
     |                     |                     |
     v                     v                     v
+----+---------------------+-------------+  +----+------+
| Postgres                                  |  | Worker   |
| - 文档/任务/会话/配置/审计/版本            |  | parse    |
+-------------------+----------------------+  | chunk    |
                    |                         | embed    |
                    v                         | index    |
               +----+-----+                   +----+-----+
               | Qdrant    |                        |
               | dense+sparse                       |
               +----------+                         |
                    |                               |
                    v                               v
               +----+-------------------------------+---+
               | Model Layer                            |
               | - Docling                              |
               | - Embedding                            |
               | - Reranker(optional)                  |
               | - MiniMax                             |
               +---------------------------------------+
```

## 4. 三阶段方案

## 4.1 第一阶段：文档解析、知识库构建、问答

### 4.1.1 目标

第一阶段的目标不是 demo，而是一个能工作的知识库问答系统，包含：

- PDF 上传
- 文档解析
- chunk 预览与构建
- embedding 与索引入库
- 混合检索
- Query 改写与扩充
- 可选 rerank
- 带引用的 RAG 问答
- 后台管理页面

### 4.1.2 第一阶段架构

```text
[RAG 问答页] ----\
                  \
                   > FastAPI
                  /
[知识库管理页] ---/
        |
        +--> Postgres
        |    - documents
        |    - chunks
        |    - jobs
        |    - kb_configs
        |    - query_logs
        |
        +--> Worker
        |    - parse
        |    - classify
        |    - chunk
        |    - embed
        |    - index
        |
        +--> Qdrant
             - dense vectors
             - sparse vectors
             - payload metadata
```

### 4.1.3 第一阶段核心组件

#### 1. 前端

- `RAG 问答页面`
  - 输入问题
  - 展示流式答案
  - 展示引用页码、来源文档、命中 chunk
  - 可选显示 query rewrite、检索模式、rerank 状态
- `文档管理和知识库构建页面`
  - 上传 PDF
  - 选择知识库
  - 查看解析状态
  - 预览 chunk
  - 触发索引构建
  - 查看失败原因和重试

#### 2. API 层

使用 `FastAPI`，负责：

- 上传与文档管理
- 构建任务触发
- 问答接口
- 检索接口
- 任务状态查询
- 后台配置管理

建议第一阶段就定义清晰接口：

- `POST /documents/upload`
- `POST /jobs/{job_id}/retry`
- `GET /jobs/{job_id}`
- `POST /kb/{kb_id}/build`
- `POST /rag/search`
- `POST /rag/answer`

#### 3. 文档解析层

主解析器：`Docling`

原因：

- 适合 PDF、表格、图片、阅读顺序较复杂的手册
- 支持结构化输出，便于后续 chunk

为解决 Docling 速度问题，第一阶段就实现解析 profile：

- `fast`
  - 文本型 PDF 优先
  - 尽量关闭重型 OCR 和高精度表格推理
- `balanced`
  - 默认模式
  - 保留结构和表格能力
- `accurate`
  - 扫描件、复杂表格、复杂手册

解析优化策略：

- 文档内容 hash 去重，避免重复解析
- 分层缓存解析结果
- 超时控制
- 按页或按文件维度记录解析状态
- 对纯文本 PDF 可增加轻量文本抽取兜底

#### 4. Chunk 构建层

第一阶段不采用单一固定长度切块，而是 `Chunker Registry`。

默认支持：

- `docling_hybrid`
  - 结构感知 + token 限制
- `markdown_header`
  - 按标题层级切分
- `recursive_token`
  - 作为兜底切块器
- `table_chunker`
  - 表格专用，重复表头，避免上下文丢失

chunk 设计要求：

- 正文：约 `300-600 tokens`
- overlap：约 `50-80 tokens`
- 表格单独 chunk
- 图片保留 `caption + 邻近正文 + 页码 + 资源路径`
- 每个 chunk 都带 metadata

chunk metadata 至少包括：

- `kb_id`
- `doc_id`
- `doc_version`
- `source_path`
- `page_start`
- `page_end`
- `section_path`
- `chunk_type`
- `language`
- `product_model`

关于 QA 文档识别：

- 上传时允许用户指定文档类型：`manual`、`faq`、`qa`、`spec`、`unknown`
- 未指定时做自动分类
- 自动分类基于弱规则与结构特征
- 后台支持人工纠正

#### 5. 知识库存储

`Postgres` 存业务数据：

- 知识库
- 文档
- 文档版本
- chunk 原文与 metadata
- 构建任务
- 用户与权限
- 问答日志
- trace 摘要
- 配置项

`Qdrant` 存检索索引：

- dense vectors
- sparse vectors
- hybrid search payload
- metadata filters

#### 6. 检索与问答层

第一阶段即启用混合检索。

检索链路：

1. 原始 query 进入 `Query Processor`
2. MiniMax 负责 Query 改写和扩充
3. 构造 dense query vector
4. 构造 sparse query 表达
5. 在 Qdrant 中执行 hybrid search
6. 使用 RRF 做融合
7. 按 metadata 做过滤
8. 可选执行 rerank
9. 组装上下文
10. MiniMax 生成带引用答案

第一阶段必须具备的检索能力：

- dense retrieval
- sparse retrieval
- hybrid retrieval
- metadata filter
- query rewrite
- context packing
- grounded answer generation

可选组件：

- reranker
  - 默认可关闭
  - 开启时懒加载

#### 7. Query 改写与检索级上下文管理

第一阶段由 `RAG Service` 内部负责：

- Query 标准化
- Query 改写与扩充
- 最近数轮的检索级上下文继承
- 产品型号、语言、故障码、文档类型等过滤条件提取

边界规则：

- 只为“把资料找准”服务的上下文，放在 RAG
- 不负责任务级规划，不承担 Agent 的职责

#### 8. 异步任务设计

第一阶段先不强依赖 `Redis + RQ`。

最小方案：

- `Postgres job table`
- `独立 worker 进程`
- worker 轮询数据库任务并执行

原因：

- 组件少
- 便于快速启动
- 足够支持第一阶段的解析、chunk、embedding、索引构建

后续当并发和任务复杂度提升时，再升级为 `Redis + RQ`。

### 4.1.4 第一阶段实现清单

- FastAPI 服务
- RAG 问答页面
- 后台文档管理页面
- Docling 解析流程
- chunk registry
- Postgres 文档与任务表
- Qdrant hybrid search
- MiniMax query rewrite + answer generation
- 可选 reranker
- 结构化日志和 trace 基础字段

### 4.1.5 第一阶段完成标准

- 能上传储能产品 PDF
- 能查看解析和构建状态
- 能完成 chunk 与索引构建
- 能进行混合检索问答
- 回答能带来源和页码
- 出错时可重试并可追踪

## 4.2 第二阶段：增加 Agent

### 4.2.1 目标

第二阶段不是重写 RAG，而是在第一阶段已有 RAG 服务上叠加 Agent。

Agent 的职责：

- 多轮对话
- 工具选择
- 多步任务拆解
- 多次调用 RAG
- 汇总多个工具结果

### 4.2.2 第二阶段架构

```text
[Agent 对话页面] --> FastAPI --> Agent Service(PydanticAI)
                                  |
                                  +--> rag_search_tool
                                  +--> rag_answer_tool
                                  +--> document_lookup_tool
                                  +--> future_sql_tool
                                  +--> future_api_tool

[RAG 问答页面] -----> FastAPI --> RAG Service
```

### 4.2.3 Agent 选型

第二阶段使用 `PydanticAI`，不使用 `Agno` 作为主框架。

原因：

- 更轻
- 结构化输出和类型约束更自然
- 便于测试
- 适合作为“上层编排层”
- 不会侵入底层知识库与检索系统

不选择 `Agno` 作为主骨架的原因：

- 它更适合快速搭 Agent 系统
- 但本项目核心是可控的 RAG 平台，而非让框架接管 knowledge/memory 主链路

### 4.2.4 第二阶段组件

#### 1. Agent 对话页面

- 多轮聊天
- 展示工具调用过程
- 展示引用资料
- 支持查看中间 trace

#### 2. Agent Service

基于 `PydanticAI` 实现，负责：

- 对话状态
- 工具调用
- 结构化回复
- 任务级上下文管理

#### 3. Agent 可调用工具

第一批工具：

- `rag_search_tool`
- `rag_answer_tool`
- `document_lookup_tool`

后续扩展：

- `sql_tool`
- `api_tool`
- `rule_tool`

### 4.2.5 上下文边界

RAG 管理：

- Query rewrite
- retrieval context
- 检索过滤条件
- 上下文拼装

Agent 管理：

- 多轮任务目标
- 工具调用历史
- 当前任务阶段
- 任务级决策上下文

### 4.2.6 第二阶段完成标准

- Agent 页面可工作
- Agent 能调用 RAG 服务
- 支持多轮对话
- 支持引用资料和工具轨迹展示
- Agent 与 RAG 的职责边界清晰

## 4.3 第三阶段：最终产品化

### 4.3.1 目标

第三阶段重点是把系统补齐为稳定、可运维、可发布的产品。

### 4.3.2 第三阶段架构增强

```text
Frontend
  |- RAG 问答
  |- Agent 对话
  |- Admin/KB

FastAPI API Layer
  |- Auth
  |- RAG APIs
  |- Agent APIs
  |- Admin APIs

Async Layer
  |- Postgres job table or Redis + RQ
  |- workers

Storage
  |- Postgres
  |- Qdrant
  |- Object Storage(local/S3 compatible)

Observability
  |- Structured logs
  |- OpenTelemetry
  |- Langfuse or Phoenix
  |- Evaluation pipeline
```

### 4.3.3 产品化补齐项

#### 1. 鉴权与权限

- JWT 登录
- RBAC：`admin`、`operator`、`user`
- 后期可接入企业 SSO / OIDC

#### 2. 异步任务与队列升级

当出现以下情况时升级到 `Redis + RQ`：

- 多 worker 并发构建需求明显
- 任务数量增长
- 需要更成熟的失败重试和队列隔离
- 需要更好的任务吞吐

#### 3. 对象存储

- 开发阶段可用本地文件系统
- 产品化切换到 S3-compatible storage
- 文件与解析产物分层保存

#### 4. 可观测性

- 结构化日志
- 每次问答记录 request_id、latency、kb_id、模型信息
- 记录 query rewrite 和 retrieval trace
- 记录 rerank 分数和引用来源
- 接入 OpenTelemetry
- 对接 Langfuse 或 Phoenix

#### 5. 评测体系

必须建立：

- 检索评测集
- 问答评测集
- 典型工单/产品问答集

指标建议：

- `Hit@K`
- `MRR`
- 引用命中率
- groundedness
- 回答完整性

#### 6. 版本化与回滚

- 文档版本
- 索引版本
- 知识库发布版本
- 支持回滚到上一版

#### 7. 安全与审计

- 上传文件大小限制
- MIME 校验
- 文档去重
- 配置项脱敏
- 管理操作审计

### 4.3.4 第三阶段完成标准

- 多用户可用
- 权限清晰
- 后台稳定运行
- 任务可观测、可审计
- 有评测与发布流程
- 支持版本管理与回滚

## 5. 为什么这样分层

### 5.1 Agent 用框架，RAG 不用框架

最终判断：

- Agent：用 `PydanticAI`
- RAG：手搓

原因：

- Agent 的通用编排、tool calling、结构化输出、测试替身等，框架有明显收益
- RAG 是本项目的核心产品能力，必须完全掌控解析、chunk、检索、重排、索引、追踪链路

### 5.2 为什么不是 LlamaIndex 或 Agno 主导

不采用 `LlamaIndex` 作为 RAG 主骨架：

- 会加快前期搭建
- 但会限制对核心链路的控制力
- 本项目还有后台管理、索引版本、任务流、文档治理需求

不采用 `Agno` 作为 Agent 主骨架：

- 它适合快速搭 Agent
- 但本项目更需要轻量、可测、与自有服务边界清晰的 Agent 层

## 6. TDD 实施方案

## 6.1 核心原则

- 先写失败测试，再写实现
- 先写验收标准，再写技术实现
- 单元测试不依赖真实外部服务
- 每次修 bug 先补失败测试
- 每次检索优化都要跑评测

## 6.2 测试分层

### 1. 单元测试

测试纯逻辑：

- 文档类型识别
- chunk 切分
- metadata 提取
- retrieval context 合并
- query rewrite 结果校验
- RRF 融合逻辑
- rerank 选择逻辑

要求：

- 不访问真实数据库
- 不访问真实 Qdrant
- 不调用真实 MiniMax

### 2. 契约测试

测试适配器边界：

- `DoclingParser`
- `MiniMaxClient`
- `QdrantRepository`
- `Chunker`
- `Reranker`

目标：

- 确保内部接口和外部依赖的契约稳定

### 3. 集成测试

测试关键链路：

- 上传文档 -> 创建任务
- 任务执行 -> chunk 入库
- 构建索引 -> Qdrant 可检索
- 问答接口 -> 返回带引用答案
- Agent 调用 RAG -> 返回可解释结果

### 4. 评测测试

这是效果回归，不是普通单测。

测试内容：

- 检索是否打中
- 问答是否引用正确
- 中英文查询是否稳定
- 故障码、型号、参数表问题是否覆盖

## 6.3 各阶段的 TDD 执行方式

### 第一阶段 TDD

以 user story 驱动：

1. 写验收测试
2. 写单元测试
3. 写最小实现
4. 跑集成测试
5. 重构

示例 user stories：

- 作为后台用户，我上传 PDF 后应能看到解析任务状态
- 作为问答用户，我提问后应能看到带页码引用的回答
- 作为管理员，我应能重试失败的解析任务
- 作为问答用户，我用中文提问英文文档内容时应能召回相关 chunk

### 第二阶段 TDD

重点测试：

- Agent 工具调用
- 多轮上下文是否正确
- Agent 是否错误地绕过 RAG 服务
- 工具结果汇总是否正确

### 第三阶段 TDD

重点测试：

- 鉴权与权限
- 任务队列稳定性
- 版本切换与回滚
- 可观测性字段是否完整
- 性能与容量基线

## 6.4 推荐测试工具

- `pytest`
- `pytest-asyncio`
- `httpx`
- `respx` 或等价 mock 工具
- `testcontainers` 或 docker compose 集成测试环境

如果第二阶段启用 `PydanticAI`：

- 使用其测试能力替代真实模型调用

## 6.5 开发日常流程

每个功能按如下流程推进：

1. 写一个用户故事
2. 写一个失败的验收测试
3. 写失败的单元测试
4. 实现最小代码
5. 测试通过
6. 重构
7. 跑回归测试和评测

建议强制规则：

- PR 必须包含测试
- bug fix 必须包含回归测试
- 检索相关修改必须附带评测结果

## 7. 建议的代码分层

```text
frontend/
backend/
  app/
    api/
    auth/
    rag/
      ingestion/
      parsing/
      chunking/
      embedding/
      retrieval/
      rerank/
      synthesis/
    agent/
      tools/
      orchestration/
    jobs/
    repositories/
    models/
    services/
    observability/
tests/
  unit/
  contract/
  integration/
  eval/
docs/
data/
```

## 8. 里程碑建议

### 阶段一里程碑

- M1：上传、任务表、解析打通
- M2：chunk 预览与索引构建打通
- M3：hybrid search + answer 打通
- M4：后台管理页和问答页可用

### 阶段二里程碑

- M5：Agent 页面与工具调用打通
- M6：多轮对话和 trace 展示打通

### 阶段三里程碑

- M7：鉴权、日志、评测、版本发布打通
- M8：多用户、多知识库、回滚与运维能力完善

## 9. 最终一句话方案

第一阶段构建一个手搓的、可控的、支持混合检索和文档治理的 RAG 平台；第二阶段在其之上使用 `PydanticAI` 增加 Agent 能力；第三阶段补齐鉴权、异步任务、观测、评测、版本化和发布能力，形成最终产品。
