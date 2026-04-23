"""SQL query tool — executes read-only SQL against the business database."""
from __future__ import annotations

from dataclasses import dataclass, field


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
        if self.error:
            return f"查询失败: {self.error}"
        if not self.rows:
            return "查询无结果。"
        # Simple text table
        header = " | ".join(self.columns)
        lines = [header, "-" * len(header)]
        for row in self.rows[:20]:  # show first 20 in text
            lines.append(" | ".join(str(v) for v in row))
        if self.row_count > 20:
            lines.append(f"... 共 {self.row_count} 行")
        return "\n".join(lines)
