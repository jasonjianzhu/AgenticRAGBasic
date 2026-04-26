# 第四阶段任务：产品化与生产就绪

## 概述

第四阶段目标是将 AgenticRAG 从开发/测试状态提升到生产就绪。按优先级分为 6 个里程碑（M7-M12），建议按顺序推进，安全和可靠性优先。

---

## M7：安全加固

### T7.1 JWT 认证

- [ ] 用户表设计（users: id, username, email, password_hash, role, is_active）
- [ ] 注册/登录 API（`POST /auth/register`, `POST /auth/login`）
- [ ] JWT access token + refresh token 签发
- [ ] FastAPI 依赖注入 `get_current_user`，所有 API 加认证
- [ ] token 过期和刷新机制
- [ ] Alembic 迁移文件

### T7.2 RBAC 权限控制

- [ ] 角色定义：admin（全部权限）、operator（知识库管理）、user（问答）
- [ ] 权限装饰器 `require_role("admin")`
- [ ] 管理后台 API 限制 admin/operator
- [ ] Agent 会话按 user_id 隔离
- [ ] 知识库访问权限（知识库绑定可访问角色列表）
- [ ] 前端登录页面 + token 管理 + 角色路由守卫

### T7.3 API 安全

- [ ] CORS 配置改为环境变量控制，生产环境限制为前端域名
- [ ] Rate Limiting 中间件（基于 Redis 滑动窗口）
  - 全局：100 req/min
  - 用户级 Agent 对话：10 req/min
  - 用户级 RAG 问答：20 req/min
- [ ] LLM API Key 从 `.env` 迁移到环境变量注入（Docker secrets / K8s secrets）
- [ ] SQL 注入防护加固：补充注释绕过（`--`, `/**/`）检测

### T7.4 审计日志

- [ ] 审计日志表设计（audit_logs: id, user_id, action, resource_type, resource_id, details, ip, created_at）
- [ ] 关键操作自动记录：知识库创建/删除、文档上传/删除、配置变更
- [ ] 审计日志查询 API（admin 可用）
- [ ] Alembic 迁移文件

---

## M8：可靠性

### T8.1 健康检查

- [ ] `GET /health` 接口检查 PostgreSQL、Qdrant、Redis 连通性
- [ ] `GET /health/ready` 检查模型加载状态
- [ ] 依赖不可用时返回 503 + 具体不可用组件
- [ ] LLM API 连通性检查（轻量 ping）

### T8.2 数据一致性

- [ ] 定时任务：对比 PostgreSQL chunks 表和 Qdrant points 数量
- [ ] 检测孤立向量点（Qdrant 有但 PostgreSQL 没有）→ 自动清理
- [ ] 检测缺失向量点（PostgreSQL 有但 Qdrant 没有）→ 自动重建
- [ ] 一致性检查 API（admin 手动触发）
- [ ] 文档删除改为：先删 Qdrant → 成功后删 PostgreSQL，失败时回滚

### T8.3 LLM 重试与熔断

- [ ] MiniMax client 增加指数退避重试（最多 3 次，间隔 1s/2s/4s）
- [ ] 连续 5 次失败触发熔断（30 秒内直接返回错误）
- [ ] 熔断状态下的降级响应（"AI 服务暂时不可用，请稍后重试"）
- [ ] 熔断恢复：30 秒后半开状态，放行 1 个请求探测

### T8.4 优雅停机

- [ ] uvicorn SIGTERM 处理：等待当前 SSE 流完成（最多 30 秒）
- [ ] Worker 优雅停机：完成当前任务后退出
- [ ] 数据库连接池 dispose

---

## M9：可观测性

### T9.1 HTTP 请求日志

- [ ] 纯 ASGI 中间件实现请求日志（不用 BaseHTTPMiddleware）
- [ ] 记录 method、path、status、duration_ms、request_id
- [ ] request_id 绑定 structlog contextvars，贯穿全链路
- [ ] SSE 流式响应兼容

### T9.2 Prometheus Metrics

- [ ] 集成 `prometheus-fastapi-instrumentator` 或自定义 metrics
- [ ] 请求指标：QPS、延迟 P50/P95/P99、错误率（按路径分组）
- [ ] LLM 指标：调用次数、耗时、token 消耗、失败率
- [ ] RAG 指标：检索耗时、命中数、rerank 耗时
- [ ] Worker 指标：队列深度、任务耗时、失败率
- [ ] `/metrics` 端点暴露

### T9.3 OpenTelemetry + Langfuse

- [ ] OpenTelemetry SDK 集成，trace 贯穿 HTTP → Agent → RAG → LLM → Qdrant
- [ ] Langfuse 接入：LLM 调用链路可视化
- [ ] prompt 版本管理（通过 Langfuse）
- [ ] 成本追踪（token 消耗 × 单价）

---

## M10：部署运维

### T10.1 容器化

- [ ] `backend/Dockerfile`（多阶段构建，分离依赖安装和代码复制）
- [ ] `frontend/Dockerfile`（Node 构建 + Nginx 静态服务）
- [ ] `worker/Dockerfile`（复用 backend 镜像，不同 entrypoint）
- [ ] `docker-compose.yml`（PostgreSQL + Qdrant + Redis + MinIO + backend + frontend + worker）
- [ ] `docker-compose.dev.yml`（开发环境，挂载代码目录）
- [ ] `.dockerignore` 优化镜像体积

### T10.2 MinIO 对象存储

- [ ] `MinIOStorage` 实现 `StorageBackend` 接口
- [ ] 配置项：`STORAGE_PROVIDER=minio`、`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_BUCKET`
- [ ] 上传文件、解析产物、导出数据统一存入 MinIO
- [ ] 本地存储和 MinIO 通过配置切换，代码无感知

### T10.3 备份与恢复

- [ ] PostgreSQL 备份脚本（pg_dump，每日执行，保留 7 天）
- [ ] MinIO bucket 版本控制开启
- [ ] Qdrant snapshot 定期备份（可选，可从 PostgreSQL 重建）
- [ ] 恢复演练文档（从备份恢复 PostgreSQL + 重建 Qdrant 索引的完整步骤）
- [ ] 至少完成一次恢复演练并记录结果

### T10.4 CI/CD

- [ ] GitHub Actions / GitLab CI 配置
- [ ] 自动运行单元测试 + lint
- [ ] 自动构建 Docker 镜像并推送到 registry
- [ ] 测试环境自动部署
- [ ] 生产环境手动审批部署

### T10.5 进程管理

- [ ] systemd service 文件（knowledge/rag/agent/worker 各一个）
- [ ] 或 K8s Deployment + Service 配置
- [ ] 进程挂掉自动重启
- [ ] Worker 多实例部署配置

---

## M11：数据质量

### T11.1 文档质量校验

- [ ] 解析后检查：chunk 数量 > 0、平均内容长度 > 50 字符、非空比例 > 80%
- [ ] 乱码检测：中文字符比例异常低的 chunk 标记为可疑
- [ ] 质量不达标时文档状态设为 `low_quality`，前端黄色警告提示
- [ ] 扫描件检测（chunk 内容为空或极短）→ 提示用户使用 accurate profile 重新解析

### T11.2 Chunk 元数据补全

- [ ] 语言检测：基于 chunk 内容自动填充 `language` 字段（zh/en/mixed）
- [ ] 产品型号提取：基于文档名和内容正则匹配填充 `product_model`
- [ ] 在 ingestion 阶段自动执行，不需要用户手动操作
- [ ] 已有文档支持批量补全（管理 API）

### T11.3 Query 归一化增强

- [ ] 简繁转换（`opencc` 库）
- [ ] 单位归一化映射表（kW↔千瓦、V↔伏特、Ah↔安时、kWh↔千瓦时）
- [ ] 储能行业中英文术语同义词表（BMS↔电池管理系统、PCS↔储能变流器、SOC↔荷电状态）
- [ ] 评估归一化对 Hit@K 的影响（A/B 测试）

### T11.4 Context Token 截断

- [ ] `_pack_context()` 方法增加 token 计数
- [ ] 按 `rag_context_window_tokens` 配置截断
- [ ] 截断策略：按 rerank score 降序保留，低分 chunk 优先丢弃
- [ ] 截断时记录日志（被丢弃的 chunk 数量）

---

## M12：功能完善

### T12.1 用户反馈

- [ ] 反馈表设计（feedbacks: id, user_id, session_id, message_id, rating, comment, created_at）
- [ ] `POST /agent/messages/{message_id}/feedback` API
- [ ] 前端回答气泡增加 👍/👎 按钮
- [ ] 管理后台反馈统计面板（好评率、差评分布）
- [ ] Alembic 迁移文件

### T12.2 批量操作

- [ ] 前端多文件拖拽上传
- [ ] `POST /documents/batch_upload` 接受多文件
- [ ] `POST /documents/batch_delete` 批量删除
- [ ] `POST /documents/batch_enable` / `batch_disable` 批量启用/禁用
- [ ] `POST /kb/{kb_id}/rebuild` 知识库级别索引重建（已有，验证）

### T12.3 导出功能

- [ ] `GET /agent/sessions/{session_id}/export?format=json|markdown` 对话导出
- [ ] `POST /agent/db/export` SQL 查询结果导出（CSV）
- [ ] 前端导出按钮（对话页 + 数据表格）

### T12.4 版本管理 UI

- [ ] 文档版本列表页面（查看历史版本、对比 chunk 差异）
- [ ] 版本回滚操作（恢复到指定版本的 chunk 和索引）
- [ ] 知识库快照（保存当前所有文档版本状态）

### T12.5 评测体系

- [ ] 评测数据集格式定义（query + expected_chunks + expected_answer）
- [ ] 评测脚本：批量运行 query，计算 Hit@K、MRR
- [ ] Groundedness 评测：检查回答是否基于检索内容
- [ ] 拒答准确率：知识库无答案时是否正确拒答
- [ ] 评测结果持久化，支持版本间对比
- [ ] 储能行业评测集（至少 50 条 query）

---

## 优先级与依赖关系

```
M7（安全）→ M8（可靠性）→ M9（可观测性）
                ↓
            M10（部署运维）→ M11（数据质量）→ M12（功能完善）
```

- M7 最先做：没有认证的系统不能上生产
- M8 依赖 M7：限流需要用户身份
- M9 可与 M8 并行
- M10 依赖 M7/M8：容器化需要安全配置就绪
- M11/M12 可在部署后持续迭代
