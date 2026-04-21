from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DocumentClassification:
    document_type: str
    confidence: float
    strategy: str
    metadata: dict[str, Any] = field(default_factory=dict)
