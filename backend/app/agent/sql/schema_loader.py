"""Schema loader — reads business DB table structures for Agent prompt injection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.core.config import Settings, get_settings
from app.common.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ColumnInfo:
    name: str
    type: str
    comment: str | None = None
    nullable: bool = True


@dataclass
class TableInfo:
    name: str
    comment: str | None = None
    columns: list[ColumnInfo] = field(default_factory=list)


class SchemaLoader:
    """Loads business database schema for injection into Agent system prompt.

    Uses SQLAlchemy inspect to read table metadata.
    """

    def __init__(self, session_factory: async_sessionmaker, allowed_tables: set[str] | None = None) -> None:
        self._factory = session_factory
        self._allowed_tables = allowed_tables  # None = all tables

    async def load_schema(self) -> list[TableInfo]:
        """Load table schemas from the business database."""
        tables: list[TableInfo] = []

        async with self._factory() as session:
            # Use raw SQL to get table and column info (works with asyncpg)
            table_rows = await session.execute(text(
                "SELECT table_name, obj_description((quote_ident(table_schema) || '.' || quote_ident(table_name))::regclass) as comment "
                "FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            ))

            for row in table_rows:
                table_name = row[0]
                table_comment = row[1]

                if self._allowed_tables and table_name.lower() not in {t.lower() for t in self._allowed_tables}:
                    continue

                col_rows = await session.execute(text(
                    "SELECT c.column_name, c.data_type, c.is_nullable, "
                    "pgd.description "
                    "FROM information_schema.columns c "
                    "LEFT JOIN pg_catalog.pg_statio_all_tables st ON st.relname = c.table_name AND st.schemaname = c.table_schema "
                    "LEFT JOIN pg_catalog.pg_description pgd ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position "
                    "WHERE c.table_schema = 'public' AND c.table_name = :table "
                    "ORDER BY c.ordinal_position"
                ), {"table": table_name})

                columns = []
                for col_row in col_rows:
                    columns.append(ColumnInfo(
                        name=col_row[0],
                        type=col_row[1],
                        nullable=col_row[2] == "YES",
                        comment=col_row[3],
                    ))

                tables.append(TableInfo(
                    name=table_name,
                    comment=table_comment,
                    columns=columns,
                ))

        return tables

    async def format_for_prompt(self) -> str:
        """Load schema and format as text for LLM prompt injection."""
        tables = await self.load_schema()
        if not tables:
            return "（业务数据库无可用表）"

        parts = []
        for t in tables:
            comment = f" -- {t.comment}" if t.comment else ""
            lines = [f"### {t.name}{comment}", ""]
            lines.append("| 字段 | 类型 | 说明 |")
            lines.append("|------|------|------|")
            for c in t.columns:
                col_comment = c.comment or ""
                lines.append(f"| {c.name} | {c.type} | {col_comment} |")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def to_api_response(self, tables: list[TableInfo]) -> list[dict]:
        """Convert to API response format."""
        return [
            {
                "name": t.name,
                "comment": t.comment,
                "columns": [
                    {"name": c.name, "type": c.type, "comment": c.comment, "nullable": c.nullable}
                    for c in t.columns
                ],
            }
            for t in tables
        ]
