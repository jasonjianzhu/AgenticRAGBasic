"""Recursive token-based chunker as a fallback for any text."""
from __future__ import annotations

import structlog

from app.knowledge.rag.chunking.base import BaseChunker, ChunkData
from app.knowledge.rag.chunking.utils import estimate_tokens
from app.knowledge.rag.parsing.base import ParsedDocument

logger = structlog.get_logger(__name__)

# Default separators tried in order
DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


class RecursiveTokenChunker(BaseChunker):
    """Fallback chunker that recursively splits text by separators.

    Similar to LangChain's RecursiveCharacterTextSplitter but token-based.

    Args:
        target_tokens: Target chunk size in tokens (default 500).
        overlap_tokens: Overlap between chunks in tokens (default 50).
        separators: Ordered list of separators to try.
    """

    def __init__(
        self,
        target_tokens: int = 500,
        overlap_tokens: int = 50,
        separators: list[str] | None = None,
    ) -> None:
        self._target_tokens = target_tokens
        self._overlap_tokens = overlap_tokens
        self._separators = separators or DEFAULT_SEPARATORS

    @property
    def name(self) -> str:
        return "recursive_token"

    def chunk(self, parsed: ParsedDocument, **kwargs) -> list[ChunkData]:
        """Split a parsed document into token-limited chunks."""
        target_tokens = kwargs.get("target_tokens", self._target_tokens)
        overlap_tokens = kwargs.get("overlap_tokens", self._overlap_tokens)

        text = parsed.content.strip()
        if not text:
            return []

        raw_texts = self._recursive_split(text, target_tokens, self._separators)

        # Apply overlap
        chunks = self._apply_overlap(raw_texts, overlap_tokens, target_tokens)

        result: list[ChunkData] = []
        for i, chunk_text in enumerate(chunks):
            token_count = estimate_tokens(chunk_text)
            result.append(
                ChunkData(
                    content=chunk_text,
                    ordinal=i,
                    chunk_type="text",
                    token_count=token_count,
                )
            )

        logger.info(
            "recursive_token_chunked",
            total_chunks=len(result),
            content_length=len(parsed.content),
        )
        return result

    def _recursive_split(
        self,
        text: str,
        target_tokens: int,
        separators: list[str],
    ) -> list[str]:
        """Recursively split text using separators in order."""
        if estimate_tokens(text) <= target_tokens:
            return [text] if text.strip() else []

        if not separators:
            # Last resort: hard split by characters
            return self._hard_split(text, target_tokens)

        separator = separators[0]
        remaining_separators = separators[1:]

        if separator == "":
            return self._hard_split(text, target_tokens)

        parts = text.split(separator)
        if len(parts) <= 1:
            # This separator doesn't split the text, try next
            return self._recursive_split(text, target_tokens, remaining_separators)

        # Merge parts into chunks that fit within target_tokens
        result: list[str] = []
        current_parts: list[str] = []
        current_tokens = 0

        for part in parts:
            part_stripped = part.strip()
            if not part_stripped:
                continue
            part_tokens = estimate_tokens(part_stripped)

            # If a single part exceeds target, recursively split it
            if part_tokens > target_tokens:
                # Flush current
                if current_parts:
                    result.append(separator.join(current_parts))
                    current_parts = []
                    current_tokens = 0
                # Recursively split the large part
                sub_parts = self._recursive_split(
                    part_stripped, target_tokens, remaining_separators
                )
                result.extend(sub_parts)
                continue

            if current_tokens + part_tokens > target_tokens and current_parts:
                result.append(separator.join(current_parts))
                current_parts = []
                current_tokens = 0

            current_parts.append(part_stripped)
            current_tokens += part_tokens

        if current_parts:
            result.append(separator.join(current_parts))

        return [r for r in result if r.strip()]

    def _hard_split(self, text: str, target_tokens: int) -> list[str]:
        """Hard split text by characters when no separator works."""
        # Approximate chars per token
        total_tokens = estimate_tokens(text)
        if total_tokens == 0:
            return []
        chars_per_token = len(text) / total_tokens
        chunk_size = max(1, int(target_tokens * chars_per_token))

        result: list[str] = []
        for i in range(0, len(text), chunk_size):
            segment = text[i : i + chunk_size].strip()
            if segment:
                result.append(segment)
        return result

    def _apply_overlap(
        self,
        texts: list[str],
        overlap_tokens: int,
        target_tokens: int,
    ) -> list[str]:
        """Apply overlap between consecutive chunks."""
        if len(texts) <= 1 or overlap_tokens <= 0:
            return texts

        result: list[str] = []
        for i, text in enumerate(texts):
            if i == 0:
                result.append(text)
                continue

            # Get overlap from end of previous chunk
            prev_text = texts[i - 1]
            overlap_text = self._get_tail_text(prev_text, overlap_tokens)

            if overlap_text and overlap_text != text:
                combined = overlap_text + "\n" + text
                # Only add overlap if it doesn't make the chunk too large
                if estimate_tokens(combined) <= target_tokens * 1.2:
                    result.append(combined)
                else:
                    result.append(text)
            else:
                result.append(text)

        return result

    def _get_tail_text(self, text: str, target_tokens: int) -> str:
        """Get the tail portion of text that fits within target_tokens."""
        words = text.split()
        if not words:
            return ""

        # Take words from the end
        tail_words: list[str] = []
        token_count = 0
        for word in reversed(words):
            word_tokens = estimate_tokens(word)
            if token_count + word_tokens > target_tokens:
                break
            tail_words.insert(0, word)
            token_count += word_tokens

        return " ".join(tail_words)
