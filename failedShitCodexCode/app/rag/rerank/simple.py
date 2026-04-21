from __future__ import annotations

from app.rag.rerank.base import RerankItem
from app.rag.retrieval.sparse import tokenize_for_search


class SimpleReranker:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def rerank(self, query: str, items: list[RerankItem], top_n: int) -> list[RerankItem]:
        if not self.enabled:
            return items[:top_n]

        query_terms = _tokenize(query)
        rescored = []
        for item in items:
            lexical = _lexical_overlap(query_terms, item.content)
            rescored.append(
                RerankItem(
                    item_id=item.item_id,
                    content=item.content,
                    score=(item.score * 0.6) + (lexical * 0.4),
                    metadata=item.metadata,
                )
            )
        rescored.sort(key=lambda item: item.score, reverse=True)
        return rescored[:top_n]


def _tokenize(text: str) -> set[str]:
    return set(tokenize_for_search(text))


def _lexical_overlap(query_terms: set[str], content: str) -> float:
    if not query_terms:
        return 0.0
    content_terms = _tokenize(content)
    if not content_terms:
        return 0.0
    return len(query_terms & content_terms) / len(query_terms)
