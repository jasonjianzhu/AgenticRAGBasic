"""Abstract base classes and data models for document parsing."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class ParsedPage:
    """Content extracted from a single page."""

    page_number: int
    content: str


@dataclass
class ParsedTable:
    """A table extracted from the document."""

    content: str  # Markdown table representation
    page_number: int
    caption: str | None = None


@dataclass
class ContentSegment:
    """A text segment with its source page number.

    This is the key data structure for precise page attribution.
    Each segment is a piece of text (paragraph, heading, etc.)
    that comes from a known page in the source document.
    """

    text: str
    page_number: int


@dataclass
class ParsedDocument:
    """Result of parsing a document.

    Attributes:
        content: Full extracted text (markdown format, for backward compat).
        pages: Per-page content.
        tables: Extracted tables with page numbers.
        segments: Ordered list of text segments with page attribution.
                  This is the primary data source for chunking.
        metadata: Parser metadata.
    """

    content: str
    pages: list[ParsedPage]
    tables: list[ParsedTable]
    segments: list[ContentSegment] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary suitable for JSON encoding."""
        return {
            "content": self.content,
            "pages": [
                {"page_number": p.page_number, "content": p.content}
                for p in self.pages
            ],
            "tables": [
                {"content": t.content, "page_number": t.page_number, "caption": t.caption}
                for t in self.tables
            ],
            "segments": [
                {"text": s.text, "page_number": s.page_number}
                for s in self.segments
            ],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ParsedDocument:
        """Deserialize from a plain dictionary."""
        return cls(
            content=data["content"],
            pages=[
                ParsedPage(page_number=p["page_number"], content=p["content"])
                for p in data.get("pages", [])
            ],
            tables=[
                ParsedTable(
                    content=t["content"],
                    page_number=t["page_number"],
                    caption=t.get("caption"),
                )
                for t in data.get("tables", [])
            ],
            segments=[
                ContentSegment(text=s["text"], page_number=s["page_number"])
                for s in data.get("segments", [])
            ],
            metadata=data.get("metadata", {}),
        )


class DocumentParser(abc.ABC):
    """Abstract base class for document parsers."""

    @abc.abstractmethod
    async def parse(self, file_path: str, profile: str = "balanced") -> ParsedDocument:
        """Parse a document file and return structured content."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Parser name identifier."""
