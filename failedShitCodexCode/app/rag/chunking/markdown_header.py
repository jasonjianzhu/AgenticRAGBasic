from __future__ import annotations

from app.rag.chunking.models import ChunkDraft, ChunkingOptions
from app.rag.chunking.recursive_token import RecursiveTokenChunker
from app.rag.chunking.utils import chunk_text, join_section_path, parse_markdown_heading
from app.rag.parsing.models import ParsedDocument


class MarkdownHeaderChunker:
    name = "markdown_header"

    def __init__(self) -> None:
        self._fallback = RecursiveTokenChunker()

    def chunk(self, document: ParsedDocument, options: ChunkingOptions) -> list[ChunkDraft]:
        sections: list[tuple[str | None, str]] = []
        heading_stack: list[str] = []
        current_section_path: str | None = None
        current_lines: list[str] = []
        saw_heading = False

        for raw_line in document.text.splitlines():
            heading = parse_markdown_heading(raw_line)
            if heading is not None:
                saw_heading = True
                self._flush_section(sections, current_section_path, current_lines)
                level, title = heading
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(title)
                current_section_path = join_section_path(heading_stack)
                continue
            current_lines.append(raw_line)

        self._flush_section(sections, current_section_path, current_lines)

        if not saw_heading:
            return self._fallback.chunk(document, options)

        chunks: list[ChunkDraft] = []
        for section_path, text in sections:
            for chunk in chunk_text(text, target_chars=options.target_chars, overlap_chars=options.overlap_chars):
                chunks.append(ChunkDraft(chunk_type="text", content=chunk, section_path=section_path))
        return chunks

    def _flush_section(self, sections: list[tuple[str | None, str]], section_path: str | None, current_lines: list[str]) -> None:
        text = "\n".join(current_lines).strip()
        current_lines.clear()
        if text:
            sections.append((section_path, text))
