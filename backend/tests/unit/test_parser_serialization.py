"""Tests for parsed document serialization/deserialization (S5-04)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from app.knowledge.rag.parsing.base import ParsedDocument, ParsedPage, ParsedTable
from app.knowledge.rag.parsing.serialization import (
    load_parsed_document,
    parsed_json_path,
    save_parsed_document,
)
from app.common.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(base_dir=tmp_path)


def _sample_doc() -> ParsedDocument:
    return ParsedDocument(
        content="# 产品手册\n\n电池过温告警处理流程",
        pages=[
            ParsedPage(page_number=1, content="第一页内容"),
            ParsedPage(page_number=2, content="第二页内容"),
        ],
        tables=[
            ParsedTable(
                content="| 告警码 | 描述 |\n|---|---|\n| E003 | 过温 |",
                page_number=1,
                caption="告警代码表",
            ),
        ],
        metadata={"parser_name": "docling", "profile": "balanced", "page_count": 2},
    )


# ---------------------------------------------------------------------------
# parsed_json_path
# ---------------------------------------------------------------------------

class TestParsedJsonPath:
    def test_format(self):
        path = parsed_json_path("kb-123", "doc-456", 1)
        assert path == "kb-123/doc-456/1/parsed.json"

    def test_string_version(self):
        path = parsed_json_path("kb-1", "doc-2", "3")
        assert path == "kb-1/doc-2/3/parsed.json"


# ---------------------------------------------------------------------------
# save_parsed_document
# ---------------------------------------------------------------------------

class TestSaveParsedDocument:
    @pytest.mark.asyncio
    async def test_save_creates_file(self, storage: LocalStorage):
        doc = _sample_doc()
        written = await save_parsed_document(storage, "kb1", "doc1", 1, doc)

        assert await storage.exists("kb1/doc1/1/parsed.json")
        assert written  # non-empty path

    @pytest.mark.asyncio
    async def test_saved_content_is_valid_json(self, storage: LocalStorage):
        doc = _sample_doc()
        await save_parsed_document(storage, "kb1", "doc1", 1, doc)

        raw = await storage.read("kb1/doc1/1/parsed.json")
        data = json.loads(raw.decode("utf-8"))

        assert data["content"] == doc.content
        assert len(data["pages"]) == 2
        assert len(data["tables"]) == 1
        assert data["metadata"]["parser_name"] == "docling"

    @pytest.mark.asyncio
    async def test_saved_json_preserves_unicode(self, storage: LocalStorage):
        doc = _sample_doc()
        await save_parsed_document(storage, "kb1", "doc1", 1, doc)

        raw = await storage.read("kb1/doc1/1/parsed.json")
        text = raw.decode("utf-8")

        # ensure_ascii=False means Chinese characters are stored directly
        assert "产品手册" in text
        assert "电池过温" in text

    @pytest.mark.asyncio
    async def test_save_overwrites_existing(self, storage: LocalStorage):
        doc1 = ParsedDocument(content="first", pages=[], tables=[])
        doc2 = ParsedDocument(content="second", pages=[], tables=[])

        await save_parsed_document(storage, "kb1", "doc1", 1, doc1)
        await save_parsed_document(storage, "kb1", "doc1", 1, doc2)

        raw = await storage.read("kb1/doc1/1/parsed.json")
        data = json.loads(raw.decode("utf-8"))
        assert data["content"] == "second"


# ---------------------------------------------------------------------------
# load_parsed_document
# ---------------------------------------------------------------------------

class TestLoadParsedDocument:
    @pytest.mark.asyncio
    async def test_load_roundtrip(self, storage: LocalStorage):
        original = _sample_doc()
        await save_parsed_document(storage, "kb1", "doc1", 1, original)

        loaded = await load_parsed_document(storage, "kb1", "doc1", 1)

        assert loaded.content == original.content
        assert len(loaded.pages) == len(original.pages)
        for lp, op in zip(loaded.pages, original.pages):
            assert lp.page_number == op.page_number
            assert lp.content == op.content
        assert len(loaded.tables) == len(original.tables)
        for lt, ot in zip(loaded.tables, original.tables):
            assert lt.content == ot.content
            assert lt.page_number == ot.page_number
            assert lt.caption == ot.caption
        assert loaded.metadata == original.metadata

    @pytest.mark.asyncio
    async def test_load_nonexistent_raises(self, storage: LocalStorage):
        with pytest.raises(FileNotFoundError):
            await load_parsed_document(storage, "no-kb", "no-doc", 99)

    @pytest.mark.asyncio
    async def test_load_empty_document(self, storage: LocalStorage):
        doc = ParsedDocument(content="", pages=[], tables=[])
        await save_parsed_document(storage, "kb1", "doc1", 1, doc)

        loaded = await load_parsed_document(storage, "kb1", "doc1", 1)
        assert loaded.content == ""
        assert loaded.pages == []
        assert loaded.tables == []
        assert loaded.metadata == {}

    @pytest.mark.asyncio
    async def test_different_versions(self, storage: LocalStorage):
        """Different versions are stored independently."""
        doc_v1 = ParsedDocument(content="version 1", pages=[], tables=[])
        doc_v2 = ParsedDocument(content="version 2", pages=[], tables=[])

        await save_parsed_document(storage, "kb1", "doc1", 1, doc_v1)
        await save_parsed_document(storage, "kb1", "doc1", 2, doc_v2)

        loaded_v1 = await load_parsed_document(storage, "kb1", "doc1", 1)
        loaded_v2 = await load_parsed_document(storage, "kb1", "doc1", 2)

        assert loaded_v1.content == "version 1"
        assert loaded_v2.content == "version 2"
