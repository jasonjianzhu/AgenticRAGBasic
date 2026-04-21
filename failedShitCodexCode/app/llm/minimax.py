from __future__ import annotations

import httpx
import orjson
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.rag.query.rewrite import QueryRewriteResult


class MiniMaxClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def rewrite_query(self, query: str) -> QueryRewriteResult:
        prompt = (
            "Rewrite the user query for retrieval and return JSON with keys "
            "rewritten_query, expanded_queries, language, document_type.\n"
            f"User query: {query}"
        )
        text = self._call_messages(prompt)
        payload = orjson.loads(text)
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=payload["rewritten_query"],
            expanded_queries=payload.get("expanded_queries", []),
            language=payload.get("language"),
            document_type=payload.get("document_type"),
        )

    def generate_answer(self, query: str, context_blocks: list[str]) -> str:
        prompt = (
            "Answer the user question using only the provided context.\n"
            f"Question: {query}\n"
            "Context:\n"
            + "\n\n".join(context_blocks)
        )
        return self._call_messages(prompt)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(httpx.HTTPError),
    )
    def _call_messages(self, prompt: str) -> str:
        response = httpx.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        contents = payload.get("content", [])
        text_blocks = [item.get("text", "") for item in contents if item.get("type") == "text"]
        return "\n".join(part for part in text_blocks if part).strip()
