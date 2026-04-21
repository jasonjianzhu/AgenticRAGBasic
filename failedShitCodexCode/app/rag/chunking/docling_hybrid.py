from __future__ import annotations

from app.rag.chunking.models import ChunkDraft, ChunkingOptions
from app.rag.chunking.table import TableChunker
from app.rag.chunking.utils import chunk_text, join_section_path, parse_markdown_heading
from app.rag.parsing.models import ParsedBlock, ParsedBlockType, ParsedDocument


class DoclingHybridChunker:
    name = "docling_hybrid"

    def __init__(self) -> None:
        self.table_chunker = TableChunker()

    def chunk(self, document: ParsedDocument, options: ChunkingOptions) -> list[ChunkDraft]:
        chunks: list[ChunkDraft] = []
        section_stack: list[str] = []
        text_blocks: list[ParsedBlock] = []

        def flush_text_blocks() -> None:
            if not text_blocks:
                return
            section_path = join_section_path(section_stack)
            text = "\n\n".join(block.text.strip() for block in text_blocks if block.text.strip()).strip()
            page_start = min((block.page_start for block in text_blocks if block.page_start is not None), default=None)
            page_end = max((block.page_end or block.page_start for block in text_blocks if block.page_start is not None), default=None)
            text_blocks.clear()
            for piece in chunk_text(text, target_chars=options.target_chars, overlap_chars=options.overlap_chars):
                chunks.append(
                    ChunkDraft(
                        chunk_type="text",
                        content=piece,
                        section_path=section_path,
                        page_start=page_start,
                        page_end=page_end,
                    )
                )

        for block in document.blocks:
            if block.type == ParsedBlockType.TEXT:
                heading = parse_markdown_heading(block.text)
                if heading is not None:
                    flush_text_blocks()
                    level, title = heading
                    section_stack = section_stack[: level - 1]
                    section_stack.append(title)
                    continue
                text_blocks.append(block)
                continue

            flush_text_blocks()
            if block.type == ParsedBlockType.TABLE:
                table_document = ParsedDocument(
                    source_path=document.source_path,
                    text=block.text,
                    blocks=[block],
                    metadata=document.metadata,
                )
                for table_chunk in self.table_chunker.chunk(table_document, options):
                    chunks.append(
                        ChunkDraft(
                            chunk_type=table_chunk.chunk_type,
                            content=table_chunk.content,
                            section_path=join_section_path(section_stack),
                            page_start=table_chunk.page_start,
                            page_end=table_chunk.page_end,
                            metadata=table_chunk.metadata,
                        )
                    )
                continue

            chunks.append(
                ChunkDraft(
                    chunk_type="figure",
                    content=block.text.strip(),
                    section_path=join_section_path(section_stack),
                    page_start=block.page_start,
                    page_end=block.page_end or block.page_start,
                    metadata=block.metadata,
                )
            )

        flush_text_blocks()
        return chunks
