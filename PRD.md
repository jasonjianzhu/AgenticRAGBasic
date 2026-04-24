# AgenticRAG 产品需求文档（PRD）

## 文档信息

| 版本 | 日期 | 作者 | 说明 |
|------|------|------|------|
| v0.2 | 2026-04-21 | AgenticRAG Team | 补充完善各阶段细节 |
| v0.1 | 2026-04-21 | AgenticRAG Team | 初始版本 |

---

## 1. 产品概述

### 1.1 产品定位

AgenticRAG 是一款面向储能行业的智能知识库与问答平台。系统以可控、可测、可追溯的 RAG（检索增强生成）为核心，向上封装 Agent 能力，最终形成面向运营人员的知识库管理工具和面向最终用户的智能问答 Agent。

产品分四阶段推进：
1. **知识库平台**：文档上传、解析、chunk、索引构建
2. **RAG 知识问答**：混合检索、query 改写、带引用问答
3. **Agent 构建**：多轮对话、工具调用、trace 展示
4. **最终产品化**：鉴权、权限、观测、评测、版本、发布、运维

### 1.2 核心价值

- **知识可控**：文档解析、chunk 切分、索引构建全链路自研，确保检索效果可优化、可评测
- **答案可溯**：所有回答附带来源页码和引用块，方便核查
- **架构灵活**：RAG 与 Agent 分层解耦，RAG 作为原子服务被 Agent 调用
- **渐进建设**：分为四阶段推进，每阶段均有明确完成标准

### 1.3 目标用户

| 角色 | 说明 |
|------|------|
| 管理员 (admin) | 系统配置、知识库管理、版本发布 |
| 运营人员 (operator) | 文档上传、解析触发、状态监控、失败重试 |
| 问答用户 (user) | 面向最终用户，使用 RAG 问答或 Agent 对话 |

---

## 2. 系统架构

### 2.1 基础设施

| 组件 | 用途 | 引入阶段 |
|------|------|----------|
| PostgreSQL | 业务数据持久化（文档、chunk、任务、会话、配置、审计） | 第一阶段 |
| Qdrant | 向量检索（dense + sparse hybrid search） | 第一阶段 |
| Redis | 异步任务队列（RQ）、缓存 | 第一阶段 |
| TEI Embedding (BGE-M3) | 文本向量化，同时输出 dense 和 sparse 向量 | 第一阶段 |
| TEI Reranker | 重排服务（默认关闭，按需开启） | 第二阶段 |
| MiniMax M2.7 (Anthropic-compatible API) | Query 改写、答案生成、Agent 对话 | 第二阶段 |
| Langfuse | LLM 调用 trace、检索链路观测 | 第二阶段 |
| 业务数据库 (PostgreSQL) | 储能设备运行数据、告警记录（只读连接） | 第三阶段 |
| ECharts (前端) | 数据分析图表渲染 | 第三阶段 |
| PydanticAI | Agent 框架，工具调用编排 | 第三阶段 |
| MinIO (S3-compatible) | 对象存储，统一文件管理 | 第四阶段 |

### 2.2 总体架构

```
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
| RAG Service |     | Agent Service |     | Admin Jobs |
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
               +----------+                        |
                    |                               |
                    v                               v
               +----+-------------------------------+---+
               | Model Layer                            |
               | - Docling                              |
               | - TEI Embedding                        |
               | - TEI Reranker(optional)              |
               | - MiniMax                             |
               +---------------------------------------+
```

### 2.3 技术选型

| 层次 | 技术选型 | 说明 |
|------|----------|------|
| 后端框架 | FastAPI | 主 API 层 |
| Agent 框架 | PydanticAI | 第三阶段引入，不接管底层 RAG |
| PDF 解析 | Docling | 结构化输出，支持表格和图片 |
| Embedding 模型 | BGE-M3 (via TEI) | 同时输出 dense vector + sparse vector，一次推理两种向量 |
| 检索库 | Qdrant | 支持 dense + sparse 混合检索 |
| 业务库 | PostgreSQL | 主数据存储 |
| 异步任务 | Redis + RQ | 解析、chunk、embed、index |
| LLM | MiniMax M2.7 | Anthropic-compatible API |
| 前端 | 一个工程，多个页面 | 管理页（知识库/文档）、RAG 问答页、Agent 对话页 |
| 文件存储 | 本地文件系统（第一~三阶段）→ MinIO（第四阶段） | 通过抽象接口隔离 |

---

## 3. 文档与任务状态流转

### 3.1 文档状态

```
uploaded → parsing → chunked → indexing → ready
    ↓         ↓          ↓          ↓       ↓
  failed   failed    failed     failed    disabled
```

| 状态 | 说明 |
|------|------|
| uploaded | 文件已上传，待解析 |
| parsing | 解析中 |
| chunked | 解析完成，chunk 已生成，待索引构建 |
| indexing | 索引构建中 |
| ready | 可参与检索 |
| failed | 失败（可重试） |
| disabled | 人工禁用 |

### 3.2 任务状态

| 状态 | 说明 |
|------|------|
| queued | 等待执行 |
| started | 执行中 |
| finished | 成功完成 |
| failed | 失败 |
| retrying | 重试中 |

---

## 4. 第一阶段：知识库平台

### 4.1 阶段目标

交付文档上传、解析、chunk 生成、索引构建的后台管理能力，并提供轻量检索调试手段供运营人员验证索引质量。支持：

- 知识库 CRUD 与配置管理
- PDF 上传与去重
- Docling 文档解析（fast/balanced/accurate 三档）
- Chunker Registry（docling_hybrid / markdown_header / recursive_token / table_chunker）
- chunk 预览与持久化
- TEI embedding (BGE-M3) 同时生成 dense + sparse 向量，Qdrant 索引入库
- 文档启用/禁用管理
- 轻量检索调试接口（验证索引质量）
- 后台管理页面

### 4.2 核心功能

#### 4.2.1 知识库管理

- 知识库创建、编辑、删除
- 知识库配置（默认 chunker 策略、默认解析 profile、embedding 模型）
- 知识库统计概览（文档数、chunk 数、就绪文档数、失败文档数、最后构建时间）
- 知识库列表与详情

#### 4.2.2 文档上传与管理

- 文件上传至指定知识库
- 文件 hash 去重（SHA-256）
- 文档元数据保存（名称、大小、类型、上传时间）
- 文档列表与详情（支持按状态筛选）
- 文档启用/禁用（禁用的文档不参与检索）
- 文档删除策略：软删除标记 + 异步清理关联 chunk 和 Qdrant 向量
- 批量操作：批量上传、批量重建索引、批量启用/禁用

#### 4.2.3 文档解析（Docling）

三种解析 profile：

| Profile | 适用场景 |
|--------|----------|
| fast | 文本型 PDF，关闭重型 OCR 和高精度表格推理 |
| balanced | 默认模式，保留结构和表格能力 |
| accurate | 扫描件、复杂表格、复杂手册 |

解析兜底策略：纯文本 PDF 走轻量抽取；Docling 失败时回退。

#### 4.2.4 Chunk 构建（Chunker Registry）

| Chunker | 说明 |
|---------|------|
| docling_hybrid | 结构感知 + token 限制 |
| markdown_header | 按标题层级切分 |
| recursive_token | 兜底切块器 |
| table_chunker | 表格专用，保留表头，避免上下文丢失 |

Chunk 规格：

- 正文：约 300-600 tokens
- overlap：约 50-80 tokens
- 每个 chunk 带 metadata（kb_id, doc_id, doc_version, source_path, page_start, page_end, section_path, chunk_type, language, product_model）

文档类型识别：支持 `manual`、`faq`、`qa`、`spec`、`unknown`，支持人工指定和自动分类。

#### 4.2.5 索引与存储

- BGE-M3 (TEI) 一次推理同时生成 dense 向量和 sparse 向量
- Qdrant collection 同时存储 dense vector + sparse vector + payload metadata
- 元数据过滤（kb、文档状态、文档类型、语言、产品型号）
- 索引重建接口（按文档或按知识库粒度）
- 文档删除时同步清理 Qdrant 中对应 point

#### 4.2.6 检索调试

第一阶段提供轻量检索调试接口，供运营人员验证索引质量：

- 输入 query，直接执行 dense + sparse hybrid search
- 返回 top-k chunks（含 score、metadata、内容片段）
- 不做 query rewrite，不做 answer generation
- 用于判断索引是否正确构建、chunk 质量是否合格

#### 4.2.7 异步任务

使用 Redis + RQ 实现异步任务，与第一阶段同步建设。

队列定义：

- `ingestion`：解析 + chunk
- `indexing`：embedding + 索引构建

worker 支持：任务入队、状态同步、失败重试（retry）、超时控制、任务日志记录。

### 4.3 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/kb` | POST | 创建知识库 |
| `/kb` | GET | 知识库列表 |
| `/kb/{kb_id}` | GET | 知识库详情（含统计） |
| `/kb/{kb_id}` | PUT | 更新知识库配置 |
| `/kb/{kb_id}` | DELETE | 删除知识库 |
| `/kb/{kb_id}/build` | POST | 触发知识库索引构建 |
| `/kb/{kb_id}/search_debug` | POST | 检索调试（轻量，不含 rewrite/answer） |
| `/documents/upload` | POST | 上传文档 |
| `/documents` | GET | 文档列表（支持筛选） |
| `/documents/{doc_id}` | GET | 文档详情 |
| `/documents/{doc_id}/chunks` | GET | 文档 chunk 预览 |
| `/documents/{doc_id}/enable` | POST | 启用文档 |
| `/documents/{doc_id}/disable` | POST | 禁用文档 |
| `/documents/{doc_id}` | DELETE | 删除文档 |
| `/jobs` | GET | 任务列表 |
| `/jobs/{job_id}` | GET | 任务状态 |
| `/jobs/{job_id}/retry` | POST | 重试任务 |

### 4.4 文件存储规范

第一阶段使用本地文件系统，通过抽象接口隔离，第四阶段切换 MinIO。

目录结构：

```
var/
├── uploads/{kb_id}/{doc_id}/{filename}       # 原始上传文件
├── parsed/{kb_id}/{doc_id}/{version}/        # Docling 解析产物（JSON）
└── logs/                                      # 应用日志
```

规则：
- 文件以 `{原始文件名}` 保存，路径中用 kb_id/doc_id 隔离
- 解析产物按 version 目录组织，支持多版本
- 文档删除时异步清理对应文件和解析产物

### 4.5 资源约束

| 约束项 | 限制 | 说明 |
|--------|------|------|
| 单文件大小上限 | 50 MB | 超过拒绝上传 |
| 支持文件类型 | PDF（第一阶段） | 后续扩展 DOCX、MD |
| MIME 校验 | application/pdf | 防止伪造扩展名 |
| 解析超时 | 300s / 文件 | 超时标记失败 |
| embedding 批处理 | 32 chunks / batch | TEI 单次请求上限 |
| Qdrant 写入批次 | 100 points / batch | 避免单次写入过大 |
| 单文档最大页数 | 500 页 | 超过建议拆分 |
| worker 并发数 | 可配置，默认 2 | ingestion 和 indexing 各 1 |
| 任务最大重试次数 | 2 次 | 超过标记永久失败 |

### 4.6 前端页面

| 页面 | 说明 |
|------|------|
| 知识库管理页 | 知识库列表、创建/编辑/删除、统计概览、配置管理 |
| 文档管理页 | 上传 PDF、选择知识库、查看解析状态、预览 chunk、触发索引构建、失败重试、批量操作 |
| 检索调试页 | 输入 query 测试检索效果、查看命中 chunk 和 score |

### 4.7 第一阶段完成标准

- [ ] 知识库 CRUD 和配置管理可用
- [ ] 上传、解析、chunk、索引链路可跑通
- [ ] 管理页面可用
- [ ] chunk 预览可用
- [ ] 检索调试接口可验证索引质量
- [ ] 文档启用/禁用/删除功能正常
- [ ] 异步任务失败可重试、可追踪
- [ ] 测试体系初步建立

---

## 5. 第二阶段：RAG 知识问答

### 5.1 阶段目标

在知识库平台基础上，增加 RAG 问答能力，面向问答用户（user）提供可引用的检索增强生成服务。

### 5.2 核心功能

#### 5.2.1 混合检索

- dense retrieval（BGE-M3 dense vector 查询）
- sparse retrieval（BGE-M3 sparse vector 查询，利用第一阶段已入库的 sparse 向量）
- hybrid retrieval（RRF 融合 dense + sparse 结果）
- metadata filter（按 kb、文档状态、文档类型、语言、产品型号）
- 多知识库检索：支持指定多个 kb_id 联合检索，结果统一 RRF 融合排序

#### 5.2.2 Query 处理

- query 标准化（全角转半角、多余空格清理）
- query rewrite + expansion（MiniMax，输出结构化改写结果）
- retrieval context 提取（从 query 中识别产品型号、语言、故障码、文档类型）
- retrieval context 历史继承（最近 N 轮检索上下文合并）
- context packing（将命中 chunk 组装为 LLM 输入上下文）

#### 5.2.3 可选重排

- TEI Reranker（默认关闭，按需开启，避免资源浪费）
- 统一 rerank 接口（支持切换实现）
- top-n 重排（对 hybrid search 结果取 top-20 候选，rerank 后取 top-5）
- 懒加载：仅在开启时加载模型

#### 5.2.4 答案生成

- answer generation（MiniMax，流式输出）
- 引用拼接（文档名 + 页码 + 命中 chunk 摘要）
- grounded answer：system prompt 约束回答必须基于检索内容，无法回答时明确告知
- 拒答策略：检索结果为空或 score 过低时，返回"未找到相关信息"而非编造

#### 5.2.5 流式输出

使用 SSE（Server-Sent Events）实现流式答案传输：

事件类型：

| 事件 | 说明 |
|------|------|
| `token` | 答案 token 片段 |
| `citation` | 引用信息（文档名、页码、chunk_id） |
| `trace` | 检索 trace 摘要（query rewrite、检索模式、命中数） |
| `done` | 流结束标记 |
| `error` | 错误信息 |

支持客户端主动断开连接取消生成。

### 5.3 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/rag/search` | POST | 检索接口，返回命中 chunk 和 trace 摘要 |
| `/rag/answer` | POST | 问答接口，SSE 流式返回带引用答案 |
| `/rag/config` | GET/PUT | RAG 配置（top-k、rerank 开关、context 窗口等） |

### 5.4 前端页面

| 页面 | 说明 |
|------|------|
| RAG 问答页 | 输入问题、展示流式答案、展示引用来源和命中 chunk、可选显示 query rewrite |

### 5.5 第二阶段完成标准

- [ ] 混合检索可用（dense + sparse + RRF）
- [ ] query rewrite 生效
- [ ] rerank 可配置开启，默认关闭
- [ ] 返回流式答案带引用
- [ ] 多知识库联合检索可用
- [ ] 问答页面端到端可用
- [ ] 基线评测可重复执行
- [ ] Langfuse trace 可查看 LLM 调用链路

---

## 6. 第三阶段：Agent 构建

### 6.1 阶段目标

在第二阶段已有 RAG 服务基础上增加 Agent，对外提供多轮对话、意图路由、工具调用和数据分析能力，面向最终用户。Agent 需要同时具备三条核心链路：

1. **知识问答链路**：调用 RAG 服务检索知识库，生成带引用的答案
2. **数据分析链路**：连接业务数据库，生成 SQL 查询运行数据，返回结构化数据 + 图表配置
3. **混合链路**：先查数据再查知识库（或反过来），汇总多源结果

### 6.2 Agent 核心能力

#### 6.2.1 意图路由

Agent 接收用户消息后，由 LLM 自主判断应该调用哪些工具：

| 意图类型 | 示例 | 工具链路 |
|----------|------|----------|
| 知识问答 | "电池过温告警怎么处理" | `rag_search_tool` → 生成答案 |
| 数据查询 | "查一下昨天的设备运行状况" | `sql_query_tool` → 返回数据 |
| 数据分析 | "对比最近7天的故障统计" | `sql_query_tool` → `chart_tool` → 总结 |
| 混合查询 | "E003告警最近一周出现了几次，怎么处理" | `sql_query_tool` + `rag_search_tool` → 汇总 |
| 闲聊/兜底 | "你好"、"谢谢" | 直接回复，不调用工具 |

意图路由不需要显式分类器，由 PydanticAI Agent 框架 + system prompt + 工具描述驱动 LLM 自主决策。

#### 6.2.2 多轮对话

- 会话级上下文维护（历史消息传入 LLM）
- 支持多轮追问（"那 E004 呢？"能继承上文语境）
- 工具调用结果纳入对话历史
- 上下文窗口截断（超出后丢弃早期消息）

#### 6.2.3 多步任务拆解

Agent 可自主将复杂问题拆解为多步工具调用：

- 先查数据，再查知识库，最后汇总
- 先查一个子问题，根据结果决定下一步查询（多跳）
- 查询失败时自动降级或换一种方式查询

#### 6.2.4 结构化输出

Agent 的回答不仅是纯文本，还可能包含：

- 文本答案（Markdown 格式）
- 引用来源（知识问答场景）
- 数据表格（SQL 查询结果）
- 图表配置（前端渲染用）
- 工具调用过程（trace）

### 6.3 业务数据库（只读）

Agent 通过 `sql_query_tool` 连接储能业务数据库（与 AgenticRAG 主库分离），执行只读查询。

#### 6.3.1 业务数据库 Schema（示例）

业务数据库为已有系统，Agent 只做只读连接。以下为典型表结构（实际以对接时为准）：

| 表名 | 说明 | 典型字段 |
|------|------|----------|
| `devices` | 设备台账 | id, device_name, device_model, site_name, status, installed_at |
| `device_metrics` | 设备运行指标（时序） | id, device_id, metric_name, metric_value, recorded_at |
| `alarms` | 告警记录 | id, device_id, alarm_code, alarm_level, message, occurred_at, resolved_at |
| `maintenance_logs` | 维护记录 | id, device_id, maintenance_type, description, performed_at, performed_by |

#### 6.3.2 SQL 安全策略

| 策略 | 说明 |
|------|------|
| 只读连接 | 使用只读数据库用户，连接串独立配置 |
| SELECT only | 应用层校验 SQL，拒绝 INSERT/UPDATE/DELETE/DROP/ALTER 等 |
| 表白名单 | 只允许查询配置中声明的表，防止越权访问 |
| 行数限制 | 单次查询最多返回 500 行 |
| 超时控制 | 单次查询超时 30 秒 |
| Schema 注入 | 将表结构描述注入 Agent system prompt，帮助 LLM 生成正确 SQL |

#### 6.3.3 SQL 生成流程

```
用户问题
  → Agent 判断需要查数据
  → LLM 根据 schema 描述生成 SQL
  → 应用层校验 SQL（只读 + 白名单 + 行数限制）
  → 执行查询，返回结果
  → Agent 根据结果生成文字总结 / 调用 chart_tool 生成图表
```

### 6.4 图表能力

Agent 在数据分析场景下，可以返回图表配置供前端渲染。

#### 6.4.1 图表类型

| 类型 | 适用场景 | 示例 |
|------|----------|------|
| 折线图 (line) | 时序趋势 | 最近7天电池温度变化 |
| 柱状图 (bar) | 分类对比 | 各站点故障次数对比 |
| 饼图 (pie) | 占比分布 | 告警类型分布 |
| 表格 (table) | 明细数据 | 设备运行状态列表 |
| 面积图 (area) | 累积趋势 | 累计发电量 |
| 堆叠柱状图 (stacked_bar) | 多维对比 | 各站点各类型告警统计 |

#### 6.4.2 图表配置协议

Agent 通过 `chart_tool` 输出标准化图表配置，前端使用 ECharts 渲染：

```json
{
  "chart_type": "line",
  "title": "最近7天电池平均温度",
  "x_axis": {"label": "日期", "data": ["04-17", "04-18", "04-19", "04-20", "04-21", "04-22", "04-23"]},
  "y_axis": {"label": "温度 (°C)"},
  "series": [
    {"name": "1号电池组", "data": [35.2, 36.1, 34.8, 37.5, 36.9, 35.4, 36.2]},
    {"name": "2号电池组", "data": [34.8, 35.5, 34.2, 36.8, 36.1, 34.9, 35.7]}
  ]
}
```

图表配置由 LLM 根据 SQL 查询结果生成，通过 SSE `chart` 事件发送给前端。

### 6.5 会话管理

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 会话过期时间 | 24 小时 | 超时自动归档 |
| 上下文窗口 | 最近 20 条消息 | 超出后截断早期消息 |
| 历史压缩策略 | 摘要压缩 | 超出窗口的历史生成摘要保留 |
| 最大并发会话数 | 不限（第三阶段） | 第四阶段按用户限制 |
| 工具调用失败降级 | 返回错误说明，不中断对话 | Agent 告知用户工具暂不可用 |

#### 6.5.1 会话持久化与恢复

- 用户消息和 Agent 回答实时持久化到数据库（chat_sessions + chat_messages 表）
- Agent 回答在后端执行完成后立即保存，不依赖前端连接状态
- 用户切换页面或关闭浏览器后，对话记录不丢失
- 前端通过 localStorage 记住当前会话 ID，切回 Agent 页面时自动恢复上次会话
- 如果切换页面时 Agent 正在生成回答，后端继续执行并保存结果，用户切回后可看到完整回答
- 会话侧边栏支持查看历史会话列表，点击可切换到任意历史会话

### 6.6 Agent 与 RAG 的职责边界

| RAG 层管理 | Agent 层管理 |
|------------|-------------|
| Query rewrite | 意图路由（知识问答 / 数据分析 / 混合） |
| retrieval context | 多轮对话上下文 |
| 检索过滤条件 | 工具调用编排与结果汇总 |
| 上下文拼装 | SQL 生成与校验 |
| 引用拼接 | 图表配置生成 |

### 6.7 Agent 工具集

| 工具 | 说明 | 输入 | 输出 |
|------|------|------|------|
| `rag_search_tool` | 检索知识库，返回相关 chunk，Agent 自行总结回答 | query, kb_ids, top_k, filters | 命中 chunk 列表 + trace |
| `sql_query_tool` | 查询业务数据库 | sql（LLM 生成） | 查询结果（行列数据） |
| `chart_tool` | 生成图表配置 | chart_type, title, data | ECharts 配置 JSON |

### 6.8 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/agent/chat` | POST | Agent 对话（SSE 流式） |
| `/agent/sessions` | GET | 会话列表 |
| `/agent/sessions/{session_id}` | GET | 会话详情（含历史消息） |
| `/agent/sessions/{session_id}` | DELETE | 删除会话 |
| `/agent/db/schema` | GET | 查看业务数据库可用表结构（管理用） |
| `/agent/db/test` | POST | 测试业务数据库连接（管理用） |

### 6.9 SSE 事件协议（Agent 对话）

| 事件 | 说明 |
|------|------|
| `token` | 答案 token 片段 |
| `tool_start` | 工具调用开始（工具名 + 参数摘要） |
| `tool_result` | 工具调用结果摘要 |
| `citation` | 引用信息（知识问答场景） |
| `data_table` | SQL 查询结果（表格数据） |
| `chart` | 图表配置（ECharts JSON） |
| `trace` | Agent trace 摘要 |
| `done` | 流结束标记 |
| `error` | 错误信息 |

### 6.10 前端页面

| 页面 | 说明 |
|------|------|
| Agent 对话页 | 多轮聊天界面、流式输出、工具调用过程展示、引用来源展示、数据表格渲染、ECharts 图表渲染、会话列表侧边栏 |

### 6.11 第三阶段完成标准

- [ ] Agent 对话页面可用（多轮聊天 + 流式输出）
- [ ] 意图路由正确（知识问答 / 数据分析 / 混合查询）
- [ ] Agent 能调用 RAG 服务进行知识问答
- [ ] Agent 能连接业务数据库执行只读 SQL 查询
- [ ] SQL 安全策略生效（只读、白名单、行数限制、超时）
- [ ] 数据查询结果可展示为表格
- [ ] 图表配置可生成，前端 ECharts 渲染正确
- [ ] 多轮对话稳定（上下文继承、追问有效）
- [ ] 工具调用过程可见（tool_start / tool_result 事件）
- [ ] 会话管理可用（创建、列表、详情、删除）
- [ ] 不破坏第二阶段 RAG 功能

---

## 7. 第四阶段：最终产品化

### 7.1 阶段目标

补齐鉴权、权限、观测、评测、版本、发布和运维能力，形成可稳定运行的产品。

### 7.2 鉴权与权限

- JWT 登录
- RBAC：admin、operator、user
- 后台页面权限限制
- 知识库访问权限限制
- 预留 OIDC/SSO 接入能力

### 7.3 版本与发布

- 文档版本管理
- 索引版本管理
- 知识库发布版本
- 回滚能力
- 灰度发布策略

### 7.4 可观测性

- 结构化日志
- 接入 OpenTelemetry
- 接入 Langfuse 或 Phoenix
- request_id 贯穿
- query trace 记录
- Agent trace 记录
- 错误聚合视图

### 7.5 安全与审计

- 操作审计日志
- 配置脱敏
- 文件大小限制
- MIME 校验
- 路径安全校验

### 7.6 并发控制与资源隔离

#### 7.6.1 API 限流

| 策略 | 说明 |
|------|------|
| 全局限流 | 基于 Redis 的滑动窗口限流，防止单实例过载 |
| 用户级限流 | 每用户每分钟最大请求数（Agent 对话、RAG 问答分别限制） |
| LLM 调用限流 | MiniMax API 并发上限保护，超出排队或拒绝 |
| 慢查询保护 | SQL 查询超时 30s，LLM 调用超时 60s，防止单请求占用过久 |

#### 7.6.2 资源隔离

| 资源 | 隔离策略 |
|------|----------|
| 数据库连接池 | 主库和业务库独立连接池，互不影响 |
| 会话数据 | 按用户隔离，用户只能访问自己的会话 |
| 知识库访问 | 按权限控制，不同角色可见不同知识库 |
| Embedding 推理 | 本地模型串行推理，多请求通过 asyncio.to_thread 排队；高并发场景需部署 TEI 服务横向扩展 |
| Agent 实例 | 无状态单例，deps 按请求隔离，多用户共享不冲突 |

#### 7.6.3 高并发部署建议

- 多 worker 部署：`uvicorn --workers N` 或 gunicorn + uvicorn worker
- Embedding 推理瓶颈：本地模型改为 TEI 服务（HTTP 调用，可独立扩缩容）
- LLM 瓶颈：MiniMax API 本身支持并发，必要时增加 API Key 轮换
- 数据库：连接池参数按并发量调整（pool_size、max_overflow）
- Redis：限流计数器 + 任务队列，单实例足够

### 7.6 存储与部署

- 接入 MinIO（S3-compatible）对象存储，替代本地文件系统
- 文件存储接口不变，仅切换底层实现
- 原始文件、解析产物、导出数据统一存入 MinIO
- docker compose 优化（含 MinIO 服务）
- 部署文档
- 备份与恢复文档（含 MinIO bucket 备份）

### 7.7 评测体系

| 指标 | 说明 |
|------|------|
| Hit@K | 检索命中率 |
| MRR | 平均倒数排名 |
| 引用命中率 | 答案引用是否命中 |
| Groundedness | 回答是否基于检索内容 |

评测集覆盖：

- 产品参数问答
- 告警码问答
- 安装维护问答
- 中英跨语言问答

### 7.8 第四阶段完成标准

- [ ] 系统支持多用户与多角色
- [ ] 支持版本发布与回滚
- [ ] 支持观测和追踪
- [ ] 支持审计
- [ ] 支持稳定部署和运维

---

## 8. 术语表

| 术语 | 说明 |
|------|------|
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| Chunk | 文档切分后的文本块 |
| Hybrid Retrieval | 混合检索（dense + sparse + RRF 融合） |
| Dense Retrieval | 基于向量相似度的检索 |
| Sparse Retrieval | 基于稀疏向量的检索（本项目使用 BGE-M3 输出的 sparse embedding） |
| RRF | Reciprocal Rank Fusion，反向排名融合 |
| Rerank | 对检索结果进行二次排序 |
| Query Rewrite | 对用户问题进行改写和扩充 |
| Docling | PDF/文档解析库 |
| Chunker | 文档切分策略注册器 |
| PydanticAI | Agent 编排框架（第三阶段引入） |
| TEI | Text Embeddings Inference，HuggingFace 推理服务 |
| BGE-M3 | 多语言 embedding 模型，同时输出 dense 和 sparse 向量 |
| SSE | Server-Sent Events，服务端推送事件，用于流式输出 |
| Langfuse | LLM 可观测性平台，记录调用 trace |
| MinIO | S3-compatible 对象存储服务 |

---

## 9. 附录

### 9.1 四阶段里程碑

| 里程碑 | 内容 |
|--------|------|
| M1（第一阶段） | 知识库 CRUD、上传、任务表、解析、chunk 打通 |
| M2（第一阶段） | 索引构建打通、检索调试接口可用 |
| M3（第二阶段） | hybrid search + rerank + query rewrite 打通 |
| M4（第二阶段） | 流式 answer + RAG 问答页可用 |
| M5（第三阶段） | Agent 框架 + 会话管理 + RAG 工具调用打通 |
| M6（第三阶段） | 业务数据库 SQL 查询 + 图表生成 + 多轮对话 + Agent 对话页可用 |
| M7（第四阶段） | 鉴权、日志、评测、版本发布打通 |
| M8（第四阶段） | MinIO 接入、多用户、回滚与运维能力完善 |

### 9.2 测试分层

| 测试类型 | 说明 |
|----------|------|
| 单元测试 | 纯逻辑，不依赖外部服务 |
| 契约测试 | 测试适配器边界（Parser、Client、Repository） |
| 集成测试 | 关键链路端到端测试 |
| 评测测试 | 检索效果和答案质量回归 |

### 9.3 四阶段依赖关系

```
第一阶段（知识库平台）
    ↓
第二阶段（RAG 知识问答）依赖第一阶段
    ↓
第三阶段（Agent 构建）依赖第二阶段
    ↓
第四阶段（产品化）依赖前三阶段
```

### 9.4 Sparse Retrieval 技术方案

本项目使用 BGE-M3 模型同时输出 dense 和 sparse 向量，不额外引入 BM25 或 SPLADE。

原因：
- BGE-M3 原生支持 multi-representation（dense + sparse + colbert）
- 一次推理同时获得两种向量，无需维护额外模型
- sparse 输出为 token-weight 稀疏向量，可直接存入 Qdrant sparse vector 字段
- 中英文多语言效果好，适合储能行业中英混合文档

索引构建流程（第一阶段）：
1. chunk 文本送入 TEI (BGE-M3)
2. 获取 dense vector (1024 维) + sparse vector (token-weight pairs)
3. 同时写入 Qdrant 的 dense 和 sparse 字段

检索流程（第二阶段）：
1. query 送入 TEI (BGE-M3) 获取 dense query vector + sparse query vector
2. 分别执行 dense search 和 sparse search
3. RRF 融合两路结果
4. rerank 后返回 top-k

### 9.5 错误处理与重试策略

| 场景 | 策略 |
|------|------|
| 解析失败 | 自动重试 2 次（指数退避），仍失败标记 failed，支持手动重试 |
| 部分解析成功 | 按页记录解析状态，已成功的页保留，失败页可单独重试 |
| embedding 调用失败 | 按 batch 重试，单 batch 失败不影响其他 batch |
| Qdrant 写入失败 | 整文档重试索引构建 |
| 索引构建失败 | 文档状态回退到 chunked，不影响已有索引 |
| 任务超时 | 标记 failed，记录超时时间点，支持手动重试 |
| 文档删除 | 软删除 → 异步清理 chunk 记录 → 异步清理 Qdrant points |
