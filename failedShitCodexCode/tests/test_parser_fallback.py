from __future__ import annotations

from pathlib import Path

from app.rag.parsing.fallback import FallbackParser
from app.rag.parsing.models import ParseOptions, ParsedDocument
from app.rag.parsing.simple_parser import MinimalTextParser


class BrokenParser:
    def parse(self, path: str | Path, options: ParseOptions) -> ParsedDocument:
        raise RuntimeError("primary exploded")


def test_fallback_parser_uses_fallback_when_primary_fails(tmp_path) -> None:
    path = tmp_path / "manual.pdf"
    path.write_bytes("hello from fallback".encode("utf-8"))
    parser = FallbackParser(primary=BrokenParser(), fallback=MinimalTextParser())

    parsed = parser.parse(path, ParseOptions.from_profile("fast"))

    assert parsed.text == "hello from fallback"
    assert parsed.metadata["fallback_used"] is True
    assert parsed.metadata["primary_error"] == "primary exploded"
    assert parsed.metadata["fallback_parser"] == "MinimalTextParser"


def test_fallback_parser_can_prefer_fallback_for_pdf(tmp_path) -> None:
    path = tmp_path / "manual.pdf"
    path.write_bytes("hello from fallback".encode("utf-8"))
    parser = FallbackParser(primary=BrokenParser(), fallback=MinimalTextParser(), prefer_fallback_for_pdf=True)

    parsed = parser.parse(path, ParseOptions.from_profile("fast"))

    assert parsed.text == "hello from fallback"
    assert parsed.metadata["fallback_used"] is True
    assert parsed.metadata["primary_error"] == "skipped_for_pdf"


def test_minimal_text_parser_returns_empty_document_for_unreadable_path(tmp_path) -> None:
    path = tmp_path / "missing.pdf"

    parsed = MinimalTextParser().parse(path, ParseOptions.from_profile("fast"))

    assert parsed.text == ""
    assert parsed.blocks == []
    assert parsed.metadata["parser"] == "minimal_text"
    assert "fallback_error" in parsed.metadata
