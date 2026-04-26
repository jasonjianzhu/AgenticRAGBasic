"""SQL safety validator — ensures only read-only queries on allowed tables."""
from __future__ import annotations

import re

import sqlparse
from sqlparse.sql import IdentifierList, Identifier
from sqlparse.tokens import Keyword, DML

from app.common.core.logging import get_logger

logger = get_logger(__name__)

# Statements that modify data or schema
_FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE", "MERGE", "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL",
}


class SQLValidationError(Exception):
    """Raised when SQL fails safety validation."""


class SQLValidator:
    """Validates SQL queries for safety.

    Rules:
    - Only SELECT statements allowed
    - Only whitelisted tables can be queried
    - LIMIT is injected if missing
    """

    def __init__(self, allowed_tables: set[str] | None = None, max_rows: int = 500) -> None:
        self._allowed_tables = allowed_tables  # None = allow all
        self._max_rows = max_rows

    def validate_and_rewrite(self, sql: str) -> str:
        """Validate SQL and return a safe, rewritten version.

        Raises SQLValidationError if the query is not allowed.
        """
        sql = sql.strip().rstrip(";")
        if not sql:
            raise SQLValidationError("空 SQL 语句")

        # Parse
        parsed = sqlparse.parse(sql)
        if not parsed:
            raise SQLValidationError("无法解析 SQL")

        stmt = parsed[0]

        # Check statement type
        stmt_type = stmt.get_type()
        if stmt_type and stmt_type.upper() != "SELECT":
            logger.warning("sql_validation_rejected", reason=f"non-SELECT: {stmt_type}", sql=sql[:200])
            raise SQLValidationError(f"只允许 SELECT 查询，当前为 {stmt_type}")

        # Check for forbidden keywords in tokens
        sql_upper = sql.upper()
        for kw in _FORBIDDEN_KEYWORDS:
            # Match as whole word to avoid false positives
            if re.search(rf"\b{kw}\b", sql_upper):
                logger.warning("sql_validation_rejected", reason=f"forbidden keyword: {kw}", sql=sql[:200])
                raise SQLValidationError(f"禁止使用 {kw} 语句")

        # Check table whitelist
        if self._allowed_tables is not None:
            tables = self._extract_tables(sql)
            for table in tables:
                if table.lower() not in {t.lower() for t in self._allowed_tables}:
                    logger.warning("sql_validation_rejected", reason=f"table not allowed: {table}", sql=sql[:200])
                    raise SQLValidationError(f"不允许查询表 '{table}'，允许的表: {', '.join(sorted(self._allowed_tables))}")

        # Inject LIMIT if missing
        if not re.search(r"\bLIMIT\b", sql_upper):
            sql = f"{sql} LIMIT {self._max_rows}"

        return sql

    def _extract_tables(self, sql: str) -> list[str]:
        """Extract table names from a SQL query."""
        tables: list[str] = []
        parsed = sqlparse.parse(sql)[0]

        from_seen = False
        for token in parsed.tokens:
            # Skip whitespace — don't reset from_seen
            if token.ttype is sqlparse.tokens.Whitespace:
                continue
            if token.ttype is Keyword and token.value.upper() in (
                "FROM", "JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "CROSS JOIN",
            ):
                from_seen = True
                continue
            if from_seen:
                if isinstance(token, IdentifierList):
                    for identifier in token.get_identifiers():
                        name = identifier.get_real_name()
                        if name:
                            tables.append(name)
                elif isinstance(token, Identifier):
                    name = token.get_real_name()
                    if name:
                        tables.append(name)
                from_seen = False

        return tables
