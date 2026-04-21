from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class EvalExample:
    query: str
    expected_chunk_ids: list[str] = field(default_factory=list)
    expected_answer_keywords: list[str] = field(default_factory=list)


def load_eval_dataset(path: str | Path) -> list[EvalExample]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        EvalExample(
            query=item["query"],
            expected_chunk_ids=item.get("expected_chunk_ids", []),
            expected_answer_keywords=item.get("expected_answer_keywords", []),
        )
        for item in payload
    ]
