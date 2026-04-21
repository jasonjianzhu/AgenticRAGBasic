from __future__ import annotations

from pathlib import Path

import pytest

from app.rag.parsing.models import ParsedBlock, ParsedBlockType, ParsedDocument


def build_parsed_document(filename: str, text: str) -> ParsedDocument:
    blocks = [
        ParsedBlock(type=ParsedBlockType.TEXT, text=part.strip())
        for part in text.split("\n\n")
        if part.strip()
    ]
    return ParsedDocument(
        source_path=Path(filename),
        text=text,
        blocks=blocks,
        metadata={},
    )


@pytest.mark.parametrize(
    ("filename", "text", "expected"),
    [
        (
            "battery_user_manual.pdf",
            "# Installation\n\nSafety precautions\n\nMaintenance schedule",
            "manual",
        ),
        (
            "energy_storage_notes.pdf",
            "# FAQ\n\nQ: How do I reset the alarm?\nA: Follow the reset guide.",
            "faq",
        ),
        (
            "alarm_resolution.txt",
            "Q: What does E101 mean?\nA: High temperature alarm.\n\nQ: What should I do?\nA: Check fan status.",
            "qa",
        ),
        (
            "pcs_sheet.pdf",
            "Technical specification\n\nRated voltage: 1000V\nRated current: 200A",
            "spec",
        ),
        (
            "random.txt",
            "Hello world.\n\nThis is just a short note.",
            "unknown",
        ),
    ],
)
def test_rule_based_document_classifier_detects_document_types(filename: str, text: str, expected: str) -> None:
    from app.rag.classification.rule_based import RuleBasedDocumentClassifier

    result = RuleBasedDocumentClassifier().classify(build_parsed_document(filename, text))

    assert result.document_type == expected
    if expected == "unknown":
        assert result.confidence == 0.0
    else:
        assert result.confidence > 0.0


def test_rule_based_document_classifier_prefers_faq_over_qa_when_faq_keyword_present() -> None:
    from app.rag.classification.rule_based import RuleBasedDocumentClassifier

    document = build_parsed_document(
        "battery_questions.pdf",
        "# Frequently Asked Questions\n\nQ: Can I hot swap the module?\nA: No.",
    )

    result = RuleBasedDocumentClassifier().classify(document)

    assert result.document_type == "faq"
