from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.rag.parsing.models import ParseOptions, ParsedDocument


class DocumentParser(Protocol):
    def parse(self, path: str | Path, options: ParseOptions) -> ParsedDocument:
        ...

