"""Integration tests for DoclingParser (S5-02).

These tests require docling model files to be downloaded and are
therefore marked with ``@pytest.mark.integration``. They are skipped
by default in CI; run manually with::

    pytest -m integration backend/tests/integration/test_parser_docling.py -v
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.rag.parsing.base import ParsedDocument
from app.rag.parsing.docling_parser import DoclingParser, VALID_PROFILES


def _create_simple_pdf(tmp_path: Path) -> Path:
    """Create a simple one-page PDF for integration testing.

    Uses raw PDF bytes with a minimal text stream that docling can parse.
    """
    # Minimal PDF with one page containing text content
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 72 720 Td (Hello Docling) Tj ET\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000360 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n441\n%%EOF\n"
    )
    pdf_path = tmp_path / "integration_test.pdf"
    pdf_path.write_bytes(pdf_bytes)
    return pdf_path


@pytest.fixture
def docling_parser() -> DoclingParser:
    return DoclingParser()


@pytest.mark.integration
class TestDoclingParserIntegration:
    @pytest.mark.asyncio
    async def test_parse_fast_profile(self, docling_parser: DoclingParser, tmp_path: Path):
        pdf_path = _create_simple_pdf(tmp_path)
        result = await docling_parser.parse(str(pdf_path), profile="fast")

        assert isinstance(result, ParsedDocument)
        assert result.metadata["parser_name"] == "docling"
        assert result.metadata["profile"] == "fast"
        assert result.metadata["page_count"] >= 1

    @pytest.mark.asyncio
    async def test_parse_balanced_profile(self, docling_parser: DoclingParser, tmp_path: Path):
        pdf_path = _create_simple_pdf(tmp_path)
        result = await docling_parser.parse(str(pdf_path), profile="balanced")

        assert isinstance(result, ParsedDocument)
        assert result.metadata["profile"] == "balanced"

    @pytest.mark.asyncio
    async def test_parse_accurate_profile(self, docling_parser: DoclingParser, tmp_path: Path):
        pdf_path = _create_simple_pdf(tmp_path)
        result = await docling_parser.parse(str(pdf_path), profile="accurate")

        assert isinstance(result, ParsedDocument)
        assert result.metadata["profile"] == "accurate"

    @pytest.mark.asyncio
    async def test_invalid_profile_raises(self, docling_parser: DoclingParser):
        with pytest.raises(ValueError, match="Invalid profile"):
            await docling_parser.parse("/tmp/fake.pdf", profile="turbo")

    @pytest.mark.asyncio
    async def test_file_not_found_raises(self, docling_parser: DoclingParser):
        with pytest.raises(FileNotFoundError):
            await docling_parser.parse("/nonexistent/file.pdf")


class TestDoclingParserUnit:
    """Unit tests that don't require model downloads."""

    def test_name(self):
        parser = DoclingParser()
        assert parser.name == "docling"

    def test_valid_profiles(self):
        assert VALID_PROFILES == {"fast", "balanced", "accurate"}

    @pytest.mark.asyncio
    async def test_invalid_profile_raises(self):
        parser = DoclingParser()
        with pytest.raises(ValueError, match="Invalid profile"):
            await parser.parse("/tmp/fake.pdf", profile="invalid")

    @pytest.mark.asyncio
    async def test_file_not_found_raises(self):
        parser = DoclingParser()
        with pytest.raises(FileNotFoundError, match="File not found"):
            await parser.parse("/nonexistent/path/doc.pdf")
