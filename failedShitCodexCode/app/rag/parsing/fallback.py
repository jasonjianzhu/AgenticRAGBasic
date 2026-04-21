from __future__ import annotations

from pathlib import Path

from app.rag.parsing.base import DocumentParser
from app.rag.parsing.models import ParseOptions, ParsedDocument


class FallbackParser:
    def __init__(self, primary: DocumentParser, fallback: DocumentParser, *, prefer_fallback_for_pdf: bool = False):
        self.primary = primary
        self.fallback = fallback
        self.prefer_fallback_for_pdf = prefer_fallback_for_pdf

    def parse(self, path: str | Path, options: ParseOptions) -> ParsedDocument:
        source_path = Path(path)
        if self.prefer_fallback_for_pdf and source_path.suffix.lower() == ".pdf":
            parsed = self.fallback.parse(source_path, options)
            return ParsedDocument(
                source_path=parsed.source_path,
                text=parsed.text,
                blocks=parsed.blocks,
                metadata={
                    **parsed.metadata,
                    "fallback_used": True,
                    "primary_parser": self.primary.__class__.__name__,
                    "fallback_parser": self.fallback.__class__.__name__,
                    "primary_error": "skipped_for_pdf",
                },
            )
        try:
            return self.primary.parse(source_path, options)
        except Exception as exc:
            parsed = self.fallback.parse(source_path, options)
            return ParsedDocument(
                source_path=parsed.source_path,
                text=parsed.text,
                blocks=parsed.blocks,
                metadata={
                    **parsed.metadata,
                    "fallback_used": True,
                    "primary_parser": self.primary.__class__.__name__,
                    "fallback_parser": self.fallback.__class__.__name__,
                    "primary_error": str(exc),
                },
            )
