from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from app.rag.rerank.base import Reranker
from app.rag.rerank.local import TransformersCrossEncoderReranker
from app.rag.rerank.simple import SimpleReranker


class LazyLocalReranker:
    def __init__(
        self,
        *,
        enabled: bool,
        model_name: str,
        factory: Callable[[str], Reranker] | None = None,
    ):
        self.enabled = enabled
        self.model_name = model_name
        self._factory = factory or (lambda name: TransformersCrossEncoderReranker(model_name=name, enabled=enabled))
        self._delegate: Reranker | None = None

    def rerank(self, query: str, items, top_n: int):
        delegate = self._get_delegate()
        return delegate.rerank(query, items, top_n)

    def _get_delegate(self) -> Reranker:
        if self._delegate is None:
            self._delegate = self._factory(self.model_name)
        return self._delegate


def build_reranker(settings: Settings) -> Reranker:
    if not settings.reranker_enabled:
        return SimpleReranker(enabled=False)
    if settings.reranker_backend == "simple":
        return SimpleReranker(enabled=True)
    if settings.reranker_backend == "local":
        return LazyLocalReranker(enabled=True, model_name=settings.reranker_model_name)
    raise ValueError(f"Unsupported reranker backend: {settings.reranker_backend}")
