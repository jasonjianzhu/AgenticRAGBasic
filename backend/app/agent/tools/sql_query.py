"""SQL query tool — executes read-only SQL against the business database."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# Max rows to show in full table mode (beyond this, use summary + stats)
_FULL_TABLE_THRESHOLD = 30
_SUMMARY_SHOW_ROWS = 20

_CLOSING = (
    "\n\n以上是完整查询结果。请严格基于这些数据回答，不要编造任何不在结果中的数值。"
    "如需统计分析（求和、平均、计数等），请用 SQL 聚合函数重新查询，不要手动计算。"
)


@dataclass
class SQLQueryInput:
    """Input for sql_query tool."""
    sql: str
    explanation: str = ""  # LLM explains what this query does


@dataclass
class SQLQueryOutput:
    """Output from sql_query tool."""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    error: str | None = None

    def to_text(self) -> str:
        """Return query results for LLM consumption.

        Strategy:
        - 0 rows: explicit "no data" with instruction not to fabricate
        - 1-30 rows: full Markdown table (LLM sees everything)
        - 31+ rows: first N rows + code-computed statistics summary
        """
        if self.error:
            return f"查询失败: {self.error}"
        if not self.rows:
            return "查询无结果。请告知用户暂无相关数据，不要编造任何数据。"

        if self.row_count <= _FULL_TABLE_THRESHOLD:
            return self._full_table() + _CLOSING
        else:
            return self._summary_with_stats() + _CLOSING

    def _full_table(self) -> str:
        """Full Markdown table — LLM sees all data."""
        lines = [f"查询到 {self.row_count} 条记录:\n"]
        lines.append("| " + " | ".join(self.columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(self.columns)) + " |")
        for row in self.rows:
            lines.append("| " + " | ".join(str(v) for v in row) + " |")
        return "\n".join(lines)

    def _summary_with_stats(self) -> str:
        """First N rows + code-computed statistics for large result sets."""
        show_n = _SUMMARY_SHOW_ROWS
        lines = [f"查询到 {self.row_count} 条记录:\n"]

        # Show first N rows
        lines.append("| " + " | ".join(self.columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(self.columns)) + " |")
        for row in self.rows[:show_n]:
            lines.append("| " + " | ".join(str(v) for v in row) + " |")
        lines.append(f"\n（以上展示前 {show_n} 行，共 {self.row_count} 行）\n")

        # Code-computed statistics (not LLM-computed)
        lines.append("统计摘要:")
        for i, col in enumerate(self.columns):
            values = [row[i] for row in self.rows if row[i] is not None]
            numeric = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if numeric:
                lines.append(
                    f"- {col}: min={min(numeric)}, max={max(numeric)}, "
                    f"avg={sum(numeric)/len(numeric):.2f}, count={len(numeric)}"
                )
            elif values:
                counter = Counter(str(v) for v in values)
                top = counter.most_common(10)
                dist = ", ".join(f"{k}={v}" for k, v in top)
                if len(counter) > 10:
                    dist += f", ...共{len(counter)}种"
                lines.append(f"- {col}: {dist}")

        return "\n".join(lines)
