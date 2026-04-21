from __future__ import annotations

import json
from pathlib import Path
import sys
from collections.abc import Sequence

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.eval.dataset import load_eval_dataset
from app.eval.metrics import compute_hit_at_k, compute_mrr


def build_eval_report(
    dataset_path: Path,
    *,
    base_url: str = "http://127.0.0.1:8000",
    top_k: int = 3,
) -> dict[str, object]:
    dataset = load_eval_dataset(dataset_path)
    predictions: list[list[str]] = []
    targets = [example.expected_chunk_ids[:] for example in dataset]
    answer_keyword_hits = 0

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        for example in dataset:
            search_payload = client.post(
                "/rag/search",
                json={"query": example.query, "top_k": top_k, "use_reranker": True},
            )
            search_payload.raise_for_status()
            search_data = search_payload.json()
            predicted_chunk_ids = [item["chunk_id"] for item in search_data.get("chunks", [])]
            predictions.append(predicted_chunk_ids)

            answer_payload = client.post(
                "/rag/answer",
                json={"query": example.query, "top_k": top_k, "use_reranker": True},
            )
            answer_payload.raise_for_status()
            answer_text = answer_payload.json().get("answer", "")
            if _contains_all_keywords(answer_text, example.expected_answer_keywords):
                answer_keyword_hits += 1

    return {
        "dataset_size": len(dataset),
        "hit_at_1": compute_hit_at_k(predictions, targets, k=1),
        "hit_at_3": compute_hit_at_k(predictions, targets, k=3),
        "mrr": compute_mrr(predictions, targets),
        "answer_keyword_hit_rate": (answer_keyword_hits / len(dataset)) if dataset else 0.0,
    }


def main() -> None:
    dataset_path = ROOT / "data" / "eval_phase1.json"
    report = build_eval_report(dataset_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _contains_all_keywords(answer: str, keywords: Sequence[str]) -> bool:
    if not keywords:
        return True
    lowered = answer.lower()
    return all(keyword.lower() in lowered for keyword in keywords)


if __name__ == "__main__":
    main()
