from __future__ import annotations

import math
import re


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def parse_markdown_heading(text: str) -> tuple[int, str] | None:
    match = HEADING_RE.match(text.strip())
    if match is None:
        return None
    level = len(match.group(1))
    title = match.group(2).strip()
    return level, title


def join_section_path(parts: list[str]) -> str | None:
    cleaned = [part.strip() for part in parts if part.strip()]
    if not cleaned:
        return None
    return " / ".join(cleaned)


def estimate_token_count(text: str) -> int:
    if not text.strip():
        return 0
    return max(1, math.ceil(len(text) / 4))


def detect_language(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    if CJK_RE.search(stripped):
        return "zh"
    if re.search(r"[A-Za-z]", stripped):
        return "en"
    return None


def chunk_text(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        stripped = text.strip()
        return [stripped] if stripped else []

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if current and len(candidate) > target_chars:
            chunks.append(current)
            current = _with_overlap(current=current, next_paragraph=paragraph, overlap_chars=overlap_chars)
        else:
            current = candidate

    if current:
        chunks.append(current)

    normalized: list[str] = []
    for chunk in chunks:
        if len(chunk) <= target_chars * 1.5:
            normalized.append(chunk)
            continue
        normalized.extend(_split_hard(chunk, target_chars=target_chars, overlap_chars=overlap_chars))
    return normalized


def _with_overlap(current: str, next_paragraph: str, overlap_chars: int) -> str:
    if overlap_chars <= 0:
        return next_paragraph
    overlap = current[-overlap_chars:].strip()
    if not overlap:
        return next_paragraph
    return f"{overlap}\n\n{next_paragraph}"


def _split_hard(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    step = max(1, target_chars - overlap_chars)
    while start < len(text):
        end = min(len(text), start + target_chars)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start += step
    return chunks
