from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class QueryRewriteResult:
    original_query: str
    rewritten_query: str
    expanded_queries: list[str] = field(default_factory=list)
    knowledge_base_id: str | None = None
    language: str | None = None
    fault_code: str | None = None
    product_model: str | None = None
    document_type: str | None = None


class SimpleQueryRewriter:
    def rewrite(self, query: str) -> QueryRewriteResult:
        normalized = " ".join(query.strip().split())
        upper_query = normalized.upper()
        fault_code_match = re.search(r"\b([A-Z]\d{3,4})\b", upper_query)
        fault_code = fault_code_match.group(1) if fault_code_match else None
        kb_match = re.search(r"\bkb[:=]\s*([A-Za-z0-9._-]+)", normalized, flags=re.IGNORECASE)
        model_match = re.search(r"\b([A-Z]{1,4}-?\d{2,5}[A-Z0-9-]*)\b", upper_query)

        language = None
        if any(token in normalized.lower() for token in ("英文", "english", "en ")):
            language = "en"
        elif re.search(r"[\u4e00-\u9fff]", normalized):
            language = "zh"

        document_type = "manual" if any(token in normalized.lower() for token in ("manual", "手册")) else None
        product_model = model_match.group(1) if model_match and model_match.group(1) != fault_code else None
        expanded_queries: list[str] = []
        if fault_code:
            expanded_queries.append(f"{fault_code} troubleshooting")
            expanded_queries.append(f"{fault_code} alarm handling")
        if "告警" in normalized or "alarm" in normalized.lower():
            expanded_queries.append("alarm troubleshooting guide")

        rewritten_parts = [normalized]
        if fault_code and fault_code not in normalized:
            rewritten_parts.append(fault_code)
        rewritten_query = " ".join(dict.fromkeys(part for part in rewritten_parts if part))
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=rewritten_query,
            expanded_queries=list(dict.fromkeys(expanded_queries)),
            knowledge_base_id=kb_match.group(1) if kb_match else None,
            language=language,
            fault_code=fault_code,
            product_model=product_model,
            document_type=document_type,
        )
