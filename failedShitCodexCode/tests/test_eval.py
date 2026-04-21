from __future__ import annotations

import json

import httpx
import respx

from app.eval.dataset import load_eval_dataset
from app.eval.metrics import compute_hit_at_k, compute_mrr
from scripts.run_eval import build_eval_report


def test_eval_dataset_loader_reads_examples(tmp_path) -> None:
    dataset_path = tmp_path / "eval.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "query": "E101 怎么处理",
                    "expected_chunk_ids": ["chunk-1"],
                    "expected_answer_keywords": ["E101", "overheat"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dataset = load_eval_dataset(dataset_path)

    assert len(dataset) == 1
    assert dataset[0].query == "E101 怎么处理"


def test_eval_metrics_compute_hit_at_k_and_mrr() -> None:
    predictions = [
        ["chunk-1", "chunk-2"],
        ["chunk-3", "chunk-4"],
    ]
    targets = [
        ["chunk-1"],
        ["chunk-4"],
    ]

    assert compute_hit_at_k(predictions, targets, k=1) == 0.5
    assert compute_hit_at_k(predictions, targets, k=2) == 1.0
    assert compute_mrr(predictions, targets) == 0.75


@respx.mock
def test_eval_report_calls_rag_endpoints_and_aggregates_metrics(tmp_path) -> None:
    dataset_path = tmp_path / "eval.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "query": "E101 怎么处理",
                    "expected_chunk_ids": ["chunk-1"],
                    "expected_answer_keywords": ["e101", "overheat"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    respx.post("http://127.0.0.1:8000/rag/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "chunks": [
                    {"chunk_id": "chunk-1"},
                    {"chunk_id": "chunk-2"},
                ]
            },
        )
    )
    respx.post("http://127.0.0.1:8000/rag/answer").mock(
        return_value=httpx.Response(
            200,
            json={"answer": "E101 indicates overheat and requires cooling inspection."},
        )
    )

    report = build_eval_report(dataset_path, top_k=3)

    assert report["dataset_size"] == 1
    assert report["hit_at_1"] == 1.0
    assert report["hit_at_3"] == 1.0
    assert report["mrr"] == 1.0
    assert report["answer_keyword_hit_rate"] == 1.0
