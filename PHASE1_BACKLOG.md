# 第一阶段 Backlog

第一阶段功能已交付，以下是联调过程中发现的优化项和遗留问题。

---

## 高优先级

### 1. 错误信息透传到 JobLog

**现状**：Worker 解析/索引失败时，`document.status` 设为 failed，但 `job_logs.error_message` 没有写入具体错误原因。前端只能看到"失败"，不知道为什么失败。

**改进**：`run_ingestion` / `run_indexing` 在 catch 异常后，通过同步 session 更新对应 JobLog 的 `error_message` 和 `status`。

### 2. 处理进度展示

**现状**：前端只能看到状态标签（已上传/解析中/已切块/索引中/就绪），没有进度信息。大文档解析可能需要几分钟，用户不知道进展。

**改进**：
- JobLog 表加 `progress` 字段（0-100）
- Worker 在解析/chunk/embedding 各阶段更新 progress
- 前端轮询或 WebSocket 展示进度条

### 3. Alembic 迁移验证

**现状**：迁移文件是手写的，没有用 `alembic revision --autogenerate` 对比过真实数据库 schema，可能有字段类型或约束遗漏。

**改进**：连接 Postgres 后跑一次 autogenerate，对比差异并修正。

### 4. 切分逻辑优化

**现状**：docling_hybrid chunker 按 segment 顺序线性拼接，没有利用 Docling 输出的文档结构树（标题层级、列表嵌套、段落从属关系）。切分边界可能不够语义化。

**改进**：
- 利用 Docling 的 `iterate_items()` 返回的 level 信息构建结构树
- 按结构树的节点边界切分，保证每个 chunk 是语义完整的段落/小节
- 跨节点时优先在高层级标题处断开

---

## 中优先级

### 5. Worker 单线程瓶颈

**现状**：macOS 上用 SimpleWorker（不 fork），一次只能处理一个任务。大文档解析时后续任务排队等待。

**改进**：
- 生产环境（Linux）使用标准 Worker（fork 模式），可启动多个 Worker 实例
- 或改用 `rq worker --burst` + supervisor 管理多进程

### 6. 文件存储路径耦合

**现状**：uvicorn 和 Worker 的工作目录不一致导致 `var/` 路径不同，当前通过 `.env` 配置绝对路径解决，不够优雅。

**改进**：`config.py` 中 `upload_dir` / `parsed_dir` 始终解析为绝对路径（基于 `ROOT_DIR`），不依赖 `.env` 中是否配了绝对路径。

### 7. 批量操作

**现状**：PRD 要求批量上传、批量重建索引、批量启用/禁用，当前只支持单文件操作。

**改进**：
- 前端支持多文件拖拽上传
- 后端 `POST /documents/batch_upload` 接受多文件
- `POST /kb/{kb_id}/build` 已支持批量索引重建（已实现）
- 增加 `POST /documents/batch_enable` / `batch_disable`

### 8. 文档版本清理

**现状**：重新解析同一文档会创建新的 DocumentVersion，但旧 version 的 chunks 没有清理，导致 chunk 预览可能显示多个版本的混合结果。

**改进**：创建新 version 前，删除旧 version 的 chunks（`ChunkRepository.delete_by_document_version` 已实现，只需在 ingestion_task 中调用）。

### 9. 复杂图文解析 OCR

**现状**：
- fast profile 关闭了 OCR，扫描件和图片中的文字会丢失
- accurate profile 开启了 OCR 但解析速度很慢
- 没有对 OCR 效果做评估

**改进**：
- 评估 balanced profile 下 OCR 的效果和性能
- 考虑对扫描件自动切换到 accurate profile
- 图片 caption 提取（当前未实现）

### 10. 单元测试覆盖率

**现状**：437 个测试全部通过，但没有跑过覆盖率统计。核心链路（ingestion_task、indexing）的测试大量使用 mock，缺少真实 PDF 的集成测试。

**改进**：
- 跑 `pytest --cov` 统计覆盖率，目标 >70%
- 补充 2-3 个真实 PDF 的集成测试（标记 `@pytest.mark.integration`）
- 补充端到端测试：上传 → 解析 → chunk → 索引 → 检索

---

## 低优先级

### 11. Chunk 预览分页 total 不准

**现状**：`GET /documents/{id}/chunks` 的 `total` 字段返回的是当前页数量（`len(items)`），不是总数。

**改进**：加 COUNT 查询，与其他列表接口保持一致。

### 12. 前端体验优化

- 知识库统计卡片：当前逐个请求 KB 详情获取统计，KB 多时请求量大
- 文档列表：缺少按文档类型筛选
- 检索调试：结果高亮不够精确（按空格分词，中文分词不准）
- 上传反馈：缺少上传进度条（大文件时）

---

## 留到第二阶段

### 13. Sparse Embedding

**现状**：TEI 的 BGE-M3 不支持 `/embed_sparse` 端点，当前降级为纯 dense search，sparse search 路径为空。

**二阶段方案**：
- 方案 A：用 FlagEmbedding 库本地加载 BGE-M3，`model.encode()` 一次拿 dense + sparse
- 方案 B：自建 embedding HTTP 服务（FastAPI 包一层 BGE-M3）
- 方案 C：等 TEI 新版本支持

### 14. Rerank

**现状**：检索调试只有 RRF 融合，没有 rerank。PRD 二阶段要求 TEI Reranker（默认关闭，按需开启）。

### 15. Query Rewrite

**现状**：检索调试直接用原始 query 搜索，没有 query 改写和扩展。PRD 二阶段要求 MiniMax 做 query rewrite。

---

## 已修复的问题（联调期间）

| 问题 | 修复 commit |
|------|------------|
| InMemoryJobQueue 未推送到 Redis | 应用启动时初始化 RQJobQueue |
| macOS Worker fork 崩溃 | 使用 SimpleWorker |
| 前端上传无反应 | Dragger 改用 customRequest |
| uvicorn/Worker 路径不一致 | .env 使用绝对路径 |
| DoclingParser per-page 文本是对象 repr | 修复为 export_to_markdown() |
| Chunk 页码全为 NULL（文本匹配失败） | 改为 ContentSegment 精确归属 |
| PDF 预览中文文件名 500 | Content-Disposition 用 RFC 5987 编码 |
| TEI sparse 端点不可用导致 indexing 失败 | 捕获所有异常降级为空 sparse |
| pyproject.toml 缺少 aiofiles/filetype | 补充显式依赖 |
| 列表接口 total 返回页内数量 | 加 COUNT 查询 |
