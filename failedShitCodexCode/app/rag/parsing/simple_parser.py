from __future__ import annotations

import re
import subprocess
from shutil import which
from pathlib import Path

from app.rag.parsing.models import ParseOptions, ParsedBlock, ParsedBlockType, ParsedDocument


class SimpleTextParser:
    def parse(self, path: str | Path, options: ParseOptions) -> ParsedDocument:
        source_path = Path(path)
        text = source_path.read_text(encoding="utf-8")
        blocks = [
            ParsedBlock(type=ParsedBlockType.TEXT, text=part.strip())
            for part in text.split("\n\n")
            if part.strip()
        ]
        return ParsedDocument(
            source_path=source_path,
            text=text,
            blocks=blocks,
            metadata={"parser": "simple_text", "profile": options.profile.value},
        )


class MinimalTextParser:
    def parse(self, path: str | Path, options: ParseOptions) -> ParsedDocument:
        source_path = Path(path)
        try:
            text, extraction_metadata = _extract_text(source_path)
            metadata = {
                "parser": "minimal_text",
                "profile": options.profile.value,
                **extraction_metadata,
            }
        except Exception as exc:
            text = ""
            metadata = {
                "parser": "minimal_text",
                "profile": options.profile.value,
                "fallback_error": str(exc),
            }

        blocks = [ParsedBlock(type=ParsedBlockType.TEXT, text=text)] if text else []
        return ParsedDocument(
            source_path=source_path,
            text=text,
            blocks=blocks,
            metadata=metadata,
        )


_DISALLOWED_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def _sanitize_text(text: str) -> str:
    return _DISALLOWED_CONTROL_CHARS.sub("", text)


def _extract_text(path: Path) -> tuple[str, dict[str, str]]:
    if path.suffix.lower() == ".pdf":
        text = _extract_pdf_text_with_pdftotext(path)
        if text:
            return text, {"extractor": "pdftotext"}

    raw_bytes = path.read_bytes()
    return _sanitize_text(raw_bytes.decode("utf-8", errors="ignore")).strip(), {"extractor": "bytes_decode"}


def _extract_pdf_text_with_pdftotext(path: Path) -> str:
    pdftotext_bin = which("pdftotext")
    if not pdftotext_bin:
        return ""
    try:
        result = subprocess.run(
            [pdftotext_bin, "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return _sanitize_text(result.stdout).strip()
