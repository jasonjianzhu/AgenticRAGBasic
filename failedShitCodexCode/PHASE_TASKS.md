# AgenticRAG 三阶段任务清单

本文档用于把 [IMPLEMENTATION_PLAN.md](/Users/zhujian/Code/AgenticRAG/IMPLEMENTATION_PLAN.md) 落成可执行任务列表。任务按三阶段组织，每阶段同时包含：

- 产品与功能任务
- 后端任务
- 前端任务
- 数据与基础设施任务
- 测试任务
- 阶段完成标准

## 1. 使用方式

- 以阶段为单位推进，不跨阶段提前大规模扩展
- 每个任务都必须能映射到一个用户故事或技术目标
- 每个功能任务都要配套测试任务
- 每个 bug 修复必须追加回归测试
- 每个检索效果调整都必须跑评测

## 2. 第一阶段任务：文档解析、知识库构建、RAG 问答

## 2.1 阶段目标

交付一个可用的知识库问答系统，支持：

- 上传储能产品 PDF
- 解析文档并构建 chunk
- 生成 embedding 并建立混合检索索引
- 使用混合检索进行问答
- 返回带引用的答案
- 通过后台页面完成知识库管理

## 2.2 产品与功能任务

- 定义第一阶段用户角色
  - 管理员
  - 知识库运营人员
  - 问答用户
- 定义第一阶段核心用户故事
  - 上传文档
  - 触发解析
  - 查看任务状态
  - 预览 chunk
  - 构建索引
  - 在问答页提问并查看引用答案
- 明确文档状态流转
  - uploaded
  - parsing
  - chunked
  - indexing
  - ready
  - failed
- 明确任务状态流转
  - queued
  - started
  - finished
  - failed
  - retrying

## 2.3 后端任务

### 2.3.1 项目骨架

- 初始化后端目录结构
- 初始化 FastAPI 应用
- 初始化配置管理
- 初始化日志配置
- 初始化依赖注入基础结构
- 初始化错误处理与统一响应格式

### 2.3.2 数据模型与数据库

- 设计并创建 `knowledge_bases` 表
- 设计并创建 `documents` 表
- 设计并创建 `document_versions` 表
- 设计并创建 `chunks` 表
- 设计并创建 `query_logs` 表
- 设计并创建 `job_logs` 表
- 设计并创建 `app_configs` 表
- 初始化 Alembic 迁移体系

### 2.3.3 文档上传与管理

- 实现文档上传接口
- 实现文件 hash 去重
- 实现文档元数据保存
- 实现文档列表接口
- 实现文档详情接口
- 实现文档启用/禁用接口
- 实现文档删除策略

### 2.3.4 Redis + RQ 异步任务

- 搭建 Redis 连接层
- 搭建 RQ 队列封装
- 定义 `ingestion` 队列
- 定义 `indexing` 队列
- 实现任务入队接口
- 实现 worker 启动入口
- 实现任务状态同步逻辑
- 实现失败重试逻辑
- 实现任务日志记录
- 实现任务超时控制

### 2.3.5 文档解析

- 封装 `DoclingParser`
- 实现解析 profile
  - fast
  - balanced
  - accurate
- 实现解析结果缓存
- 实现解析超时处理
- 实现轻量文本抽取兜底
- 实现结构化解析结果存储

### 2.3.6 文档分类与 chunk 构建

- 实现文档类型识别器
- 支持文档类型人工指定
- 实现 `Chunker Registry`
- 实现 `docling_hybrid` chunker
- 实现 `markdown_header` chunker
- 实现 `recursive_token` chunker
- 实现 `table_chunker`
- 实现 chunk metadata 组装
- 实现 chunk 持久化
- 实现 chunk 预览接口

### 2.3.7 检索与索引

- 封装 embedding 接口
- 集成 embedding 模型
- 封装 Qdrant 客户端
- 创建 collection 与 payload schema
- 实现 dense 索引写入
- 实现 sparse 表达写入
- 实现 hybrid retrieval
- 实现 metadata filter
- 实现 RRF 融合
- 实现检索结果去重和截断
- 实现索引重建接口

### 2.3.8 Query 处理与问答

- 封装 MiniMax 客户端
- 实现 query normalization
- 实现 query rewrite
- 实现 query expansion
- 实现 retrieval context 提取
- 实现 retrieval context 合并
- 实现 context packing
- 实现答案生成
- 实现引用拼接
- 实现 `/rag/search`
- 实现 `/rag/answer`

### 2.3.9 可选重排

- 设计统一 `Reranker` 接口
- 集成本地 reranker
- 实现 reranker 开关
- 实现 lazy load
- 在检索链路中接入可选重排

## 2.4 前端任务

### 2.4.1 前端基础

- 初始化前端工程
- 搭建路由与布局
- 搭建 API client
- 搭建通用状态管理
- 搭建表单与上传组件
- 搭建消息通知组件

### 2.4.2 RAG 问答页面

- 实现输入框与提交逻辑
- 实现流式回答展示
- 实现引用来源展示
- 实现命中 chunk 展示
- 实现 query rewrite 展示开关
- 实现错误提示与重试

### 2.4.3 文档管理和知识库构建页面

- 实现知识库列表
- 实现文档上传页面
- 实现文档状态列表
- 实现任务状态展示
- 实现 chunk 预览页面
- 实现索引构建按钮
- 实现失败重试按钮
- 实现文档启用/禁用操作

## 2.5 基础设施任务

- 配置 Postgres
- 配置 Redis
- 配置 Qdrant
- 配置本地文件存储目录
- 配置环境变量管理
- 配置本地开发启动脚本
- 编写 docker compose
- 编写 README 启动说明

## 2.6 第一阶段测试任务

### 2.6.1 单元测试

- 测试文档状态流转
- 测试任务状态流转
- 测试文件 hash 去重
- 测试文档类型识别
- 测试 chunk 切分逻辑
- 测试表格 chunk 逻辑
- 测试 retrieval context 合并逻辑
- 测试 query rewrite 结构化输出校验
- 测试 RRF 融合逻辑
- 测试 reranker 开关逻辑

### 2.6.2 契约测试

- 测试 `DoclingParser` 接口契约
- 测试 `MiniMaxClient` 接口契约
- 测试 `QdrantRepository` 接口契约
- 测试 `EmbeddingProvider` 接口契约
- 测试 `Reranker` 接口契约

### 2.6.3 集成测试

- 测试文档上传到数据库保存
- 测试上传后任务成功入队
- 测试 worker 能完成 parse -> chunk -> embed -> index
- 测试 `/rag/search` 能返回命中 chunk
- 测试 `/rag/answer` 能返回带引用答案
- 测试文档禁用后不再参与检索
- 测试索引重建流程

### 2.6.4 评测测试

- 构建首批评测样本
  - 产品参数问答
  - 告警码问答
  - 安装维护问答
  - 中英跨语言问答
- 评估 `Hit@K`
- 评估 `MRR`
- 评估引用命中率
- 评估答案 groundedness

## 2.7 第一阶段完成标准

- 上传、解析、chunk、索引链路可跑通
- 问答页面可用
- 管理页面可用
- 混合检索可用
- 返回答案带引用
- 测试体系初步建立
- 基线评测可重复执行

## 3. 第二阶段任务：增加 Agent

## 3.1 阶段目标

在第一阶段已有 RAG 服务基础上增加 Agent，对外提供多轮对话和工具调用能力。

## 3.2 产品与功能任务

- 定义 Agent 页面交互方式
- 定义 Agent 可调用工具集合
- 明确 Agent 与 RAG 的职责边界
- 定义 Agent 多轮上下文规则
- 定义 Agent 工具调用 trace 展示方式

## 3.3 后端任务

### 3.3.1 Agent 基础框架

- 集成 `PydanticAI`
- 封装 Agent service
- 定义 Agent 输入输出 schema
- 实现 Agent 会话管理
- 实现 Agent 消息存储

### 3.3.2 Tool 层

- 实现 `rag_search_tool`
- 实现 `rag_answer_tool`
- 实现 `document_lookup_tool`
- 预留 `sql_tool`
- 预留 `api_tool`
- 预留 `rule_tool`

### 3.3.3 Agent 运行时

- 实现多轮上下文维护
- 实现工具调用策略
- 实现工具结果汇总
- 实现结构化回答生成
- 实现引用结果回传
- 实现 Agent trace 输出

### 3.3.4 API

- 实现 `POST /agent/chat`
- 实现 `GET /agent/sessions`
- 实现 `GET /agent/sessions/{session_id}`
- 实现 Agent trace 查询接口

## 3.4 前端任务

### 3.4.1 Agent 对话页面

- 实现多轮聊天界面
- 实现流式输出
- 实现工具调用过程展示
- 实现引用来源展示
- 实现中间 trace 折叠展示
- 实现会话列表

## 3.5 数据与基础设施任务

- 扩展会话与消息表
- 扩展 Agent trace 存储
- 扩展工具调用日志
- 补充 Agent 环境配置

## 3.6 第二阶段测试任务

### 3.6.1 单元测试

- 测试 Agent 上下文拼接逻辑
- 测试工具选择逻辑
- 测试工具结果汇总逻辑
- 测试会话状态更新逻辑

### 3.6.2 契约测试

- 测试 Agent tool 接口契约
- 测试 `PydanticAI` 适配层契约

### 3.6.3 集成测试

- 测试 Agent 能调用 `rag_search_tool`
- 测试 Agent 能调用 `rag_answer_tool`
- 测试 Agent 多轮对话上下文是否正确
- 测试 Agent 返回内容包含引用
- 测试 Agent trace 可查询

### 3.6.4 回归测试

- 确保增加 Agent 后不影响原有 RAG 页面
- 确保 Agent 未绕过 RAG 服务直接访问底层索引

## 3.7 第二阶段完成标准

- Agent 对话页面可用
- Agent 能调用 RAG 服务
- 多轮对话稳定
- 工具调用过程可见
- 不破坏第一阶段 RAG 功能

## 4. 第三阶段任务：最终产品化

## 4.1 阶段目标

补齐鉴权、权限、观测、评测、版本、发布和运维能力，形成可稳定运行的产品。

## 4.2 产品与功能任务

- 定义用户与角色模型
- 定义多知识库权限模型
- 定义版本发布和回滚流程
- 定义审计范围
- 定义运维与告警需求

## 4.3 后端任务

### 4.3.1 鉴权与权限

- 实现 JWT 登录
- 实现 RBAC
- 限制后台页面权限
- 限制知识库访问权限
- 预留 OIDC / SSO 接入能力

### 4.3.2 版本与发布

- 实现文档版本管理
- 实现索引版本管理
- 实现知识库发布版本
- 实现回滚能力
- 实现灰度发布策略

### 4.3.3 可观测性

- 实现结构化日志
- 接入 OpenTelemetry
- 接入 Langfuse 或 Phoenix
- 实现 request_id 贯穿
- 实现 query trace 记录
- 实现 Agent trace 记录
- 实现错误聚合视图

### 4.3.4 安全与审计

- 实现操作审计日志
- 实现配置脱敏
- 实现文件大小限制
- 实现 MIME 校验
- 实现路径安全校验

### 4.3.5 存储与部署

- 接入对象存储接口
- 支持本地存储与 S3-compatible 切换
- 优化 docker compose
- 编写部署文档
- 编写备份与恢复文档

## 4.4 前端任务

- 增加登录与权限页面
- 增加审计日志查看页面
- 增加版本管理页面
- 增加评测结果查看页面
- 增加系统配置页面

## 4.5 数据与基础设施任务

- 增加对象存储
- 增加观测平台
- 增加评测任务执行能力
- 增加发布与回滚配置

## 4.6 第三阶段测试任务

### 4.6.1 单元测试

- 测试 RBAC 权限判断
- 测试版本切换逻辑
- 测试回滚逻辑
- 测试审计日志写入逻辑

### 4.6.2 集成测试

- 测试登录与权限控制
- 测试多角色访问限制
- 测试版本发布流程
- 测试版本回滚流程
- 测试对象存储读写
- 测试 trace 写入链路

### 4.6.3 评测与回归测试

- 扩展检索与问答评测集
- 建立固定回归评测任务
- 建立发布前评测门禁
- 建立性能基线测试

## 4.7 第三阶段完成标准

- 系统支持多用户与多角色
- 支持版本发布与回滚
- 支持观测和追踪
- 支持审计
- 支持稳定部署和运维

## 5. 横向公共任务

这些任务不属于单一阶段，但应持续推进：

- 维护编码规范
- 维护测试规范
- 维护 API 文档
- 维护 Prompt 与模型配置文档
- 维护评测集
- 维护故障处理手册
- 维护部署文档

## 6. 建议执行顺序

### 第一阶段建议顺序

1. 初始化工程、数据库、Redis、Qdrant、测试骨架
2. 打通上传、任务入队、worker 执行
3. 打通 Docling 解析与 chunk 入库
4. 打通 embedding 和 Qdrant 索引
5. 打通 hybrid retrieval
6. 打通问答生成与引用
7. 完成管理页面和问答页面
8. 补齐测试和评测基线

### 第二阶段建议顺序

1. 接入 `PydanticAI`
2. 实现 `rag_search_tool`
3. 实现 `rag_answer_tool`
4. 打通 Agent 页面
5. 增加 trace 展示
6. 补齐 Agent 测试

### 第三阶段建议顺序

1. 增加 JWT 和 RBAC
2. 增加版本化与回滚
3. 增加观测平台
4. 增加对象存储
5. 建立发布前评测门禁
6. 完善部署与运维文档

## 7. 细化执行 Backlog

本节将三阶段任务进一步细化为：

- Epic：一组有明确产出的主题任务
- Issue：可以独立开发和验收的工作项
- 依赖：开始该任务前的前置条件
- 验收标准：完成后如何判断通过
- 测试点：对应必须补的测试

## 7.1 第一阶段 Backlog

## 7.1.1 Epic A：工程与开发环境初始化

### A-1 初始化后端工程骨架

- 内容
  - 创建后端目录结构
  - 创建 FastAPI 入口
  - 创建基础配置模块
  - 创建日志模块
- 依赖
  - 无
- 验收标准
  - 服务可启动
  - 基础 health check 可访问
- 测试点
  - 启动测试
  - health check API 测试

### A-2 初始化前端工程骨架

- 内容
  - 创建前端工程
  - 配置路由
  - 配置基础布局
  - 配置 API client
- 依赖
  - 无
- 验收标准
  - 前端可启动
  - 至少存在 `RAG` 页面和 `Admin` 页面占位
- 测试点
  - 基础页面渲染测试

### A-3 初始化本地基础设施

- 内容
  - 编写 docker compose
  - 启动 Postgres
  - 启动 Redis
  - 启动 Qdrant
- 依赖
  - 无
- 验收标准
  - 三个服务可启动
  - 本地启动脚本可重复执行
- 测试点
  - 基础连接测试

### A-4 初始化测试框架

- 内容
  - 配置 pytest
  - 配置测试目录结构
  - 配置测试环境变量
  - 添加第一个 smoke test
- 依赖
  - A-1
- 验收标准
  - 测试命令可运行
  - 最小 smoke test 通过
- 测试点
  - smoke test

## 7.1.2 Epic B：数据库与数据模型

### B-1 设计核心表结构

- 内容
  - 设计 knowledge base 相关表
  - 设计 document 相关表
  - 设计 chunk 相关表
  - 设计 query log 表
  - 设计 job log 表
- 依赖
  - A-1
- 验收标准
  - 输出 ER 图或表结构说明
  - 字段能覆盖第一阶段需求
- 测试点
  - schema 评审

### B-2 初始化 Alembic 和首版迁移

- 内容
  - 配置 Alembic
  - 创建首版迁移脚本
  - 执行迁移
- 依赖
  - B-1
- 验收标准
  - 数据库可迁移到最新版本
  - 可重复执行
- 测试点
  - migration 集成测试

### B-3 实现 Repository 基础层

- 内容
  - 创建数据库会话管理
  - 封装基础 Repository
  - 为文档、chunk、job 提供读写接口
- 依赖
  - B-2
- 验收标准
  - Repository 可在 API 和 worker 中复用
- 测试点
  - Repository 单元测试

## 7.1.3 Epic C：文档上传与文档管理

### C-1 实现文档上传接口

- 内容
  - 接收 PDF 上传
  - 保存文件到本地存储
  - 写入文档记录
- 依赖
  - B-3
- 验收标准
  - 可上传 PDF
  - 数据库中生成文档记录
- 测试点
  - 上传 API 集成测试

### C-2 实现文件 hash 去重

- 内容
  - 计算文件 hash
  - 检查重复文件
  - 决定跳过、复用或创建新版本
- 依赖
  - C-1
- 验收标准
  - 重复上传行为符合预期
- 测试点
  - 文件去重单元测试
  - 重复上传集成测试

### C-3 实现文档列表与详情接口

- 内容
  - 查询文档列表
  - 查询文档详情
  - 返回文档状态和任务摘要
- 依赖
  - C-1
- 验收标准
  - 后台可展示文档及状态
- 测试点
  - 列表与详情 API 测试

### C-4 实现文档启用/禁用

- 内容
  - 提供启用/禁用接口
  - 检索链路只使用启用文档
- 依赖
  - C-3
- 验收标准
  - 禁用文档不会被检索命中
- 测试点
  - 文档状态单元测试
  - 检索过滤集成测试

## 7.1.4 Epic D：Redis + RQ 任务系统

### D-1 封装 Redis 连接与 RQ 队列

- 内容
  - 封装 Redis client
  - 封装 RQ queue provider
  - 定义 `ingestion` 和 `indexing` 队列
- 依赖
  - A-3
- 验收标准
  - API 可向指定队列入队
- 测试点
  - 入队单元测试

### D-2 实现 Job 模型与状态同步

- 内容
  - 定义内部 job schema
  - 同步 RQ job 状态到业务层
  - 存储错误信息和重试次数
- 依赖
  - B-3
  - D-1
- 验收标准
  - 后台可读取任务状态
- 测试点
  - 任务状态映射测试

### D-3 实现 Worker 启动入口

- 内容
  - 创建 worker 启动脚本
  - 注册任务函数
  - 配置超时和日志
- 依赖
  - D-1
- 验收标准
  - worker 可独立启动并消费任务
- 测试点
  - worker 启动测试

### D-4 实现失败重试与任务日志

- 内容
  - 支持 retry
  - 记录失败原因
  - 记录处理耗时
- 依赖
  - D-2
  - D-3
- 验收标准
  - 失败任务可重试
  - 可查看失败原因
- 测试点
  - 失败重试测试

## 7.1.5 Epic E：文档解析

### E-1 封装 DoclingParser

- 内容
  - 定义统一解析接口
  - 支持输入文件路径
  - 输出结构化解析结果
- 依赖
  - A-1
- 验收标准
  - 能从单个 PDF 解析出结构化结果
- 测试点
  - parser 契约测试

### E-2 实现解析 profile

- 内容
  - fast
  - balanced
  - accurate
- 依赖
  - E-1
- 验收标准
  - 能按 profile 切换解析参数
- 测试点
  - profile 单元测试

### E-3 实现解析兜底

- 内容
  - 纯文本 PDF 走轻量抽取
  - Docling 失败时回退
- 依赖
  - E-1
- 验收标准
  - 部分失败文档仍可得到最小解析结果
- 测试点
  - fallback 测试

### E-4 接通解析任务

- 内容
  - 上传后自动入队解析
  - worker 执行解析
  - 保存解析产物
- 依赖
  - C-1
  - D-3
  - E-1
- 验收标准
  - 上传文档后能异步完成解析
- 测试点
  - 上传到解析完成集成测试

## 7.1.6 Epic F：文档分类与 Chunk 构建

### F-1 实现文档类型识别器

- 内容
  - 支持 `manual`
  - 支持 `faq`
  - 支持 `qa`
  - 支持 `spec`
  - 支持 `unknown`
- 依赖
  - E-1
- 验收标准
  - 对典型样本文档分类稳定
- 测试点
  - 分类器单元测试

### F-2 实现 Chunker Registry

- 内容
  - 统一 chunker 接口
  - chunker 注册与选择
- 依赖
  - A-1
- 验收标准
  - 可按配置选择 chunk 策略
- 测试点
  - registry 单元测试

### F-3 实现正文 chunker

- 内容
  - `docling_hybrid`
  - `markdown_header`
  - `recursive_token`
- 依赖
  - F-2
  - E-1
- 验收标准
  - 可输出结构合理的正文 chunks
- 测试点
  - chunk 切分单元测试

### F-4 实现表格 chunker

- 内容
  - 表头保留
  - 大表分块
  - metadata 标注
- 依赖
  - F-2
  - E-1
- 验收标准
  - 表格问答场景下 chunk 可用
- 测试点
  - 表格 chunk 单元测试

### F-5 持久化 chunks 并提供预览接口

- 内容
  - 保存 chunk 原文与 metadata
  - 提供 chunk 预览查询
- 依赖
  - B-3
  - F-3
  - F-4
- 验收标准
  - 后台可查看 chunk 列表和详情
- 测试点
  - chunk 持久化测试
  - 预览 API 测试

## 7.1.7 Epic G：Embedding 与 Qdrant 索引

### G-1 封装 EmbeddingProvider

- 内容
  - 定义统一 embedding 接口
  - 接入模型实现
- 依赖
  - A-1
- 验收标准
  - 给定文本可返回向量
- 测试点
  - embedding 契约测试

### G-2 初始化 Qdrant collection

- 内容
  - 创建 collection
  - 定义 payload 结构
  - 定义 dense/sparse 字段
- 依赖
  - A-3
- 验收标准
  - 本地可成功初始化 collection
- 测试点
  - Qdrant 初始化测试

### G-3 实现 chunk 索引写入

- 内容
  - dense 向量写入
  - sparse 表达写入
  - payload 写入
- 依赖
  - G-1
  - G-2
  - F-5
- 验收标准
  - 已解析 chunk 可写入 Qdrant
- 测试点
  - 索引写入集成测试

### G-4 实现索引构建任务

- 内容
  - 将 embed 和 index 放入 `indexing` 队列
  - 构建结束后更新文档状态
- 依赖
  - D-3
  - G-3
- 验收标准
  - 文档可从 chunked 进入 ready
- 测试点
  - 状态流转集成测试

## 7.1.8 Epic H：Hybrid Retrieval

### H-1 实现 dense retrieval

- 内容
  - query embedding
  - dense top-k 查询
- 依赖
  - G-3
- 验收标准
  - 可返回 dense 检索结果
- 测试点
  - dense retrieval 测试

### H-2 实现 sparse retrieval

- 内容
  - 构造 sparse query
  - sparse top-k 查询
- 依赖
  - G-3
- 验收标准
  - 可返回 sparse 检索结果
- 测试点
  - sparse retrieval 测试

### H-3 实现 RRF 融合与去重

- 内容
  - 多路结果融合
  - 去重
  - 截断
- 依赖
  - H-1
  - H-2
- 验收标准
  - 返回统一排序结果
- 测试点
  - RRF 单元测试

### H-4 实现 metadata filter

- 内容
  - 按 kb
  - 按文档状态
  - 按文档类型
  - 按语言
  - 按产品型号
- 依赖
  - H-1
  - H-2
- 验收标准
  - 过滤条件可生效
- 测试点
  - filter 集成测试

## 7.1.9 Epic I：Query 处理、Rerank 与 Answer

### I-1 封装 MiniMaxClient

- 内容
  - 调用 Anthropic-compatible API
  - 支持 query rewrite
  - 支持 answer generation
- 依赖
  - A-1
- 验收标准
  - 能成功调用模型
- 测试点
  - client 契约测试

### I-2 实现 query rewrite 和 expansion

- 内容
  - 标准化 query
  - 输出结构化 rewrite
  - 生成扩充查询
- 依赖
  - I-1
- 验收标准
  - 可返回结构化检索查询
- 测试点
  - rewrite 单元测试

### I-3 实现 retrieval context

- 内容
  - 提取型号、语言、故障码、文档类型
  - 合并近几轮检索上下文
- 依赖
  - I-2
- 验收标准
  - query 上下文可正确继承和覆盖
- 测试点
  - context 合并测试

### I-4 实现可选 reranker

- 内容
  - 统一 rerank 接口
  - lazy load
  - top-n 重排
- 依赖
  - H-3
- 验收标准
  - rerank 可开关
- 测试点
  - rerank 开关测试

### I-5 实现答案生成与引用拼接

- 内容
  - context packing
  - answer generation
  - 引用文档与页码拼接
- 依赖
  - I-1
  - H-4
- 验收标准
  - 回答包含来源引用
- 测试点
  - answer 集成测试

## 7.1.10 Epic J：RAG API

### J-1 实现 `/rag/search`

- 内容
  - 接收 query
  - 执行 retrieval
  - 返回 chunks 和 trace 摘要
- 依赖
  - H-4
  - I-3
- 验收标准
  - API 能稳定返回检索结果
- 测试点
  - search API 测试

### J-2 实现 `/rag/answer`

- 内容
  - 接收 query
  - 走完整 RAG 流程
  - 返回答案和引用
- 依赖
  - I-5
- 验收标准
  - API 返回可展示答案
- 测试点
  - answer API 测试

## 7.1.11 Epic K：第一阶段前端页面

### K-1 管理页面文档列表

- 内容
  - 列表
  - 状态
  - 任务摘要
- 依赖
  - C-3
- 验收标准
  - 可查看文档和状态
- 测试点
  - 页面渲染测试

### K-2 管理页面上传与任务状态

- 内容
  - 上传 PDF
  - 展示任务进度
  - 支持失败重试
- 依赖
  - C-1
  - D-4
- 验收标准
  - 上传后页面可展示状态变化
- 测试点
  - 上传交互测试

### K-3 管理页面 chunk 预览与构建

- 内容
  - chunk 预览
  - 触发索引构建
- 依赖
  - F-5
  - G-4
- 验收标准
  - 可从页面查看 chunk 并触发构建
- 测试点
  - 页面交互测试

### K-4 RAG 问答页面

- 内容
  - 输入问题
  - 显示答案
  - 显示引用
  - 显示命中 chunk
- 依赖
  - J-2
- 验收标准
  - 页面完成一次端到端问答
- 测试点
  - 问答页集成测试

## 7.1.12 Epic L：第一阶段评测与回归

### L-1 建立第一批评测集

- 内容
  - 参数问答
  - 告警码问答
  - 安装维护问答
  - 中英跨语言问答
- 依赖
  - 无
- 验收标准
  - 有可执行评测样本
- 测试点
  - 评测数据格式校验

### L-2 实现评测脚本

- 内容
  - 计算 Hit@K
  - 计算 MRR
  - 统计引用命中率
- 依赖
  - L-1
  - J-1
  - J-2
- 验收标准
  - 可运行评测并输出报告
- 测试点
  - 评测脚本测试

### L-3 建立回归基线

- 内容
  - 保存首版评测结果
  - 约定回归阈值
- 依赖
  - L-2
- 验收标准
  - 后续检索修改可对比基线
- 测试点
  - 基线报告校验

## 7.2 第二阶段 Backlog

## 7.2.1 Epic M：Agent 基础接入

### M-1 集成 PydanticAI

- 内容
  - 安装并封装 PydanticAI
  - 定义 Agent 输入输出 schema
- 依赖
  - 第一阶段完成
- 验收标准
  - Agent 服务可初始化
- 测试点
  - Agent 初始化测试

### M-2 实现 Agent 会话与消息存储

- 内容
  - session
  - messages
  - trace summary
- 依赖
  - M-1
- 验收标准
  - 可持久化会话和消息
- 测试点
  - session Repository 测试

## 7.2.2 Epic N：Agent Tools

### N-1 实现 `rag_search_tool`

- 内容
  - 调用 `/rag/search`
  - 规范化输出
- 依赖
  - J-1
  - M-1
- 验收标准
  - Agent 可调用检索工具
- 测试点
  - tool 契约测试

### N-2 实现 `rag_answer_tool`

- 内容
  - 调用 `/rag/answer`
  - 规范化输出
- 依赖
  - J-2
  - M-1
- 验收标准
  - Agent 可调用问答工具
- 测试点
  - tool 契约测试

### N-3 实现 `document_lookup_tool`

- 内容
  - 查询文档信息
  - 查询知识库状态
- 依赖
  - C-3
  - M-1
- 验收标准
  - Agent 可获取文档状态信息
- 测试点
  - tool 集成测试

## 7.2.3 Epic O：Agent Runtime

### O-1 实现多轮上下文管理

- 内容
  - 会话上下文
  - 工具调用历史
  - 用户最近目标
- 依赖
  - M-2
- 验收标准
  - 多轮对话连续性可用
- 测试点
  - 多轮上下文测试

### O-2 实现工具调用流程

- 内容
  - 调用工具
  - 合并工具结果
  - 生成结构化回复
- 依赖
  - N-1
  - N-2
- 验收标准
  - Agent 能完成至少一次工具调用问答
- 测试点
  - Agent 集成测试

### O-3 实现 Agent trace

- 内容
  - 记录工具调用过程
  - 记录中间状态
- 依赖
  - O-2
- 验收标准
  - 前端可展示 trace
- 测试点
  - trace 测试

## 7.2.4 Epic P：Agent 页面

### P-1 实现对话 UI

- 内容
  - 聊天气泡
  - 输入框
  - 会话列表
- 依赖
  - M-1
- 验收标准
  - 页面可进行多轮对话
- 测试点
  - 页面渲染测试

### P-2 实现工具调用展示

- 内容
  - 展示调用的工具
  - 展示引用来源
  - 展示 trace 折叠面板
- 依赖
  - O-3
- 验收标准
  - 用户可看到工具过程
- 测试点
  - 页面交互测试

## 7.2.5 Epic Q：第二阶段回归测试

### Q-1 补充 Agent 单元与集成测试

- 内容
  - 工具选择
  - 会话上下文
  - 工具结果汇总
- 依赖
  - M-1
  - O-2
- 验收标准
  - Agent 核心链路有测试覆盖
- 测试点
  - 单元测试
  - 集成测试

### Q-2 确保 RAG 功能不回退

- 内容
  - 复跑第一阶段测试
  - 复跑第一阶段评测
- 依赖
  - 第二阶段功能完成
- 验收标准
  - RAG 页面和指标不回退
- 测试点
  - 回归测试
  - 评测测试

## 7.3 第三阶段 Backlog

## 7.3.1 Epic R：鉴权与权限

### R-1 实现登录与 JWT

- 内容
  - 登录
  - token 签发
  - token 校验
- 依赖
  - 第一阶段完成
- 验收标准
  - 登录成功后可访问受保护接口
- 测试点
  - 鉴权测试

### R-2 实现 RBAC

- 内容
  - admin
  - operator
  - user
- 依赖
  - R-1
- 验收标准
  - 不同角色权限生效
- 测试点
  - 权限测试

## 7.3.2 Epic S：版本化与发布

### S-1 实现文档版本管理

- 内容
  - 文档版本
  - 索引版本
  - 发布版本
- 依赖
  - 第一阶段完成
- 验收标准
  - 文档和索引有明确版本
- 测试点
  - 版本模型测试

### S-2 实现回滚机制

- 内容
  - 版本切换
  - 索引回滚
- 依赖
  - S-1
- 验收标准
  - 可回滚到指定版本
- 测试点
  - 回滚测试

## 7.3.3 Epic T：观测与审计

### T-1 接入结构化日志和 OpenTelemetry

- 内容
  - request_id
  - trace_id
  - query trace
  - agent trace
- 依赖
  - 第一阶段完成
- 验收标准
  - 日志和 trace 可关联
- 测试点
  - 观测集成测试

### T-2 接入 Langfuse 或 Phoenix

- 内容
  - LLM trace
  - retrieval trace
- 依赖
  - T-1
- 验收标准
  - 可在观测平台查看链路
- 测试点
  - 平台接入测试

### T-3 实现审计日志

- 内容
  - 管理操作审计
  - 配置变更审计
  - 版本发布审计
- 依赖
  - R-2
- 验收标准
  - 关键操作有审计记录
- 测试点
  - 审计测试

## 7.3.4 Epic U：对象存储与部署

### U-1 接入对象存储抽象

- 内容
  - 本地存储适配
  - S3-compatible 适配
- 依赖
  - 第一阶段完成
- 验收标准
  - 文件存储可切换
- 测试点
  - 存储契约测试

### U-2 完善部署与恢复文档

- 内容
  - 部署步骤
  - 备份
  - 恢复
  - 运维说明
- 依赖
  - U-1
- 验收标准
  - 新环境可按文档部署
- 测试点
  - 演练校验

## 7.3.5 Epic V：发布前评测门禁

### V-1 扩展评测数据集

- 内容
  - 更多产品
  - 更多故障场景
  - 更多跨语言场景
- 依赖
  - L-1
- 验收标准
  - 评测集覆盖主要业务场景
- 测试点
  - 数据集校验

### V-2 建立发布前自动评测

- 内容
  - 运行固定评测任务
  - 对比基线
  - 失败即阻断发布
- 依赖
  - V-1
  - L-3
- 验收标准
  - 评测可作为门禁
- 测试点
  - 评测流水线测试

## 8. 第一阶段建议拆分为首批 Issue

如果马上开始开发，优先创建以下 12 个 Issue：

1. 初始化后端工程、配置和 health check
2. 初始化前端工程和基础页面
3. 初始化 Postgres/Redis/Qdrant/docker compose
4. 初始化 pytest、测试目录和 smoke test
5. 设计数据库表并完成首版迁移
6. 实现文档上传接口和本地文件保存
7. 实现 Redis + RQ 入队和 worker 启动
8. 封装 DoclingParser 并打通上传后自动解析
9. 实现 Chunker Registry 和 chunk 持久化
10. 实现 embedding、Qdrant collection 和索引写入
11. 实现 hybrid retrieval、query rewrite 和 `/rag/search`
12. 实现 `/rag/answer`、RAG 页面和后台管理页面初版
