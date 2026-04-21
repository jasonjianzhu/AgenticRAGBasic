from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from typing import Any

import os

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.rag.rerank.base import RerankItem


ModelLoader = Callable[[str, str], tuple[Any, Any]]


class TransformersCrossEncoderReranker:
    def __init__(
        self,
        *,
        model_name: str,
        enabled: bool = True,
        device: str | None = None,
        max_length: int = 512,
        loader: ModelLoader | None = None,
    ) -> None:
        self.model_name = model_name
        self.enabled = enabled
        self.device = device or _resolve_device()
        self.max_length = max_length
        self._loader = loader or _load_model
        self._tokenizer = None
        self._model = None

    def rerank(self, query: str, items: list[RerankItem], top_n: int) -> list[RerankItem]:
        if not self.enabled:
            return items[:top_n]
        if not items:
            return []

        tokenizer, model = self._get_model_components()
        pairs = [[query, item.content] for item in items]
        inputs = tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        inference_context = torch.no_grad()
        with inference_context:
            outputs = model(**inputs)
        scores = outputs.logits.view(-1).float().cpu().tolist()
        reranked = [
            RerankItem(
                item_id=item.item_id,
                content=item.content,
                score=float(score),
                metadata=item.metadata,
            )
            for item, score in zip(items, scores, strict=False)
        ]
        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked[:top_n]

    def _get_model_components(self):
        if self._tokenizer is None or self._model is None:
            self._tokenizer, self._model = self._loader(self.model_name, self.device)
        return self._tokenizer, self._model


def _resolve_device() -> str:
    if torch.backends.mps.is_available():
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_model(model_name: str, device: str):
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    model.to(device)
    model.eval()
    return tokenizer, model
