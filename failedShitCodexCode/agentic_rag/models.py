from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class Document:
    id: str
    title: str
    content: str
    tags: List[str]


@dataclass
class Product:
    id: str
    name: str
    aliases: List[str]
    price_monthly: int
    invoice_support: str
    deployment: str
    description: str


@dataclass
class Rule:
    id: str
    title: str
    content: str
    tags: List[str]


@dataclass
class SubQuestion:
    id: str
    text: str
    resolved_text: str
    intent: str
    route: str
    dependencies: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Evidence:
    source_type: str
    source_id: str
    title: str
    content: str
    score: float
    route: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnswerItem:
    question_id: str
    question: str
    resolved_question: str
    intent: str
    route: str
    answer: str
    status: str
    confidence: float
    evidence: List[Evidence] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        return data


@dataclass
class PipelineResult:
    original_query: str
    shared_context: Dict[str, Any]
    sub_questions: List[SubQuestion]
    answers: List[AnswerItem]
    warnings: List[str]
    rendered_answer: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_query": self.original_query,
            "shared_context": self.shared_context,
            "sub_questions": [item.to_dict() for item in self.sub_questions],
            "answers": [item.to_dict() for item in self.answers],
            "warnings": self.warnings,
            "rendered_answer": self.rendered_answer,
        }
