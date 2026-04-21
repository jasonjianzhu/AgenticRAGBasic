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
class ParsedDocument:
    """Result of parsing a document.

    Holds the full extracted text (in markdown format), per-page content,
    extracted tables, and parser metadata.
    """

    content: str  # Full extracted text (markdown format)
    pages: list[ParsedPage]  # Per-page content
    tables: list[ParsedTable]  # Extracted tables
    metadata: dict = field(default_factory=dict)  # Parser metadata

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary suitable for JSON encoding."""
        return {
            "content": self.content,
            "pages": [
                {"page_number": p.page_number, "content": p.content}
                for p in self.pages
            ],
            "tables": [
                {
                    "content": t.content,
                    "page_number": t.page_number,
                    "caption": t.caption,
                }
                for t in self.tables
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
            metadata=data.get("metadata", {}),
        )


class DocumentParser(abc.ABC):
    """Abstract base class for document parsers."""

    @abc.abstractmethod
    async def parse(self, file_path: str, profile: str = "balanced") -> ParsedDocument:
        """Parse a document file and return structured content.

        Args:
            file_path: Path to the document file on disk.
            profile: Parsing profile (fast, balanced, accurate).

        Returns:
            A ParsedDocument with extracted content.
        """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Parser name identifier."""
