"""Persistence layer for parsed document output.

Saves and loads ``ParsedDocument`` instances as JSON via the project's
``StorageBackend`` abstraction.

Path format: ``{kb_id}/{doc_id}/{version}/parsed.json``
"""
from __future__ import annotations

import json

from app.core.logging import get_logger
from app.rag.parsing.base import ParsedDocument
from app.storage.base import StorageBackend

logger = get_logger(__name__)


def parsed_json_path(kb_id: str, doc_id: str, version: int | str) -> str:
    """Build the canonical storage path for a parsed document JSON."""
    return f"{kb_id}/{doc_id}/{version}/parsed.json"


async def save_parsed_document(
    storage: StorageBackend,
    kb_id: str,
    doc_id: str,
    version: int | str,
    parsed: ParsedDocument,
) -> str:
    """Serialize a ParsedDocument to JSON and write it to storage.

    Returns:
        The storage path where the file was written.
    """
    path = parsed_json_path(kb_id, doc_id, version)
    data = json.dumps(parsed.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")

    written_path = await storage.write(path, data)

    logger.info(
        "parsed_document_saved",
        kb_id=kb_id,
        doc_id=doc_id,
        version=version,
        path=path,
        size=len(data),
    )
    return written_path


async def load_parsed_document(
    storage: StorageBackend,
    kb_id: str,
    doc_id: str,
    version: int | str,
) -> ParsedDocument:
    """Load a ParsedDocument from JSON stored in the storage backend.

    Raises:
        FileNotFoundError: If the parsed JSON does not exist.
    """
    path = parsed_json_path(kb_id, doc_id, version)
    raw = await storage.read(path)
    data = json.loads(raw.decode("utf-8"))

    logger.info(
        "parsed_document_loaded",
        kb_id=kb_id,
        doc_id=doc_id,
        version=version,
        path=path,
    )
    return ParsedDocument.from_dict(data)
