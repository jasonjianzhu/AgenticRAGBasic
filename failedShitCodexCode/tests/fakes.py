from __future__ import annotations

import hashlib

from app.rag.query.rewrite import QueryRewriteResult


class DeterministicEmbeddingProvider:
    def __init__(self, dimension: int):
        self.dimension = dimension

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for index in range(self.dimension):
            byte = digest[index % len(digest)]
            values.append(byte / 255.0)
        return values


class FakeLLMClient:
    def rewrite_query(self, query: str):
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=f"{query} rewritten",
            expanded_queries=[f"{query} expansion"],
            language="en",
            document_type="manual",
        )

    def generate_answer(self, query: str, context_blocks: list[str]) -> str:
        return f"LLM answer for {query}: {context_blocks[0]}"
