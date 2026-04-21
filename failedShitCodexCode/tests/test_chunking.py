from __future__ import annotations

from pathlib import Path

from app.rag.parsing.models import ParsedBlock, ParsedBlockType, ParsedDocument


def test_chunker_registry_selects_default_strategy_by_document_type() -> None:
    from app.rag.chunking.registry import build_default_chunker_registry

    registry = build_default_chunker_registry()

    assert registry.select(document_type="manual").name == "docling_hybrid"
    assert registry.select(document_type="faq").name == "markdown_header"
    assert registry.select(document_type="unknown").name == "recursive_token"
    assert registry.chunkers["table"].name == "table_chunker"


def test_docling_hybrid_chunker_keeps_tables_separate() -> None:
    from app.rag.chunking.docling_hybrid import DoclingHybridChunker
    from app.rag.chunking.models import ChunkingOptions

    document = ParsedDocument(
        source_path=Path("manual.md"),
        text="# Overview\n\nBattery system overview.\n\n# Maintenance\n\nCheck wiring monthly.",
        blocks=[
            ParsedBlock(type=ParsedBlockType.TEXT, text="# Overview", page_start=1),
            ParsedBlock(type=ParsedBlockType.TEXT, text="Battery system overview.", page_start=1),
            ParsedBlock(
                type=ParsedBlockType.TABLE,
                text="| Code | Meaning |\n|---|---|\n|E101|Overheat|",
                page_start=2,
                page_end=2,
            ),
            ParsedBlock(type=ParsedBlockType.TEXT, text="# Maintenance", page_start=3),
            ParsedBlock(type=ParsedBlockType.TEXT, text="Check wiring monthly.", page_start=3),
        ],
        metadata={},
    )

    chunks = DoclingHybridChunker().chunk(document, ChunkingOptions(target_chars=80, overlap_chars=0))

    assert [chunk.chunk_type for chunk in chunks] == ["text", "table", "text"]
    assert chunks[0].section_path == "Overview"
    assert chunks[1].page_start == 2
    assert chunks[1].metadata["table_row_count"] == 1
    assert chunks[2].section_path == "Maintenance"


def test_markdown_header_chunker_splits_by_heading_hierarchy() -> None:
    from app.rag.chunking.markdown_header import MarkdownHeaderChunker
    from app.rag.chunking.models import ChunkingOptions

    text = "# Installation\nPrepare the cabinet.\n\n## Alarm handling\nReview E101 troubleshooting."
    document = ParsedDocument(
        source_path=Path("manual.md"),
        text=text,
        blocks=[ParsedBlock(type=ParsedBlockType.TEXT, text=text)],
        metadata={},
    )

    chunks = MarkdownHeaderChunker().chunk(document, ChunkingOptions(target_chars=120, overlap_chars=0))

    assert len(chunks) == 2
    assert chunks[0].section_path == "Installation"
    assert chunks[1].section_path == "Installation / Alarm handling"


def test_recursive_token_chunker_splits_long_text() -> None:
    from app.rag.chunking.models import ChunkingOptions
    from app.rag.chunking.recursive_token import RecursiveTokenChunker

    text = "\n\n".join(
        f"Paragraph {index} " + ("battery system " * 12)
        for index in range(6)
    )
    document = ParsedDocument(
        source_path=Path("notes.txt"),
        text=text,
        blocks=[ParsedBlock(type=ParsedBlockType.TEXT, text=text)],
        metadata={},
    )

    chunks = RecursiveTokenChunker().chunk(document, ChunkingOptions(target_chars=120, overlap_chars=20))

    assert len(chunks) >= 2
    assert all(chunk.chunk_type == "text" for chunk in chunks)


def test_table_chunker_preserves_header_and_splits_large_table() -> None:
    from app.rag.chunking.models import ChunkingOptions
    from app.rag.chunking.table import TableChunker

    table_text = "\n".join(
        [
            "| Code | Meaning | Action |",
            "|---|---|---|",
            "| E101 | Overheat | Check cooling |",
            "| E102 | Overcurrent | Check inverter |",
            "| E103 | Fan fault | Replace fan |",
            "| E104 | Sensor fault | Check sensor |",
        ]
    )
    document = ParsedDocument(
        source_path=Path("alarm_table.md"),
        text=table_text,
        blocks=[
            ParsedBlock(
                type=ParsedBlockType.TABLE,
                text=table_text,
                page_start=4,
                page_end=4,
            )
        ],
        metadata={},
    )

    chunks = TableChunker().chunk(document, ChunkingOptions(target_chars=90, overlap_chars=0))

    assert len(chunks) == 2
    assert all(chunk.chunk_type == "table" for chunk in chunks)
    assert chunks[0].content.splitlines()[0] == "| Code | Meaning | Action |"
    assert chunks[1].content.splitlines()[0] == "| Code | Meaning | Action |"
    assert chunks[0].metadata["table_header"] == ["Code", "Meaning", "Action"]
    assert chunks[0].metadata["table_row_start"] == 1
    assert chunks[1].metadata["table_row_start"] == 3
    assert chunks[1].metadata["table_row_count"] == 2
