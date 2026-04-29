# Agent 防幻觉/编造方案设计

## 文档信息

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-04-29 | 初始版本，基于调研和现状分析 |

---

## 1. 问题分类

Agent 的编造/幻觉问题按场景分为三类，每类的根因和解法不同：

| 场景 | 典型表现 | 根因 | 严重程度 |
|------|----------|------|----------|
| **SQL 数据分析** | 编造数值、错误计算、张冠李戴 | 模型看不到完整数据；Schema 信息不足；模型自行计算 | 🔴 高 |
| **RAG 知识问答** | 用自身知识补充、过度推断 | 检索结果不够时模型"发挥"；prompt 约束被忽略 | 🟡 中 |
| **通用/闲聊** | 偶尔编造不存在的功能或参数 | 模型通病，低频 | 🟢 低 |

**核心原则：分场景治理，SQL 场景投入最大，不做通用 harness。**

---

## 2. SQL 场景：多层防线方案

SQL 场景是编造的重灾区。方案采用 5 层防线，每层解决一个具体问题：

```
用户问题
  ↓
① Schema 语义增强（启动时加载，注入 prompt）
  ↓
② SQL 生成 + Few-shot 示例引导
  ↓
③ Dry-Run 预检（EXPLAIN，不执行）
  ↓
④ 执行 + 完整数据分层返回给 LLM
  ↓
⑤ 回答数值确定性校验（代码层）
  ↓
最终回答
```

### 2.1 第①层：Schema 语义增强

**现状问题：** `schema_loader.py` 只给了表名、字段名、类型、注释。模型不知道 `alarm_level` 有哪些可选值，`metric_name` 有哪些指标，就会猜测。

**方案：** 启动时自动加载枚举值、表间关系、数据范围，注入 system prompt。

**实现要点：**

```python
# schema_loader.py 增强

async def _load_enum_values(self, session, table_name: str, column_name: str, limit: int = 20) -> list[str]:
    """对关键字段自动获取枚举值"""
    result = await session.execute(text(
        f"SELECT DISTINCT {column_name} FROM {table_name} "
        f"WHERE {column_name} IS NOT NULL LIMIT :limit"
    ), {"limit": limit})
    return [str(row[0]) for row in result]

# 对以下类型的字段自动获取枚举值：
# - 名称中包含 status, type, level, category, code, name 的字段
# - 类型为 varchar/text 且 distinct count < 50 的字段
```

**Prompt 注入格式：**

```markdown
### alarms -- 告警记录

| 字段 | 类型 | 说明 | 可选值 |
|------|------|------|--------|
| alarm_level | varchar | 告警级别 | critical, major, minor, warning |
| alarm_code | varchar | 告警代码 | E001, E002, E003, E004, E005 |

### 表间关系
- alarms.device_id → devices.id（设备告警关联）
- device_metrics.device_id → devices.id（设备指标关联）
- maintenance_logs.device_id → devices.id（维护记录关联）
```

**优先级：P0**
**复杂度：中**
**预期效果：减少 SQL 生成中的字段名/值猜测错误**

---

### 2.2 第②层：Few-shot 查询示例

**现状问题：** 模型从零写 SQL，没有参考。对于复杂 JOIN、时间范围过滤、聚合方式容易出错。

**方案：** 在 system prompt 中注入 3-5 个高质量的 (问题, SQL) 示例对。

**示例格式：**

```markdown
## SQL 查询示例

用户问: "最近7天各站点的告警数量统计"
SQL:
SELECT d.site_name, COUNT(*) as alarm_count
FROM alarms a JOIN devices d ON a.device_id = d.id
WHERE a.occurred_at >= NOW() - INTERVAL '7 days'
GROUP BY d.site_name ORDER BY alarm_count DESC

用户问: "查一下设备A最近的运行温度"
SQL:
SELECT recorded_at, metric_value
FROM device_metrics
WHERE device_id = (SELECT id FROM devices WHERE device_name = '设备A')
  AND metric_name = 'temperature'
ORDER BY recorded_at DESC LIMIT 50
```

**管理方式：**
- 初期硬编码在 prompts.py 中（3-5 个覆盖高频场景）
- 中期从配置文件加载，支持运营人员维护
- 长期通过用户反馈积累"golden dataset"（第四阶段）

**优先级：P0**
**复杂度：低**
**预期效果：高频查询场景 SQL 准确率显著提升**

---

### 2.3 第③层：SQL Dry-Run 预检

**现状问题：** SQL 生成后直接执行。如果表名/字段名写错，报错信息返回给用户，但模型没有机会自纠。

**方案：** 执行前先用 `EXPLAIN` 做 dry-run，如果报错则把错误信息反馈给模型重新生成。

**实现要点：**

```python
# sql/validator.py 增加 dry_run 方法

async def dry_run(self, sql: str, executor: SQLExecutor) -> str | None:
    """用 EXPLAIN 预检 SQL，返回错误信息或 None（通过）"""
    try:
        await executor.execute(f"EXPLAIN {sql}")
        return None  # 通过
    except Exception as e:
        return str(e)  # 返回错误信息
```

**Agent 工具层集成：**

```python
# agent.py sql_query 工具中
safe_sql = deps.sql_validator.validate_and_rewrite(sql)

# Dry-run 预检
error = await deps.sql_validator.dry_run(safe_sql, deps.sql_executor)
if error:
    # 返回错误信息让模型自纠，而不是直接报错给用户
    return f"SQL 预检失败: {error}\n请根据错误信息修正 SQL 后重试。"

# 预检通过，执行查询
columns, rows, row_count = await deps.sql_executor.execute(safe_sql)
```

**约束：** 最多重试 1 次（由 PydanticAI 的 retries=2 控制），避免无限循环。

**优先级：P1**
**复杂度：中**
**预期效果：拦截表名/字段名错误，给模型自纠机会**

---

### 2.4 第④层：完整数据分层返回

**现状问题：** `SQLQueryOutput.to_text()` 只返回 3 行示例数据，模型看不到完整数据就"脑补"剩余内容。这是 SQL 场景编造的最大根因。

**方案：** 根据查询结果行数分层返回，确保模型有足够信息正确回答。

**分层策略：**

| 结果行数 | 策略 | 返回内容 |
|----------|------|----------|
| 0 行 | 空结果 | "查询无结果。请告知用户暂无相关数据，不要编造任何数据。" |
| 1-30 行 | 全量返回 | 完整 Markdown 表格 + closing instruction |
| 31-200 行 | 摘要+统计 | 前 20 行明细 + 代码计算的统计摘要（分布、计数、min/max/avg） |
| 200+ 行 | 统计为主 | 前 10 行明细 + 详细统计摘要 + 提示"如需更精确统计请用 SQL 聚合" |

**实现要点：**

```python
# tools/sql_query.py

CLOSING_INSTRUCTION = (
    "\n\n以上是完整查询结果。请严格基于这些数据回答，不要编造任何不在结果中的数值。"
    "如需统计分析（求和、平均、计数等），请用 SQL 聚合函数重新查询，不要手动计算。"
)

def to_text(self) -> str:
    if self.error:
        return f"查询失败: {self.error}"
    if not self.rows:
        return "查询无结果。请告知用户暂无相关数据，不要编造任何数据。"

    if self.row_count <= 30:
        return self._full_table() + CLOSING_INSTRUCTION
    else:
        return self._summary_with_stats() + CLOSING_INSTRUCTION

def _full_table(self) -> str:
    """全量返回 Markdown 表格"""
    lines = [f"查询到 {self.row_count} 条记录:\n"]
    lines.append("| " + " | ".join(self.columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(self.columns)) + " |")
    for row in self.rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)

def _summary_with_stats(self) -> str:
    """前 N 行 + 统计摘要"""
    show_rows = 20 if self.row_count <= 200 else 10
    lines = [f"查询到 {self.row_count} 条记录:\n"]

    # 前 N 行明细
    lines.append("| " + " | ".join(self.columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(self.columns)) + " |")
    for row in self.rows[:show_rows]:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    lines.append(f"\n（以上展示前 {show_rows} 行，共 {self.row_count} 行）\n")

    # 统计摘要（代码计算，不是模型计算）
    lines.append("统计摘要:")
    for i, col in enumerate(self.columns):
        values = [row[i] for row in self.rows if row[i] is not None]
        numeric_values = [v for v in values if isinstance(v, (int, float))]
        if numeric_values:
            lines.append(
                f"- {col}: min={min(numeric_values)}, max={max(numeric_values)}, "
                f"avg={sum(numeric_values)/len(numeric_values):.2f}, count={len(numeric_values)}"
            )
        elif values:
            # 分类字段：统计分布
            from collections import Counter
            counter = Counter(str(v) for v in values)
            top_items = counter.most_common(10)
            dist = ", ".join(f"{k}={v}" for k, v in top_items)
            if len(counter) > 10:
                dist += f", ...共{len(counter)}种"
            lines.append(f"- {col}: {dist}")

    return "\n".join(lines)
```

**关键点：统计摘要由代码计算，不是让模型计算。** 模型看到的 min/max/avg/分布都是确定性的数字。

**优先级：P0**
**复杂度：低**
**预期效果：直接解决 50%+ 的 SQL 场景编造问题**

---

### 2.5 第⑤层：回答数值确定性校验

**现状问题：** harness 模块当前是空壳（方案 A 用 LLM 验证失败后清空了）。

**方案：** 只做 SQL 场景的确定性数值校验，不做通用 harness，不用 LLM 校验。

**实现要点：**

```python
# harness/checks.py

import re
from dataclasses import dataclass

@dataclass
class HarnessResult:
    passed: bool
    reason: str = ""
    suspicious_values: list[str] = field(default_factory=list)

def check_sql_answer_values(answer: str, tool_outputs: list[str], has_tool_calls: bool) -> HarnessResult:
    """检查 SQL 场景下回答中的数值是否可追溯到工具输出。

    只在以下条件同时满足时执行：
    1. has_tool_calls=True（模型调用了工具）
    2. tool_outputs 非空（有 SQL 查询结果）
    3. 回答中包含具体数值

    不拦截、不重跑，只标记可疑数值。
    """
    if not has_tool_calls or not tool_outputs:
        return HarnessResult(passed=True)

    # 从回答中提取数值（整数和小数）
    answer_numbers = set(re.findall(r'\b\d+\.?\d*\b', answer))
    if not answer_numbers:
        return HarnessResult(passed=True)

    # 从工具输出中提取所有数值
    source_numbers = set()
    for output in tool_outputs:
        source_numbers.update(re.findall(r'\b\d+\.?\d*\b', output))

    # 过滤掉常见的非数据数值（年份、页码、序号等）
    trivial = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
               '100', '1000', '2026', '2025', '2024'}
    answer_numbers -= trivial
    source_numbers -= trivial

    # 找出回答中有但工具输出中没有的数值
    suspicious = answer_numbers - source_numbers
    if suspicious:
        return HarnessResult(
            passed=False,
            reason=f"回答中包含工具输出中不存在的数值: {', '.join(sorted(suspicious)[:5])}",
            suspicious_values=sorted(suspicious)[:5],
        )

    return HarnessResult(passed=True)
```

**集成方式（在 chat_stream 中）：**

```python
# 回答生成完成后，文本发送给前端之前
if deps.has_numeric_sql and deps.tool_outputs:
    from app.agent.harness.checks import check_sql_answer_values
    check = check_sql_answer_values(result_text, deps.tool_outputs, deps.has_tool_calls)
    if not check.passed:
        logger.warning("harness_suspicious_values",
                       reason=check.reason,
                       values=check.suspicious_values)
        # 不拦截，追加 disclaimer
        yield {"event": "token", "data": {
            "content": "\n\n> ⚠️ 注意：以上部分数值未能与查询结果完全匹配，请以数据表格中的原始数据为准。"
        }}
```

**设计原则：**
- **不拦截**：误伤风险高（模型可能做了合理的格式化，如"1234" → "1,234"），只追加提示
- **不重跑**：之前验证过 LLM 重跑也会编造，增加延迟无收益
- **只做 SQL 场景**：RAG 场景的 groundedness 检测需要语义理解，确定性代码做不好
- **日志记录**：所有可疑案例记录日志，用于后续 prompt 优化和评测

**优先级：P1**
**复杂度：低**
**预期效果：标记可疑编造，引导用户看原始数据**

---

## 3. RAG 场景：强化 Prompt 约束

RAG 场景的编造问题相对轻，当前方案（空结果拒答 + prompt 约束）已经是业界标准做法。进一步优化：

### 3.1 强化 Closing Instruction

**现状：** `rag_search` 的 `to_text()` 在有结果时只说"请严格基于以下内容回答"。

**优化：** 在检索结果末尾追加更强的约束：

```python
# tools/rag_search.py to_text() 末尾追加
footer = (
    "\n\n---\n"
    "以上是全部检索结果。回答要求：\n"
    "1. 只使用以上内容回答，不要补充知识库中没有的信息\n"
    "2. 如果以上内容不足以完整回答用户问题，告知用户"知识库中相关信息有限"\n"
    "3. 用【文档名 第X页】标注引用来源"
)
```

**优先级：P1**
**复杂度：极低**

### 3.2 检索结果质量预判

**方案：** 当所有检索结果的 RRF score 都低于阈值时，在返回给模型的文本中明确标注"检索结果相关性较低"。

```python
# 在 rag_search 工具中
if all(c.score < 0.015 for c in output.chunks):
    header = "【知识库检索结果相关性较低】以下内容可能与用户问题不完全匹配，请谨慎引用：\n"
```

**优先级：P2**
**复杂度：低**

---

## 4. 通用防线：Prompt 工程优化

### 4.1 System Prompt 增加负面示例

在回答原则中增加"不要做什么"的具体示例：

```markdown
## 错误示例（绝对禁止）

❌ 用户问"设备A的电压"，你没有调用 sql_query 就回答"设备A电压为380V"
   → 正确做法：先调用 sql_query 查询，查不到就说"暂无数据"

❌ sql_query 返回了3条记录，你在回答中写了5条数据
   → 正确做法：只展示查询返回的数据，不要补充

❌ sql_query 返回 avg=35.2，你在回答中写"平均温度约35度"
   → 正确做法：直接写"平均温度 35.2"，不要四舍五入或近似
```

**优先级：P1**
**复杂度：极低**

### 4.2 Temperature 动态调整

数据分析场景使用更低的 temperature 减少随机性：

```python
# 在 chat_stream 中，根据是否有 SQL 工具调用动态调整
# 默认 temperature=0.1，SQL 场景可降到 0.0
```

**优先级：P2**
**复杂度：低**

---

## 5. 中期方案：查询模板（轻量 Semantic Layer）

### 5.1 背景

dbt 的 2026 基准测试表明：Semantic Layer 方案在覆盖范围内准确率接近 100%，因为 LLM 的任务被简化为"选择正确的 metric 和 dimension"，查询生成是确定性的。

完整的 Semantic Layer 太重，但可以借鉴思路做轻量版。

### 5.2 方案：参数化查询模板

为高频查询场景预定义模板，LLM 只需填参数：

```python
QUERY_TEMPLATES = {
    "device_alarms": {
        "description": "查询设备告警记录",
        "params": {
            "device_name": {"type": "str", "description": "设备名称，可选"},
            "start_time": {"type": "datetime", "description": "开始时间"},
            "end_time": {"type": "datetime", "description": "结束时间"},
            "alarm_level": {"type": "str", "description": "告警级别，可选", "enum": ["critical", "major", "minor", "warning"]},
        },
        "template": """
            SELECT a.*, d.device_name, d.site_name
            FROM alarms a JOIN devices d ON a.device_id = d.id
            WHERE 1=1
            {%- if device_name %} AND d.device_name = :device_name {%- endif %}
            {%- if alarm_level %} AND a.alarm_level = :alarm_level {%- endif %}
            AND a.occurred_at BETWEEN :start_time AND :end_time
            ORDER BY a.occurred_at DESC
        """,
    },
    "metric_trend": {
        "description": "查询设备运行指标趋势",
        "params": {
            "device_name": {"type": "str", "description": "设备名称"},
            "metric_name": {"type": "str", "description": "指标名称", "enum": ["voltage", "current", "temperature", "soc", "soh"]},
            "start_time": {"type": "datetime", "description": "开始时间"},
            "end_time": {"type": "datetime", "description": "结束时间"},
        },
        "template": "...",
    },
    "alarm_statistics": {
        "description": "告警统计分析（按站点/级别/时间段）",
        "params": { ... },
        "template": "...",
    },
}
```

**工作流程：**
1. LLM 先判断用户问题是否匹配已有模板
2. 匹配 → 调用 `template_query` 工具，只填参数（准确率接近 100%）
3. 不匹配 → 走现有的自由 SQL 生成路径

**优先级：P2**
**复杂度：高**
**预期效果：高频场景 SQL 准确率接近 100%**

---

## 6. 长期方案：评测驱动优化

### 6.1 评测集构建

| 类别 | 示例 | 预期行为 |
|------|------|----------|
| SQL 正确性 | "最近7天告警统计" | SQL 正确、数据准确 |
| SQL 编造检测 | "设备A的电压"（数据库无此设备） | 返回"暂无数据"，不编造 |
| RAG groundedness | "电池过温怎么处理" | 回答基于检索内容，有引用 |
| RAG 拒答 | "量子计算原理"（知识库无关） | 明确告知"知识库中暂无" |
| 混合查询 | "E003告警最近出现几次，怎么处理" | 先查数据再查知识库，汇总 |
| 不编造测试 | "预测下周告警趋势" | 拒绝预测，只展示历史数据 |

### 6.2 自动化评测

- 每次 prompt 修改后跑评测集回归
- 记录 groundedness、拒答准确率、SQL 正确率
- 通过 Langfuse 追踪 prompt 版本与效果的关系

**优先级：P3（第四阶段）**

---

## 7. 方案总结与优先级

| 优先级 | 方案 | 场景 | 复杂度 | 预期效果 |
|--------|------|------|--------|----------|
| **P0** | to_text() 分层返回完整数据 | SQL | 低 | 解决 50%+ SQL 编造 |
| **P0** | Schema 枚举值 + 表间关系注入 | SQL | 中 | 减少 SQL 生成错误 |
| **P0** | Few-shot 查询示例 | SQL | 低 | 高频场景准确率提升 |
| **P1** | SQL dry-run 预检 + 自纠错 | SQL | 中 | 拦截无效 SQL |
| **P1** | 数值确定性校验（harness） | SQL | 低 | 标记可疑编造 |
| **P1** | RAG closing instruction 强化 | RAG | 极低 | 减少知识补充 |
| **P1** | Prompt 负面示例 | 通用 | 极低 | 减少常见编造模式 |
| **P2** | 查询模板（轻量 Semantic Layer） | SQL | 高 | 高频场景接近 100% |
| **P2** | 结构化输出（output_type） | 通用 | 中 | 系统性防编造 |
| **P2** | Temperature 动态调整 | SQL | 低 | 减少随机性 |
| **P2** | 检索结果质量预判 | RAG | 低 | 低质量结果预警 |
| **P3** | 评测集 + 自动化回归 | 通用 | 高 | 持续优化闭环 |
| **P3** | NLI groundedness 检测 | RAG | 高 | RAG 编造检测 |

### 不做的事

| 方案 | 原因 |
|------|------|
| 用 LLM 校验 LLM | 已验证会误判，增加延迟和成本 |
| 通用 harness（拦截所有场景） | 误伤率高，之前已踩坑清空 |
| 换 Agent 框架 | PydanticAI 能力足够，问题在使用方式 |
| 强制拦截+重跑 | 重跑同样可能编造，降级展示原始数据更可靠 |

---

## 8. 参考资料

- dbt Semantic Layer vs Text-to-SQL 2026 基准测试：Semantic Layer 在覆盖范围内准确率接近 100%
- ActiveWizards Text-to-SQL 架构：多阶段 pipeline + EXPLAIN 预检 + 反馈循环
- Wren AI 方案：Schema-first + Dry-run 验证 + 语义层（MDL）
- RAGTruth 基准：NLI 模型做 groundedness 检测 F1=0.83
- OpenAI Agents SDK Guardrails：input/output/tool 三层 guardrail 设计（参考思路，不采用框架）
