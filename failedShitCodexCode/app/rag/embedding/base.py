from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_query(self, text: str) -> list[float]:
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...
