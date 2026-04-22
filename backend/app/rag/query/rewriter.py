"""Query rewriting and expansion using LLM."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.common.core.logging import get_logger
from app.rag.generation.base import BaseLLMClient, LLMMessage

logger = get_logger(__name__)

REWRITE_SYSTEM_PROMPT = """你是一个搜索查询改写助手。用户会输入一个问题，请将其改写为更适合向量检索的查询。

规则：
1. 保留核心语义，补充同义词和相关术语
2. 只输出改写后的查询文本，一行，不要输出任何解释、思考过程或其他内容
3. 不要回答用户的问题，只做查询改写

示例：
用户：电池过温怎么办
输出：电池过温告警 温度过高 处理方法 解决方案

用户：ESS-5000安装步骤
输出：ESS-5000 储能系统 安装步骤 安装指南 操作流程"""


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
            response = await self._llm.complete(messages, temperature=0.1, max_tokens=128)
            rewritten = self._clean_response(response.content)
            result = RewriteResult(
                original_query=query,
                rewritten_query=rewritten if rewritten else query,
                keywords=[],
            )
            logger.info(
                "query_rewritten",
                original=query,
                rewritten=result.rewritten_query,
            )
            return result
        except Exception as e:
            logger.warning("query_rewrite_failed", query=query, error=str(e))
            return RewriteResult(original_query=query, rewritten_query=query)

    def _clean_response(self, content: str) -> str:
        """Clean LLM response: strip think tags, markdown, extra whitespace."""
        import re
        text = content.strip()
        # Remove <think>...</think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Remove markdown code blocks
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
        # Take only the first line (in case LLM added explanations)
        first_line = text.split("\n")[0].strip()
        # If the response is too long (>200 chars), it's probably an answer not a rewrite
        if len(first_line) > 200:
            return ""
        return first_line
