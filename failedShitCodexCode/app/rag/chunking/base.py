from __future__ import annotations

from typing import Protocol

from app.rag.chunking.models import ChunkDraft, ChunkingOptions
from app.rag.parsing.models import ParsedDocument


class Chunker(Protocol):
    name: str

    def chunk(self, document: ParsedDocument, options: ChunkingOptions) -> list[ChunkDraft]:
        ...
