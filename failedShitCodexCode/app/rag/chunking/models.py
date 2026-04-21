from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChunkingOptions:
    target_chars: int = 1600
    overlap_chars: int = 240


@dataclass(frozen=True)
class ChunkDraft:
    chunk_type: str
    content: str
    section_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
