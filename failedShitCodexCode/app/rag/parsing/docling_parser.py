from __future__ import annotations

from pathlib import Path
from typing import Any

from app.rag.parsing.models import ParseOptions, ParsedBlock, ParsedBlockType, ParsedDocument


class DoclingParser:
    def parse(self, path: str | Path, options: ParseOptions) -> ParsedDocument:
        source_path = Path(path)
        converter = self._build_converter(options)
        result = converter.convert(source_path)
        markdown = result.document.export_to_markdown()
        blocks = self._blocks_from_markdown(markdown)
        return ParsedDocument(
            source_path=source_path,
            text=markdown,
            blocks=blocks,
            metadata={
                "parser": "docling",
                "profile": options.profile.value,
                "extract_tables": options.extract_tables,
                "run_ocr": options.run_ocr,
                "extract_figures": options.extract_figures,
            },
        )

    def _build_converter(self, options: ParseOptions):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = options.run_ocr
        pipeline_options.do_table_structure = options.extract_tables
        if hasattr(pipeline_options, "generate_picture_images"):
            pipeline_options.generate_picture_images = options.extract_figures

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )

    def _blocks_from_markdown(self, markdown: str) -> list[ParsedBlock]:
        chunks = [part.strip() for part in markdown.split("\n\n") if part.strip()]
        return [
            ParsedBlock(
                type=self._guess_block_type(chunk),
                text=chunk,
                metadata={"source": "markdown"},
            )
            for chunk in chunks
        ]

    def _guess_block_type(self, text: str) -> ParsedBlockType:
        if "|" in text and "---" in text:
            return ParsedBlockType.TABLE
        if text.lower().startswith(("figure", "image")):
            return ParsedBlockType.FIGURE
        return ParsedBlockType.TEXT


def docling_available() -> bool:
    try:
        import docling  # noqa: F401
    except Exception:
        return False
    return True

