"""Tests for the parser interface and ParsedDocument dataclass (S5-01)."""
from __future__ import annotations

import pytest

from app.knowledge.rag.parsing.base import (
    DocumentParser,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
)


# ---------------------------------------------------------------------------
# ParsedPage dataclass
# ---------------------------------------------------------------------------

class TestParsedPage:
    def test_create(self):
        page = ParsedPage(page_number=1, content="Hello world")
        assert page.page_number == 1
        assert page.content == "Hello world"

    def test_empty_content(self):
        page = ParsedPage(page_number=0, content="")
        assert page.content == ""


# ---------------------------------------------------------------------------
# ParsedTable dataclass
# ---------------------------------------------------------------------------

class TestParsedTable:
    def test_create_with_caption(self):
        table = ParsedTable(content="| A | B |", page_number=3, caption="Table 1")
        assert table.content == "| A | B |"
        assert table.page_number == 3
        assert table.caption == "Table 1"

    def test_create_without_caption(self):
        table = ParsedTable(content="| X |", page_number=1)
        assert table.caption is None


# ---------------------------------------------------------------------------
# ParsedDocument dataclass
# ---------------------------------------------------------------------------

class TestParsedDocument:
    def _make_doc(self) -> ParsedDocument:
        return ParsedDocument(
            content="# Title\n\nSome text",
            pages=[
                ParsedPage(page_number=1, content="Page one text"),
                ParsedPage(page_number=2, content="Page two text"),
            ],
            tables=[
                ParsedTable(content="| H1 | H2 |\n|---|---|\n| a | b |", page_number=1, caption="My Table"),
                ParsedTable(content="| X |", page_number=2),
            ],
            metadata={"parser_name": "test", "profile": "balanced"},
        )

    def test_fields(self):
        doc = self._make_doc()
        assert doc.content.startswith("# Title")
        assert len(doc.pages) == 2
        assert len(doc.tables) == 2
        assert doc.metadata["parser_name"] == "test"

    def test_default_metadata(self):
        doc = ParsedDocument(content="", pages=[], tables=[])
        assert doc.metadata == {}

    def test_to_dict(self):
        doc = self._make_doc()
        d = doc.to_dict()
        assert d["content"] == doc.content
        assert len(d["pages"]) == 2
        assert d["pages"][0]["page_number"] == 1
        assert d["pages"][0]["content"] == "Page one text"
        assert len(d["tables"]) == 2
        assert d["tables"][0]["caption"] == "My Table"
        assert d["tables"][1]["caption"] is None
        assert d["metadata"]["parser_name"] == "test"

    def test_from_dict(self):
        original = self._make_doc()
        d = original.to_dict()
        restored = ParsedDocument.from_dict(d)

        assert restored.content == original.content
        assert len(restored.pages) == len(original.pages)
        for rp, op in zip(restored.pages, original.pages):
            assert rp.page_number == op.page_number
            assert rp.content == op.content
        assert len(restored.tables) == len(original.tables)
        for rt, ot in zip(restored.tables, original.tables):
            assert rt.content == ot.content
            assert rt.page_number == ot.page_number
            assert rt.caption == ot.caption
        assert restored.metadata == original.metadata

    def test_roundtrip_empty(self):
        doc = ParsedDocument(content="", pages=[], tables=[])
        restored = ParsedDocument.from_dict(doc.to_dict())
        assert restored.content == ""
        assert restored.pages == []
        assert restored.tables == []
        assert restored.metadata == {}

    def test_from_dict_missing_optional_fields(self):
        """from_dict should handle missing 'pages', 'tables', 'metadata' gracefully."""
        data = {"content": "hello"}
        doc = ParsedDocument.from_dict(data)
        assert doc.content == "hello"
        assert doc.pages == []
        assert doc.tables == []
        assert doc.metadata == {}

    def test_to_dict_unicode(self):
        """Ensure unicode content survives serialization."""
        doc = ParsedDocument(
            content="电池过温告警处理",
            pages=[ParsedPage(page_number=1, content="中文内容")],
            tables=[],
            metadata={"lang": "zh"},
        )
        d = doc.to_dict()
        restored = ParsedDocument.from_dict(d)
        assert restored.content == "电池过温告警处理"
        assert restored.pages[0].content == "中文内容"


# ---------------------------------------------------------------------------
# DocumentParser ABC
# ---------------------------------------------------------------------------

class TestDocumentParserABC:
    def test_cannot_instantiate(self):
        """DocumentParser is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            DocumentParser()  # type: ignore[abstract]

    def test_concrete_subclass(self):
        """A concrete subclass implementing all abstract methods works."""

        class DummyParser(DocumentParser):
            @property
            def name(self) -> str:
                return "dummy"

            async def parse(self, file_path: str, profile: str = "balanced") -> ParsedDocument:
                return ParsedDocument(content="", pages=[], tables=[])

        parser = DummyParser()
        assert parser.name == "dummy"

    def test_incomplete_subclass(self):
        """A subclass missing abstract methods cannot be instantiated."""

        class IncompleteParser(DocumentParser):
            @property
            def name(self) -> str:
                return "incomplete"
            # Missing parse()

        with pytest.raises(TypeError):
            IncompleteParser()  # type: ignore[abstract]
