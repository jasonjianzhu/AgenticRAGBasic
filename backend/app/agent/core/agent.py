"""PydanticAI Agent definition with tool registration.

This is the central Agent that handles multi-turn dialogue,
intent routing (knowledge QA vs data analysis), and tool orchestration.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext

from app.common.core.logging import get_logger
from app.agent.core.prompts import build_system_prompt
from app.agent.tools.chart import ChartAxis, ChartConfig, ChartSeries
from app.agent.tools.rag_search import RAGSearchChunk, RAGSearchOutput
from app.agent.tools.sql_query import SQLQueryOutput

logger = get_logger(__name__)


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
        model_name: PydanticAI model identifier (e.g. "openai:gpt-4o", "anthropic:model").
        system_prompt: Full system prompt including DB schema.
        provider: Optional provider instance (e.g. AnthropicProvider with custom base_url).

    Returns:
        Configured Agent instance.
    """
    kwargs: dict[str, Any] = {
        "instructions": system_prompt,
        "deps_type": AgentDeps,
        "output_type": str,
        "retries": 2,
    }

    # If a custom provider is given, create a Model object instead of using string
    if provider:
        from pydantic_ai.models.anthropic import AnthropicModel
        model = AnthropicModel(model_name.replace("anthropic:", ""), provider=provider)
        agent = Agent(model, **kwargs)
    else:
        agent = Agent(model_name, **kwargs)

    # ── RAG Search Tool ──────────────────────────────────────

    @agent.tool
    async def rag_search(ctx: RunContext[AgentDeps], query: str, top_k: int = 5) -> str:
        """检索知识库，查找技术文档、产品手册、FAQ 中的相关内容。

        Args:
            query: 检索问题，例如"电池过温告警处理方法"
            top_k: 返回结果数量，默认5
        """
        deps = ctx.deps
        if deps.emit_event:
            await deps.emit_event("tool_start", {
                "tool": "rag_search",
                "args_summary": f"检索: {query[:50]}",
            })

        try:
            result = await deps.rag_service.search(
                query=query,
                kb_ids=deps.kb_ids,
                top_k=top_k,
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

            # Emit citations
            if deps.emit_event:
                for chunk in output.chunks:
                    await deps.emit_event("citation", {
                        "index": chunk.index,
                        "document_title": chunk.document_title,
                        "page": chunk.page_start,
                        "snippet": chunk.content[:200],
                    })
                await deps.emit_event("tool_result", {
                    "tool": "rag_search",
                    "summary": f"找到 {len(output.chunks)} 条相关结果",
                })

            return output.to_text()

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

            return output.to_text()

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
