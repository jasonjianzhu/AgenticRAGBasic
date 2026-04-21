from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class RerankItem:
    item_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class Reranker(Protocol):
    enabled: bool

    def rerank(self, query: str, items: list[RerankItem], top_n: int) -> list[RerankItem]:
        ...
