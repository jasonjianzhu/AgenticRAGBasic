from __future__ import annotations

from app.rag.chunking.models import ChunkDraft, ChunkingOptions
from app.rag.chunking.utils import chunk_text
from app.rag.parsing.models import ParsedDocument


class RecursiveTokenChunker:
    name = "recursive_token"

    def chunk(self, document: ParsedDocument, options: ChunkingOptions) -> list[ChunkDraft]:
        return [
            ChunkDraft(chunk_type="text", content=chunk)
            for chunk in chunk_text(document.text, target_chars=options.target_chars, overlap_chars=options.overlap_chars)
        ]
