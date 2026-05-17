"""PydanticAI Agent definition with tool registration.

This is the central Agent that handles multi-turn dialogue,
intent routing (knowledge QA vs data analysis), and tool orchestration.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext

from app.agent.tools.chart import ChartAxis, ChartConfig, ChartSeries
from app.agent.tools.rag_search import RAGSearchChunk, RAGSearchOutput
from app.agent.tools.sql_query import SQLQueryOutput
from app.common.core.logging import get_logger

logger = get_logger(__name__)


def _has_numeric_values(rows: list[list]) -> bool:
    """Check if query results contain numeric values (not just strings).

    Returns False for metadata queries (table names, column names, etc.)
    Returns True for business data queries (voltages, counts, metrics, etc.)
    """
    for row in rows[:5]:  # check first 5 rows
        for val in row:
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return True
    return False


# ---------------------------------------------------------------------------
# Agent dependencies — injected into every tool call
# ---------------------------------------------------------------------------

@dataclass
class AgentDeps:
    """Dependencies available to all Agent tool calls."""

    # RAG service (from Phase 2)
    rag_service: Any  # RAGService instance
    # SQL executor
    sql_executor: Any  # SQLExecutor instance
    sql_validator: Any  # SQLValidator instance
    # Default KB IDs for RAG search
    kb_ids: list[uuid.UUID] = field(default_factory=list)
    # Callback to emit SSE events during tool execution
    emit_event: Any = None  # async callable(event_type, data)
    # Collected citations from rag_search calls (keyed by index)
    collected_citations: dict = field(default_factory=dict)
    # Collected raw sql_query outputs for display on fallback
    tool_outputs: list[str] = field(default_factory=list)
    has_numeric_sql: bool = False
    has_tool_calls: bool = False


# ---------------------------------------------------------------------------
# Create the Agent
# ---------------------------------------------------------------------------

def create_agent(
    model_name: str = "openai:gpt-4o",
    system_prompt: str = "",
    provider: Any = None,
) -> Agent[AgentDeps, str]:
    """Create a PydanticAI Agent with all tools registered.

    Args:
        model_name: PydanticAI model identifier (e.g. "openai:deepseek-v4-pro", "anthropic:deepseek-v4-pro").
        system_prompt: Full system prompt including DB schema.
        provider: Optional provider instance (e.g. AnthropicProvider with custom base_url).

    Returns:
        Configured Agent instance.
    """
    if provider:
        from pydantic_ai.models.anthropic import AnthropicModel
        model = AnthropicModel(model_name.replace("anthropic:", ""), provider=provider)
        agent = Agent(
            model,
            instructions=system_prompt,
            deps_type=AgentDeps,
            output_type=str,
            retries=3,
        )
    else:
        agent = Agent(
            model_name,
            instructions=system_prompt,
            deps_type=AgentDeps,
            output_type=str,
            retries=3,
        )

    # ── RAG Search Tool ──────────────────────────────────────

    @agent.tool
    async def kb_search(ctx: RunContext[AgentDeps], query: str = "", top_k: int = 5) -> str:
        """检索知识库，查找技术文档、产品手册、FAQ 中的相关内容。

        Args:
            query: 必须原封不动使用用户发送的完整原文，禁止任何修改、拆分或关键词提取
            top_k: 返回结果数量，默认5
        """
        deps = ctx.deps
        raw_query = query
        if not query.strip():
            prompt_text = ctx.prompt if isinstance(ctx.prompt, str) else ""
            query = prompt_text.strip() or query
            if query.strip():
                logger.info(
                    "rag_search_tool_query_resolved",
                    tool_name="kb_search",
                    raw_query=raw_query,
                    prompt_text=prompt_text[:160],
                    resolved_query=query[:160],
                )
        if not query.strip():
            logger.warning(
                "rag_search_tool_invalid_args",
                tool_name="kb_search",
                raw_args={"query": query, "top_k": top_k},
                error_reason="query_missing_or_empty",
            )
            if deps.emit_event:
                await deps.emit_event("tool_result", {
                    "tool": "kb_search",
                    "summary": "检索失败: 缺少 query 参数",
                })
            return "知识库检索失败: kb_search 缺少非空 query 参数，请用完整检索问题重新调用。"
        if deps.emit_event:
            await deps.emit_event("tool_start", {
                "tool": "kb_search",
                "args_summary": f"检索: {query[:50]}",
            })

        try:
            logger.info(
                "rag_search_tool_start",
                tool_name="kb_search",
                query=query[:120],
                top_k=top_k,
                kb_ids=[str(kb_id) for kb_id in deps.kb_ids],
            )
            result = await deps.rag_service.search(
                query=query,
                kb_ids=deps.kb_ids,
                top_k=top_k,
                enable_rewrite=False,
            )

            output = RAGSearchOutput(
                chunks=[
                    RAGSearchChunk(
                        index=i + 1,
                        document_title=r.document_title,
                        content=r.content,
                        page_start=r.page_start,
                        score=r.score,
                    )
                    for i, r in enumerate(result.results)
                ],
                total_hits=result.trace.returned,
            )

            # Store citations keyed by "document_title 第X页" for post-answer matching
            if deps.emit_event:
                for chunk in output.chunks:
                    cite_key = chunk.document_title
                    if chunk.page_start:
                        cite_key += f" 第{chunk.page_start}页"
                    deps.collected_citations[cite_key] = {
                        "document_title": chunk.document_title,
                        "page": chunk.page_start,
                        "snippet": chunk.content[:200],
                    }
                await deps.emit_event("tool_result", {
                    "tool": "rag_search",
                    "summary": f"找到 {len(output.chunks)} 条相关结果",
                })

            text_result = output.to_text()
            deps.has_tool_calls = True
            logger.info("rag_search_tool_result",
                        query=query,
                        chunks=len(output.chunks),
                        total_hits=output.total_hits,
                        titles=[c.document_title for c in output.chunks],
                        content_preview=text_result[:300])
            return text_result

        except Exception as e:
            logger.error("rag_search_tool_error", error=str(e))
            if deps.emit_event:
                await deps.emit_event("tool_result", {
                    "tool": "rag_search",
                    "summary": f"检索失败: {e}",
                })
            return f"知识库检索失败: {e}"

    # ── SQL Query Tool ───────────────────────────────────────

    @agent.tool
    async def sql_query(ctx: RunContext[AgentDeps], sql: str, explanation: str = "") -> str:
        """查询储能业务数据库，获取设备运行数据、告警记录、维护日志等。

        Args:
            sql: SELECT 查询语句，基于系统提示中的数据库 schema 编写
            explanation: 简要说明这个查询的目的
        """
        deps = ctx.deps
        if deps.emit_event:
            await deps.emit_event("tool_start", {
                "tool": "sql_query",
                "args_summary": explanation or sql[:80],
            })

        try:
            # Validate and rewrite SQL
            safe_sql = deps.sql_validator.validate_and_rewrite(sql)

            # Execute
            columns, rows, row_count = await deps.sql_executor.execute(safe_sql)

            output = SQLQueryOutput(columns=columns, rows=rows, row_count=row_count)
            logger.info("sql_query_tool_result", sql=safe_sql[:200], row_count=row_count, explanation=explanation[:80])

            # Emit data table event
            if deps.emit_event:
                await deps.emit_event("data_table", {
                    "columns": columns,
                    "rows": rows[:100],  # cap for SSE
                    "row_count": row_count,
                })
                await deps.emit_event("tool_result", {
                    "tool": "sql_query",
                    "summary": f"查询到 {row_count} 条记录",
                })

            sql_text_result = output.to_text()
            deps.has_tool_calls = True
            # Only collect for harness if query returned numeric data
            if _has_numeric_values(output.rows):
                deps.tool_outputs.append(sql_text_result)
                deps.has_numeric_sql = True
            return sql_text_result

        except Exception as e:
            error_msg = str(e)
            logger.error("sql_query_tool_error", error=error_msg, sql=sql[:200])
            if deps.emit_event:
                await deps.emit_event("tool_result", {
                    "tool": "sql_query",
                    "summary": f"查询失败: {error_msg}",
                })
            return f"SQL 查询失败: {error_msg}"

    # ── Chart Generation Tool ────────────────────────────────

    @agent.tool
    async def generate_chart(
        ctx: RunContext[AgentDeps],
        chart_type: str,
        title: str,
        x_label: str,
        x_data: list[str],
        y_label: str,
        series: list[dict[str, Any]],
    ) -> str:
        """根据数据生成图表，前端会自动渲染。

        Args:
            chart_type: 图表类型，可选 line/bar/pie/area/stacked_bar
            title: 图表标题
            x_label: X轴标签
            x_data: X轴数据列表
            y_label: Y轴标签
            series: 数据系列列表，每项包含 name(系列名) 和 data(数据列表)
        """
        deps = ctx.deps

        config = ChartConfig(
            chart_type=chart_type,
            title=title,
            x_axis=ChartAxis(label=x_label, data=x_data),
            y_axis=ChartAxis(label=y_label),
            series=[ChartSeries(name=s.get("name", ""), data=s.get("data", [])) for s in series],
        )

        echarts_option = config.to_echarts_option()

        if deps.emit_event:
            await deps.emit_event("chart", echarts_option)

        return f"已生成{chart_type}图表: {title}"

    return agent
