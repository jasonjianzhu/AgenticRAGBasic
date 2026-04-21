from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.rag.parsing.models import ParsedBlock, ParsedBlockType, ParsedDocument


def parsed_document_to_dict(document: ParsedDocument) -> dict[str, Any]:
    return {
        "source_path": str(document.source_path),
        "text": document.text,
        "metadata": document.metadata,
        "blocks": [parsed_block_to_dict(block) for block in document.blocks],
    }


def parsed_block_to_dict(block: ParsedBlock) -> dict[str, Any]:
    return {
        "type": block.type.value,
        "text": block.text,
        "page_start": block.page_start,
        "page_end": block.page_end,
        "metadata": block.metadata,
    }


def parsed_document_from_dict(payload: dict[str, Any]) -> ParsedDocument:
    return ParsedDocument(
        source_path=Path(payload["source_path"]),
        text=payload.get("text", ""),
        blocks=[parsed_block_from_dict(block) for block in payload.get("blocks", [])],
        metadata=payload.get("metadata", {}),
    )


def parsed_block_from_dict(payload: dict[str, Any]) -> ParsedBlock:
    return ParsedBlock(
        type=ParsedBlockType(payload["type"]),
        text=payload.get("text", ""),
        page_start=payload.get("page_start"),
        page_end=payload.get("page_end"),
        metadata=payload.get("metadata", {}),
    )


def write_parsed_document(document: ParsedDocument, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(parsed_document_to_dict(document), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def read_parsed_document(input_path: str | Path) -> ParsedDocument:
    path = Path(input_path)
    return parsed_document_from_dict(json.loads(path.read_text(encoding="utf-8")))
