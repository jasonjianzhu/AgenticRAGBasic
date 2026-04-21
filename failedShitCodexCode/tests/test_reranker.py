from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.rag.rerank.base import RerankItem
from app.rag.rerank.local import TransformersCrossEncoderReranker
from app.rag.rerank.factory import LazyLocalReranker, build_reranker
from app.rag.rerank.simple import SimpleReranker


class FakeTensor:
    def __init__(self, value: Any) -> None:
        self.value = value
        self.device: str | None = None

    def to(self, device: str):
        self.device = device
        return self


class FakeTokenizer:
    def __init__(self) -> None:
        self.pairs: list[list[str]] | None = None
        self.max_length: int | None = None

    def __call__(
        self,
        pairs: list[list[str]],
        *,
        padding: bool,
        truncation: bool,
        max_length: int,
        return_tensors: str,
    ) -> dict[str, FakeTensor]:
        self.pairs = pairs
        self.max_length = max_length
        return {
            "input_ids": FakeTensor(pairs),
            "attention_mask": FakeTensor(pairs),
        }


class FakeLogits:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores

    def view(self, *_args):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def tolist(self) -> list[float]:
        return self.scores


class FakeModel:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.device: str | None = None
        self.calls: list[dict[str, FakeTensor]] = []

    def to(self, device: str):
        self.device = device
        return self

    def eval(self):
        return self

    def __call__(self, **inputs):
        self.calls.append(inputs)
        return type("FakeOutput", (), {"logits": FakeLogits(self.scores)})()


def test_simple_reranker_can_be_disabled() -> None:
    reranker = SimpleReranker(enabled=False)
    items = [
        RerankItem(item_id="1", content="battery alarm", score=0.2, metadata={}),
        RerankItem(item_id="2", content="maintenance guide", score=0.9, metadata={}),
    ]

    reranked = reranker.rerank("battery alarm", items, top_n=2)

    assert [item.item_id for item in reranked] == ["1", "2"]


def test_simple_reranker_promotes_lexically_relevant_items() -> None:
    reranker = SimpleReranker(enabled=True)
    items = [
        RerankItem(item_id="1", content="maintenance guide", score=0.9, metadata={}),
        RerankItem(item_id="2", content="battery overheat alarm handling", score=0.4, metadata={}),
    ]

    reranked = reranker.rerank("overheat alarm", items, top_n=2)

    assert reranked[0].item_id == "2"


def test_build_reranker_can_disable_reranking() -> None:
    settings = Settings(RERANKER_ENABLED=False)
    reranker = build_reranker(settings)

    reranked = reranker.rerank(
        "battery alarm",
        [RerankItem(item_id="1", content="battery alarm", score=0.5)],
        top_n=1,
    )

    assert reranker.enabled is False
    assert reranked[0].item_id == "1"


def test_lazy_local_reranker_delays_delegate_creation() -> None:
    created = []

    def fake_factory(model_name: str):
        created.append(model_name)
        return SimpleReranker(enabled=True)

    reranker = LazyLocalReranker(enabled=True, model_name="dummy", factory=fake_factory)

    assert reranker._delegate is None

    reranked = reranker.rerank(
        "overheat alarm",
        [RerankItem(item_id="1", content="overheat alarm", score=0.5)],
        top_n=1,
    )

    assert reranker._delegate is not None
    assert created == ["dummy"]
    assert reranked[0].item_id == "1"


def test_transformers_cross_encoder_reranker_uses_model_scores() -> None:
    tokenizer = FakeTokenizer()
    model = FakeModel(scores=[0.2, 1.7, -0.3])

    def fake_loader(model_name: str, device: str):
        assert model_name == "BAAI/bge-reranker-v2-m3"
        assert device == "cpu"
        return tokenizer, model

    reranker = TransformersCrossEncoderReranker(
        model_name="BAAI/bge-reranker-v2-m3",
        device="cpu",
        loader=fake_loader,
    )
    items = [
        RerankItem(item_id="1", content="maintenance guide", score=0.9, metadata={}),
        RerankItem(item_id="2", content="battery overheat alarm handling", score=0.1, metadata={}),
        RerankItem(item_id="3", content="wiring inspection", score=0.8, metadata={}),
    ]

    reranked = reranker.rerank("overheat alarm", items, top_n=2)

    assert [item.item_id for item in reranked] == ["2", "1"]
    assert tokenizer.pairs == [
        ["overheat alarm", "maintenance guide"],
        ["overheat alarm", "battery overheat alarm handling"],
        ["overheat alarm", "wiring inspection"],
    ]
    assert tokenizer.max_length == 512
    assert model.calls


def test_transformers_cross_encoder_reranker_skips_model_when_disabled() -> None:
    created = []

    def fake_loader(model_name: str, device: str):
        created.append((model_name, device))
        raise AssertionError("loader should not be called when reranker is disabled")

    reranker = TransformersCrossEncoderReranker(
        model_name="BAAI/bge-reranker-v2-m3",
        enabled=False,
        loader=fake_loader,
    )
    items = [
        RerankItem(item_id="1", content="battery alarm", score=0.2, metadata={}),
        RerankItem(item_id="2", content="maintenance guide", score=0.9, metadata={}),
    ]

    reranked = reranker.rerank("battery alarm", items, top_n=1)

    assert [item.item_id for item in reranked] == ["1"]
    assert created == []
