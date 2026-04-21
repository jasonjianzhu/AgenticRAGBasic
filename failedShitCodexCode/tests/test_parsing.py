from __future__ import annotations

import subprocess

import pytest

from app.rag.parsing.docling_parser import DoclingParser
from app.rag.parsing.models import ParseOptions, ParserProfile, ParsedBlockType
from app.rag.parsing.simple_parser import MinimalTextParser, SimpleTextParser, _sanitize_text


def test_parse_options_from_profiles() -> None:
    fast = ParseOptions.from_profile(ParserProfile.FAST)
    balanced = ParseOptions.from_profile(ParserProfile.BALANCED)
    accurate = ParseOptions.from_profile(ParserProfile.ACCURATE)

    assert fast.extract_tables is False
    assert fast.run_ocr is False
    assert balanced.extract_tables is True
    assert balanced.run_ocr is False
    assert accurate.extract_tables is True
    assert accurate.run_ocr is True
    assert accurate.extract_figures is True


def test_simple_text_parser_returns_blocks(tmp_path) -> None:
    path = tmp_path / "manual.txt"
    path.write_text("Intro\n\nAlarm table", encoding="utf-8")

    parsed = SimpleTextParser().parse(path, ParseOptions.from_profile("fast"))

    assert parsed.metadata["parser"] == "simple_text"
    assert [block.text for block in parsed.blocks] == ["Intro", "Alarm table"]


def test_docling_markdown_block_guessing() -> None:
    parser = DoclingParser()

    table_block = parser._guess_block_type("| A | B |\n|---|---|")
    text_block = parser._guess_block_type("Battery system overview")

    assert table_block == ParsedBlockType.TABLE
    assert text_block == ParsedBlockType.TEXT


def test_minimal_text_parser_decodes_bytes_with_errors_ignored(tmp_path) -> None:
    path = tmp_path / "manual.pdf"
    path.write_bytes(b"hello\xff world")

    parsed = MinimalTextParser().parse(path, ParseOptions.from_profile("fast"))

    assert "hello" in parsed.text
    assert parsed.metadata["parser"] == "minimal_text"


def test_minimal_text_parser_uses_pdftotext_for_pdf_when_available(tmp_path, monkeypatch) -> None:
    path = tmp_path / "manual.pdf"
    path.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr("app.rag.parsing.simple_parser.which", lambda _: "/opt/homebrew/bin/pdftotext")

    def fake_run(cmd, check, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="Title\n\nSection body\x00", stderr="")

    monkeypatch.setattr("app.rag.parsing.simple_parser.subprocess.run", fake_run)

    parsed = MinimalTextParser().parse(path, ParseOptions.from_profile("fast"))

    assert parsed.text == "Title\n\nSection body"
    assert parsed.metadata["extractor"] == "pdftotext"


def test_minimal_text_parser_falls_back_to_bytes_when_pdftotext_fails(tmp_path, monkeypatch) -> None:
    path = tmp_path / "manual.pdf"
    path.write_bytes(b"hello\x00world")

    monkeypatch.setattr("app.rag.parsing.simple_parser.which", lambda _: "/opt/homebrew/bin/pdftotext")

    def fake_run(cmd, check, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr("app.rag.parsing.simple_parser.subprocess.run", fake_run)

    parsed = MinimalTextParser().parse(path, ParseOptions.from_profile("fast"))

    assert parsed.text == "helloworld"
    assert parsed.metadata["extractor"] == "bytes_decode"


def test_sanitize_text_removes_nul_and_control_chars() -> None:
    cleaned = _sanitize_text("a\x00b\x07c\nok\tkeep")

    assert cleaned == "abc\nok\tkeep"
