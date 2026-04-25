"""RAG search tool — searches knowledge base and returns relevant chunks."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class RAGSearchInput:
    """Input for rag_search tool."""
    query: str
    kb_ids: list[str] | None = None
    top_k: int = 5


@dataclass
class RAGSearchChunk:
    """A single search result chunk."""
    index: int
    document_title: str
    content: str
    page_start: int | None = None
    score: float = 0.0


@dataclass
class RAGSearchOutput:
    """Output from rag_search tool."""
    chunks: list[RAGSearchChunk] = field(default_factory=list)
    total_hits: int = 0

    def to_text(self) -> str:
        if not self.chunks:
            return "【知识库检索结果为空】未找到相关知识库内容。请直接告知用户知识库中暂无相关信息，不要用自身知识回答。"
        header = f"【知识库检索结果】共找到 {len(self.chunks)} 条相关内容，请严格基于以下内容回答，不要补充知识库中没有的信息：\n"
        parts = []
        for c in self.chunks:
            source = f"[{c.index}] {c.document_title}"
            if c.page_start:
                source += f" 第{c.page_start}页"
            parts.append(f"{source}\n{c.content}")
        return header + "\n\n---\n\n".join(parts)
