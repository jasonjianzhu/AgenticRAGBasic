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
| chunk 预览 total 返回当前页数量而非总数 | 加 COUNT 查询（Backlog #11） |
| chunk 预览只加载前 100 条不能翻页 | 分页加载，每页 20 条 |
| chunked 状态没有 Spin 动画 | 加入中间状态列表 |
| 进度条看不到（任务太快） | 改用 Spin 动画 + 1.5 秒轮询 |
| Alembic 迁移缺失（progress + rag_configs） | 补充 002 迁移文件 |
| README 启动顺序和路径错误 | 统一 backend/ 目录，修正 venv 和前端路径 |
| FlagEmbedding 与 transformers 版本不兼容 | 锁定 transformers<4.50 |
| 测试文件 create_app 引用失效 | 改用 create_knowledge_app(settings=testing) |

---

## 待优化

### 1. Query Rewrite 同义扩充增加召回

**现状**：当前 query rewrite 只做了改写和关键词提取，改写后的 query 用于单次 embedding 检索。

**改进**：
- 在 rewrite 阶段让 LLM 输出同义词/近义词扩展（如"过温" → "温度过高"、"高温告警"、"overtemperature"）
- 用扩展后的多个 query 分别做 embedding 检索，合并结果
- 或者将扩展关键词拼接到 rewritten_query 中，利用 sparse retrieval 的词汇匹配能力增加召回
- 评估扩充后对 Hit@K 和 MRR 的影响

### 2. `rag_context_window_tokens` 未使用

**现状**：配置项已定义但 context packing 时没有做 token 截断。

**改进**：在 `_pack_context()` 中按 token 预算截断，避免超出 LLM 上下文窗口。

### 3. `previous_context` API 未暴露

**现状**：`RAGService.search()` 支持 `previous_context` 参数，但 HTTP API 没有暴露。Phase 2 前端是单轮问答不需要，Phase 3 Agent 接入时需要。

**改进**：Phase 3 时在 API 加可选字段，或 Agent 直接调 Python 接口。

### 4. RAG 服务单元测试

**现状**：RAG 服务核心逻辑（query 处理、RRF 融合、引用拼接、拒答策略）没有单元测试。

**改进**：补充 `tests/unit/test_rag_service.py`、`test_query_normalizer.py`、`test_query_rewriter.py`、`test_context_extractor.py`。

### 5. System Prompt 硬编码

**现状**：答案生成的 system prompt 写在 `RAGService._build_answer_messages()` 里，不方便调整。

**改进**：抽到 `app/rag/generation/prompts.py`，支持配置化或模板化。

### 6. Docker Compose 缺少 Langfuse

**现状**：Langfuse 服务未加入 docker-compose.yml。

**改进**：添加 Langfuse 服务配置，或文档说明外部部署方式。

### 7. 文档类型分类不准确

**现状**：规则分类器把英文手册（如 "Jinko 5MWh liquid-cooled ESS User Manual"、"JKS-215KLAA User Manual"）错误识别为 `spec`。原因是 `spec` 关键词 `specification` 的优先级高于 `manual` 关键词 `user manual`，而这些文档内容中可能包含 specification 相关词汇。

**改进**：
- 调整分类优先级：`manual` 关键词匹配应优先于 `spec`
- 增加英文手册关键词覆盖（"User Manual"、"Operation Manual" 等）
- 考虑文件名权重高于内容匹配
- 或引入 LLM 辅助分类替代纯规则

### 8. RAG 问答页缺少过滤条件

**现状**：RAG 问答页只有知识库选择，没有 document_type / language / product_model 过滤条件。自动 filter 已关闭（chunk 元数据不完整会导致误过滤）。

**改进**：
- 先补全 chunk 元数据（language、product_model 在 ingestion 阶段填充）
- 然后在 RAG 问答页加过滤条件选择器
- 或重新启用自动 filter（基于 context 提取）

### 9. LLM 引用编号与 citation 不一致

**现状**：后端 context packing 用 [1] [2] [3] 编号传给 LLM，citation 列表也用相同编号。但 MiniMax 生成答案时可能不遵守编号规则（自己编号或不标注引用），导致前端显示的引用来源和答案中的 [n] 对不上。

**改进**：
- 优化 system prompt，更强调引用格式要求
- 或后端在生成完成后做引用对齐（解析答案中的 [n]，映射到实际 citation）
- 或换用更遵守指令的模型
