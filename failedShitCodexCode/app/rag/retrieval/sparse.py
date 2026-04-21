from __future__ import annotations

import math
import re
from collections import Counter

import jieba

from app.rag.vector_store.base import SparseVector


def tokenize_for_search(text: str) -> list[str]:
    lowered = text.lower()
    latin_tokens = re.findall(r"[a-z0-9]+", lowered)
    chinese_tokens = [token.strip() for token in jieba.cut(lowered) if token.strip() and re.search(r"[\u4e00-\u9fff]", token)]
    return [token for token in latin_tokens + chinese_tokens if len(token) > 1 or token.isdigit()]


def build_sparse_vector(text: str, vector_size: int) -> SparseVector:
    tokens = tokenize_for_search(text)
    if not tokens:
        return SparseVector(indices=[], values=[])

    frequencies = Counter(tokens)
    total = sum(frequencies.values())
    merged_weights: Counter[int] = Counter()
    for token, count in sorted(frequencies.items()):
        index = hash(token) % vector_size
        weight = 1.0 + math.log(count / total + 1.0)
        merged_weights[index] += weight
    indices = sorted(merged_weights)
    values = [merged_weights[index] for index in indices]
    return SparseVector(indices=indices, values=values)
