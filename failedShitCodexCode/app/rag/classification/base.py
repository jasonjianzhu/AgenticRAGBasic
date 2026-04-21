from __future__ import annotations

from typing import Protocol

from app.rag.classification.models import DocumentClassification
from app.rag.parsing.models import ParsedDocument


class DocumentClassifier(Protocol):
    def classify(self, document: ParsedDocument) -> DocumentClassification:
        ...
