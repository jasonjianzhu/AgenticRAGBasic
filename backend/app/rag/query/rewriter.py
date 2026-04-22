"""Query rewriting and expansion using LLM."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.common.core.logging import get_logger
from app.rag.generation.base import BaseLLMClient, LLMMessage

logger = get_logger(__name__)

REWRITE_SYSTEM_PROMPT = """你是一个搜索查询改写助手。用户会输入一个问题，你需要：
1. 改写为更适合检索的查询（保留核心语义，补充同义词和相关术语）
2. 提取关键词用于扩展检索

请严格按以下 JSON 格式返回，不要输出其他内容：
{
  "rewritten_query": "改写后的查询",
  "keywords": ["关键词1", "关键词2", "关键词3"]
}"""


@dataclass
class RewriteResult:
    """Result of query rewriting."""

    original_query: str
    rewritten_query: str
    keywords: list[str] = field(default_factory=list)


class QueryRewriter:
    """Rewrite and expand queries using an LLM.

    Args:
        llm_client: LLM client for generating rewrites.
    """

    def __init__(self, llm_client: BaseLLMClient) -> None:
        self._llm = llm_client

    async def rewrite(self, query: str) -> RewriteResult:
        """Rewrite a query for better retrieval.

        Args:
            query: Original user query.

        Returns:
            RewriteResult with rewritten query and extracted keywords.
            Falls back to original query on LLM failure.
        """
        messages = [
            LLMMessage(role="system", content=REWRITE_SYSTEM_PROMPT),
            LLMMessage(role="user", content=query),
        ]

        try:
            response = await self._llm.complete(messages, temperature=0.1, max_tokens=256)
            parsed = self._parse_response(response.content)
            result = RewriteResult(
                original_query=query,
                rewritten_query=parsed.get("rewritten_query", query),
                keywords=parsed.get("keywords", []),
            )
            logger.info(
                "query_rewritten",
                original=query,
                rewritten=result.rewritten_query,
                keywords=result.keywords,
            )
            return result
        except Exception as e:
            logger.warning("query_rewrite_failed", query=query, error=str(e))
            return RewriteResult(original_query=query, rewritten_query=query)

    def _parse_response(self, content: str) -> dict:
        """Parse LLM response as JSON, with fallback extraction."""
        content = content.strip()

        # Try direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass

        # Fallback: return content as rewritten_query
        return {"rewritten_query": content, "keywords": []}
