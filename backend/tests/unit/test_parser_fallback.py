"""Tests for the fallback (pypdfium2) parser (S5-03)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from app.knowledge.rag.parsing.base import ParsedDocument
from app.knowledge.rag.parsing.fallback import FallbackParser


def _create_minimal_pdf(text: str = "Hello World", num_pages: int = 1) -> bytes:
    """Create a minimal valid PDF with text content.

    Uses raw PDF bytes. For multi-page, duplicates the page object.
    Returns raw PDF bytes that pypdfium2 can read back.
    """
    # Simple single-page PDF with text
    if num_pages == 1:
        return (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
            b"4 0 obj\n<< /Length 44 >>\nstream\n"
            b"BT /F1 12 Tf 72 720 Td (Hello World) Tj ET\n"
            b"endstream\nendobj\n"
            b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
            b"xref\n0 6\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"0000000266 00000 n \n"
            b"0000000362 00000 n \n"
            b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
            b"startxref\n443\n%%EOF\n"
        )
    else:
        # Multi-page: build dynamically
        # For simplicity, use pypdfium2 to create multi-page PDFs
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument.new()
        for _ in range(num_pages):
            pdf.new_page(612, 792).close()
        raw = pdf.save()
        pdf.close()
        return raw


def _create_raw_minimal_pdf() -> bytes:
    """Create a minimal PDF from raw bytes (no text, but valid structure).

    This is the simplest possible valid PDF that pypdfium2 can open.
    """
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n196\n%%EOF\n"
    )


@pytest.fixture
def fallback_parser() -> FallbackParser:
    return FallbackParser()


class TestFallbackParserProperties:
    def test_name(self, fallback_parser: FallbackParser):
        assert fallback_parser.name == "fallback_pypdfium2"

    def test_is_document_parser(self, fallback_parser: FallbackParser):
        from app.knowledge.rag.parsing.base import DocumentParser
        assert isinstance(fallback_parser, DocumentParser)


class TestFallbackParserParse:
    @pytest.mark.asyncio
    async def test_parse_minimal_raw_pdf(self, fallback_parser: FallbackParser, tmp_path: Path):
        """Parse a minimal raw PDF (no text content)."""
        pdf_path = tmp_path / "empty.pdf"
        pdf_path.write_bytes(_create_raw_minimal_pdf())

        result = await fallback_parser.parse(str(pdf_path))

        assert isinstance(result, ParsedDocument)
        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1
        assert result.tables == []
        assert result.metadata["parser_name"] == "fallback_pypdfium2"
        assert result.metadata["profile"] == "fallback"
        assert result.metadata["page_count"] == 1

    @pytest.mark.asyncio
    async def test_parse_file_not_found(self, fallback_parser: FallbackParser):
        with pytest.raises(FileNotFoundError, match="File not found"):
            await fallback_parser.parse("/nonexistent/path/doc.pdf")

    @pytest.mark.asyncio
    async def test_parse_returns_parsed_document(self, fallback_parser: FallbackParser, tmp_path: Path):
        """Result is a proper ParsedDocument with expected metadata."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(_create_raw_minimal_pdf())

        result = await fallback_parser.parse(str(pdf_path))

        assert isinstance(result, ParsedDocument)
        assert isinstance(result.content, str)
        assert isinstance(result.pages, list)
        assert isinstance(result.tables, list)
        assert isinstance(result.metadata, dict)

    @pytest.mark.asyncio
    async def test_profile_ignored(self, fallback_parser: FallbackParser, tmp_path: Path):
        """Profile parameter is accepted but ignored in fallback parser."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(_create_raw_minimal_pdf())

        result = await fallback_parser.parse(str(pdf_path), profile="accurate")

        # Profile is always 'fallback' regardless of input
        assert result.metadata["profile"] == "fallback"

    @pytest.mark.asyncio
    async def test_no_tables_extracted(self, fallback_parser: FallbackParser, tmp_path: Path):
        """Fallback parser never extracts tables."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(_create_raw_minimal_pdf())

        result = await fallback_parser.parse(str(pdf_path))
        assert result.tables == []

    @pytest.mark.asyncio
    async def test_page_numbers_are_one_indexed(self, fallback_parser: FallbackParser, tmp_path: Path):
        """Page numbers should start at 1, not 0."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(_create_raw_minimal_pdf())

        result = await fallback_parser.parse(str(pdf_path))
        assert result.pages[0].page_number == 1
