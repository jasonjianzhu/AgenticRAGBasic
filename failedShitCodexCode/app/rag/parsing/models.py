from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ParserProfile(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    ACCURATE = "accurate"


class ParsedBlockType(StrEnum):
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"


@dataclass(frozen=True)
class ParseOptions:
    profile: ParserProfile = ParserProfile.BALANCED
    extract_tables: bool = True
    run_ocr: bool = False
    extract_figures: bool = False

    @classmethod
    def from_profile(cls, profile: ParserProfile | str) -> "ParseOptions":
        profile = ParserProfile(profile)
        if profile == ParserProfile.FAST:
            return cls(profile=profile, extract_tables=False, run_ocr=False, extract_figures=False)
        if profile == ParserProfile.ACCURATE:
            return cls(profile=profile, extract_tables=True, run_ocr=True, extract_figures=True)
        return cls(profile=profile, extract_tables=True, run_ocr=False, extract_figures=False)


@dataclass(frozen=True)
class ParsedBlock:
    type: ParsedBlockType
    text: str
    page_start: int | None = None
    page_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    source_path: Path
    text: str
    blocks: list[ParsedBlock]
    metadata: dict[str, Any] = field(default_factory=dict)

