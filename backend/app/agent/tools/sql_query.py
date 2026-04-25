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
        # Return summary instead of raw data to prevent LLM from dumping it as text
        # The full data is already sent to frontend via data_table SSE event
        summary = f"查询到 {self.row_count} 条记录，字段: {', '.join(self.columns)}"
        # Show first 3 rows as sample for LLM to understand the data
        if self.rows:
            samples = []
            for row in self.rows[:3]:
                pairs = [f"{col}={val}" for col, val in zip(self.columns, row)]
                samples.append("; ".join(pairs))
            summary += "\n示例数据:\n" + "\n".join(f"  - {s}" for s in samples)
            if self.row_count > 3:
                summary += f"\n  ... 共 {self.row_count} 行"
        return summary
