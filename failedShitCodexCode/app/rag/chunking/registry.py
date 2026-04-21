from __future__ import annotations

from dataclasses import dataclass, field

from app.rag.chunking.base import Chunker
from app.rag.chunking.docling_hybrid import DoclingHybridChunker
from app.rag.chunking.markdown_header import MarkdownHeaderChunker
from app.rag.chunking.recursive_token import RecursiveTokenChunker
from app.rag.chunking.table import TableChunker


@dataclass
class ChunkerRegistry:
    chunkers: dict[str, Chunker] = field(default_factory=dict)
    default_mapping: dict[str, str] = field(default_factory=dict)
    fallback_name: str = "recursive_token"

    def register(self, chunker: Chunker) -> None:
        self.chunkers[chunker.name] = chunker

    def select(self, document_type: str, preferred: str | None = None) -> Chunker:
        chunker_name = preferred or self.default_mapping.get(document_type, self.fallback_name)
        try:
            return self.chunkers[chunker_name]
        except KeyError as exc:
            raise ValueError(f"Chunker not registered: {chunker_name}") from exc


def build_default_chunker_registry() -> ChunkerRegistry:
    registry = ChunkerRegistry(
        default_mapping={
            "manual": "docling_hybrid",
            "spec": "docling_hybrid",
            "faq": "markdown_header",
            "qa": "markdown_header",
            "unknown": "recursive_token",
        }
    )
    registry.register(DoclingHybridChunker())
    registry.register(MarkdownHeaderChunker())
    registry.register(RecursiveTokenChunker())
    registry.chunkers["table"] = TableChunker()
    return registry
