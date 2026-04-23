# 第二阶段 Backlog

开发过程中发现的优化项和遗留问题。

---

## 已修复的问题（联调期间）

| 问题 | 修复 |
|------|------|
| ROOT_DIR 路径错误（拆分后多了 common/ 层） | parents[2] → parents[3] |
| .env 读不到导致 embedding model_path 为空 | 同上 |
| indexing 自动入队时没创建 JobLog | 入队后同步创建 JobLog 记录 |
| 文档删除为软删除，唯一约束导致无法重传 | 改为硬删除 + CASCADE |
| 删除后本地文件残留（只删文件不删目录） | 改为 rmtree 删整个 doc_id 目录 |
| chunk 预览 total 返回当前页数量而非总数 | 加 COUNT 查询 |
| chunk 预览只加载前 100 条不能翻页 | 分页加载，每页 20 条 |
| chunked 状态没有 Spin 动画 | 加入中间状态列表 |
| 进度条看不到（任务太快） | 改用 Spin 动画 + 1.5 秒轮询 |
| Alembic 迁移缺失（progress + rag_configs） | 补充 002 迁移文件 |
| README 启动顺序和路径错误 | 统一 backend/ 目录，修正 venv 和前端路径 |
| FlagEmbedding 与 transformers 版本不兼容 | 锁定 transformers<4.50 |
| 测试文件 create_app 引用失效 | 改用 create_knowledge_app(settings=testing) |
| query rewrite fallback 把 LLM 回答当成 query | 改为纯文本模式，清理 think 标签，超长降级用原始 query |
| ContextExtractor 自动加 language filter 导致检索为空 | 不再自动应用 context filter，只用显式 filters |
| RRF score 阈值 0.3 过高，所有结果被过滤 | 降到 0.01（RRF 分数范围本身在 0.01-0.05） |
| MiniMax think 标签显示在前端 | 流式输出和最终渲染都过滤 `<think>` 内容 |
| 答案显示原始 Markdown 符号 | 使用 react-markdown + remark-gfm 渲染 |
| Markdown 表格不渲染 | 添加 remark-gfm 插件 |
| 参考来源与答案引用编号不一致 | 改为 LLM 在答案末尾自行输出参考资料，去掉前端折叠面板 |
| 不相关的低分结果进入 context 和 citations | rerank 后过滤 score < 0.01 的结果 |
| embedding 和 reranker 每次请求重新加载模型 | 改为模块级单例，模型只加载一次 |
| 首次请求慢（等模型加载） | RAG 服务启动时预加载 embedding + reranker |
| rerank 候选数 20 太多导致慢 | 降到 10 |
| MiniMax API 端点格式不对（anthropic vs openai） | 文档说明用 OpenAI 兼容端点 /v1 |
| system prompt 中文引号导致 SyntaxError | 改为单引号 |
| SSE trace 事件只发 hits 字段 | 改为发送完整 trace（dense_hits/sparse_hits/returned 等） |
| answer_top_k=3 漏掉相关结果 | 改回 5 |

---

## 待优化

### 1. Query Rewrite 同义扩充增加召回

**现状**：当前 query rewrite 已关闭（MiniMax 不遵守改写格式）。即使开启，也只做单次改写，没有同义词扩展。

**改进**：
- 换用更遵守指令的模型，或优化 prompt
- 在 rewrite 阶段输出同义词扩展，利用 sparse retrieval 增加召回
- 评估扩充后对 Hit@K 和 MRR 的影响

### 2. `rag_context_window_tokens` 未使用

**现状**：配置项已定义但 context packing 时没有做 token 截断。

**改进**：在 `_pack_context()` 中按 token 预算截断，避免超出 LLM 上下文窗口。

### 3. `previous_context` API 未暴露

**现状**：`RAGService.search()` 支持 `previous_context` 参数，但 HTTP API 没有暴露。Phase 2 前端是单轮问答不需要，Phase 3 Agent 接入时需要。

**改进**：Phase 3 时在 API 加可选字段，或 Agent 直接调 Python 接口。

### 4. RAG 服务单元测试

**现状**：RAG 服务核心逻辑（query 处理、RRF 融合、拒答策略）没有单元测试。

**改进**：补充 `tests/unit/test_rag_service.py`、`test_query_normalizer.py`、`test_context_extractor.py`。

### 5. System Prompt 硬编码

**现状**：答案生成的 system prompt 写在 `RAGService._build_answer_messages()` 里，不方便调整。

**改进**：抽到 `app/rag/generation/prompts.py`，支持配置化或模板化。

### 6. Docker Compose 缺少 Langfuse

**现状**：Langfuse 服务未加入 docker-compose.yml。

**改进**：添加 Langfuse 服务配置，或文档说明外部部署方式。

### 7. 文档类型分类不准确

**现状**：规则分类器把英文手册错误识别为 `spec`。

**改进**：调整分类优先级，增加英文手册关键词，或引入 LLM 辅助分类。

### 8. RAG 问答页缺少过滤条件

**现状**：RAG 问答页只有知识库选择，没有过滤条件。自动 filter 已关闭。

**改进**：先补全 chunk 元数据（language、product_model），然后加过滤条件选择器。

### 9. Chunk 元数据不完整

**现状**：chunks 的 `language` 和 `product_model` 字段大多为 null，导致 metadata filter 无法使用。

**改进**：在 ingestion 阶段自动填充 language（基于内容检测）和 product_model（基于文档名/内容提取）。

### 10. Langfuse trace 未接入 RAG 链路

**现状**：`RAGTrace` 类已实现但没有在 `RAGService` 中调用。

**改进**：在 search/answer 流程中接入 trace，记录各步骤耗时和中间结果。
