from __future__ import annotations


def compute_hit_at_k(predictions: list[list[str]], targets: list[list[str]], k: int) -> float:
    if not predictions:
        return 0.0
    hits = 0
    for predicted, expected in zip(predictions, targets, strict=False):
        if set(predicted[:k]) & set(expected):
            hits += 1
    return hits / len(predictions)


def compute_mrr(predictions: list[list[str]], targets: list[list[str]]) -> float:
    if not predictions:
        return 0.0
    reciprocal_ranks: list[float] = []
    for predicted, expected in zip(predictions, targets, strict=False):
        rank = 0.0
        for index, chunk_id in enumerate(predicted, start=1):
            if chunk_id in expected:
                rank = 1 / index
                break
        reciprocal_ranks.append(rank)
    return sum(reciprocal_ranks) / len(reciprocal_ranks)
