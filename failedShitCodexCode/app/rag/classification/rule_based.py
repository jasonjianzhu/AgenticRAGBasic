from __future__ import annotations

import re
from dataclasses import dataclass

from app.rag.classification.models import DocumentClassification
from app.rag.parsing.models import ParsedDocument


@dataclass(frozen=True)
class _Rule:
    document_type: str
    pattern: str
    weight: float
    target: str = "text"


class RuleBasedDocumentClassifier:
    def __init__(self) -> None:
        self.rules = (
            _Rule("faq", r"frequently asked questions|faq|常见问题", 3.0),
            _Rule("qa", r"(?m)^\s*q[:：]", 1.5),
            _Rule("qa", r"(?m)^\s*a[:：]", 1.5),
            _Rule("manual", r"user manual|installation|maintenance|safety|operation guide|troubleshooting", 1.2),
            _Rule("spec", r"technical specification|specification|rated voltage|rated current|parameter", 1.3),
            _Rule("manual", r"manual|guide", 1.8, target="filename"),
            _Rule("faq", r"faq|frequently[_ -]?asked[_ -]?questions", 2.5, target="filename"),
            _Rule("spec", r"spec|datasheet|parameter", 1.8, target="filename"),
        )

    def classify(self, document: ParsedDocument) -> DocumentClassification:
        haystacks = {
            "text": document.text.lower(),
            "filename": document.source_path.name.lower(),
        }
        scores = {
            "manual": 0.0,
            "faq": 0.0,
            "qa": 0.0,
            "spec": 0.0,
        }

        for rule in self.rules:
            matches = re.findall(rule.pattern, haystacks[rule.target], flags=re.IGNORECASE)
            if matches:
                scores[rule.document_type] += len(matches) * rule.weight

        if scores["faq"] > 0.0:
            scores["faq"] += min(scores["qa"], 1.5)

        document_type, score = max(scores.items(), key=lambda item: item[1])
        total_score = sum(scores.values())
        if score <= 0.0 or total_score <= 0.0:
            return DocumentClassification(
                document_type="unknown",
                confidence=0.0,
                strategy="rule_based",
                metadata={"scores": scores},
            )

        return DocumentClassification(
            document_type=document_type,
            confidence=round(score / total_score, 4),
            strategy="rule_based",
            metadata={"scores": scores},
        )
