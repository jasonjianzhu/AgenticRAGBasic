"""Document parser implementation using the Docling library."""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.logging import get_logger
from app.rag.parsing.base import DocumentParser, ParsedDocument, ParsedPage, ParsedTable

logger = get_logger(__name__)

# Profile names
PROFILE_FAST = "fast"
PROFILE_BALANCED = "balanced"
PROFILE_ACCURATE = "accurate"
VALID_PROFILES = {PROFILE_FAST, PROFILE_BALANCED, PROFILE_ACCURATE}


def _build_converter(profile: str):
    """Build a docling DocumentConverter configured for the given profile.

    Imports are deferred so the heavy docling models are only loaded when
    actually needed.
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    if profile == PROFILE_FAST:
        pipeline_opts = PdfPipelineOptions(
            do_ocr=False,
            do_table_structure=False,
        )
    elif profile == PROFILE_ACCURATE:
        pipeline_opts = PdfPipelineOptions(
            do_ocr=True,
            do_table_structure=True,
            table_structure_options=TableStructureOptions(do_cell_matching=True),
        )
    else:
        # balanced – docling defaults
        pipeline_opts = PdfPipelineOptions()

    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts),
        },
    )
    return converter


def _run_docling(file_path: str, profile: str) -> ParsedDocument:
    """Synchronous helper that runs docling conversion.

    Designed to be called inside ``asyncio.to_thread`` so the event loop
    is not blocked by the CPU-heavy parsing.
    """
    converter = _build_converter(profile)
    result = converter.convert(file_path)
    doc = result.document

    # Full markdown content
    content = doc.export_to_markdown()

    # Per-page content
    pages: list[ParsedPage] = []
    for page in result.pages:
        page_no = page.page_no
        # Export full doc text – we'll attribute per-page via body items
        pages.append(ParsedPage(page_number=page_no, content=""))

    # Build per-page text from body items that carry provenance
    page_texts: dict[int, list[str]] = {}
    for item, _level in doc.iterate_items():
        if hasattr(item, "prov") and item.prov:
            # Extract text content from the item
            text = ""
            if hasattr(item, "export_to_markdown"):
                try:
                    text = item.export_to_markdown()
                except Exception:
                    pass
            if not text and hasattr(item, "text"):
                text = item.text or ""
            if not text:
                continue

            for prov in item.prov:
                pn = prov.page_no
                page_texts.setdefault(pn, []).append(text)

    # Assign collected text to pages
    for p in pages:
        if p.page_number in page_texts:
            p.content = "\n\n".join(page_texts[p.page_number])

    # Tables
    tables: list[ParsedTable] = []
    for table_item in doc.tables.values() if hasattr(doc.tables, "values") else doc.tables:
        # Get table item – doc.tables is a dict-like mapping
        tbl = table_item if not isinstance(table_item, tuple) else table_item[1]
        md = tbl.export_to_markdown() if hasattr(tbl, "export_to_markdown") else str(tbl)
        page_no = tbl.prov[0].page_no if tbl.prov else 0
        caption_text = None
        if tbl.captions:
            # captions are RefItems; resolve text if possible
            caption_parts = []
            for cap_ref in tbl.captions:
                if hasattr(cap_ref, "text"):
                    caption_parts.append(cap_ref.text)
                elif hasattr(cap_ref, "export_to_markdown"):
                    caption_parts.append(cap_ref.export_to_markdown())
            if caption_parts:
                caption_text = " ".join(caption_parts)
        tables.append(ParsedTable(content=md, page_number=page_no, caption=caption_text))

    metadata = {
        "parser_name": "docling",
        "profile": profile,
        "page_count": len(result.pages),
    }

    return ParsedDocument(
        content=content,
        pages=pages,
        tables=tables,
        metadata=metadata,
    )


class DoclingParser(DocumentParser):
    """Parse PDF documents using the Docling library.

    Supports three profiles:
    - fast: disables OCR and table structure recognition
    - balanced: default docling settings
    - accurate: enables OCR, table structure, and cell matching
    """

    @property
    def name(self) -> str:
        return "docling"

    async def parse(self, file_path: str, profile: str = "balanced") -> ParsedDocument:
        """Parse a PDF using docling with the specified profile."""
        if profile not in VALID_PROFILES:
            raise ValueError(
                f"Invalid profile '{profile}'. Must be one of: {', '.join(sorted(VALID_PROFILES))}"
            )

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(
            "docling_parse_start",
            file_path=file_path,
            profile=profile,
        )

        try:
            parsed = await asyncio.to_thread(_run_docling, file_path, profile)
        except Exception:
            logger.exception(
                "docling_parse_failed",
                file_path=file_path,
                profile=profile,
            )
            raise

        logger.info(
            "docling_parse_complete",
            file_path=file_path,
            profile=profile,
            page_count=len(parsed.pages),
            table_count=len(parsed.tables),
            content_length=len(parsed.content),
        )
        return parsed
