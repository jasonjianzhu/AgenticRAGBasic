"""Fallback document parser using pypdfium2 for plain text extraction.

Used when the primary Docling parser fails. Extracts raw text page-by-page
without table detection or structural analysis.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pypdfium2

from app.core.logging import get_logger
from app.rag.parsing.base import DocumentParser, ParsedDocument, ParsedPage, ParsedTable

logger = get_logger(__name__)


def _extract_with_pypdfium2(file_path: str) -> ParsedDocument:
    """Synchronous text extraction using pypdfium2."""
    from app.rag.parsing.base import ContentSegment

    pdf = pypdfium2.PdfDocument(file_path)
    pages: list[ParsedPage] = []
    segments: list[ContentSegment] = []
    all_text_parts: list[str] = []

    try:
        for i in range(len(pdf)):
            page = pdf[i]
            text_page = page.get_textpage()
            text = text_page.get_text_bounded()
            text_page.close()
            page.close()

            page_num = i + 1
            pages.append(ParsedPage(page_number=page_num, content=text))
            if text.strip():
                all_text_parts.append(text)
                # Each page's text is one segment
                segments.append(ContentSegment(text=text, page_number=page_num))
    finally:
        pdf.close()

    content = "\n\n".join(all_text_parts)

    metadata = {
        "parser_name": "fallback_pypdfium2",
        "profile": "fallback",
        "page_count": len(pages),
    }

    return ParsedDocument(
        content=content,
        pages=pages,
        tables=[],
        segments=segments,
        metadata=metadata,
    )


class FallbackParser(DocumentParser):
    """Plain-text PDF parser using pypdfium2.

    Extracts text page-by-page without any structural analysis or table
    detection. Intended as a fallback when Docling fails.
    """

    @property
    def name(self) -> str:
        return "fallback_pypdfium2"

    async def parse(self, file_path: str, profile: str = "balanced") -> ParsedDocument:
        """Extract plain text from a PDF.

        The *profile* parameter is accepted for interface compatibility but
        is ignored – fallback always uses simple text extraction.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info("fallback_parse_start", file_path=file_path)

        try:
            parsed = await asyncio.to_thread(_extract_with_pypdfium2, file_path)
        except Exception:
            logger.exception("fallback_parse_failed", file_path=file_path)
            raise

        logger.info(
            "fallback_parse_complete",
            file_path=file_path,
            page_count=len(parsed.pages),
            content_length=len(parsed.content),
        )
        return parsed
