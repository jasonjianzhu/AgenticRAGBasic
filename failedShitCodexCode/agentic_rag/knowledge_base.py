from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable, List, Sequence

from .models import Document, Evidence, Product, Rule


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"[。！？!?；;]\s*", text)
    return [part.strip() for part in parts if part.strip()]


def extract_terms(text: str) -> List[str]:
    normalized = normalize_text(text)
    ascii_terms = re.findall(r"[a-z0-9_]+", normalized)
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    terms = list(ascii_terms)
    for chunk in chinese_chunks:
        terms.append(chunk)
        if len(chunk) > 2:
            for size in (2, 3):
                if len(chunk) >= size:
                    for index in range(len(chunk) - size + 1):
                        terms.append(chunk[index : index + size])
    return sorted(set(terms))


def overlap_score(query: str, text: str) -> float:
    query_terms = set(extract_terms(query))
    text_terms = set(extract_terms(text))
    if not query_terms or not text_terms:
        return 0.0
    overlap = len(query_terms & text_terms)
    if overlap == 0:
        return 0.0
    return overlap / math.sqrt(len(text_terms))


def keyword_boost(query: str, text: str) -> float:
    score = 0.0
    pairs = (
        (("到账", "时效", "工作日"), 1.2),
        (("发票", "专用发票", "普通发票"), 1.0),
        (("退款", "退款申请", "原路退回"), 0.8),
        (("部署", "私有化", "专属云", "SaaS"), 0.8),
        (("价格", "月付", "元"), 0.8),
    )
    for keywords, boost in pairs:
        if any(keyword in query for keyword in keywords) and any(keyword in text for keyword in keywords):
            score += boost
    return score


class KnowledgeRepository:
    def __init__(self, documents: Sequence[Document], products: Sequence[Product], rules: Sequence[Rule]):
        self.documents = list(documents)
        self.products = list(products)
        self.rules = list(rules)

    @classmethod
    def from_path(cls, path: str | Path) -> "KnowledgeRepository":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        documents = [Document(**item) for item in payload["documents"]]
        products = [Product(**item) for item in payload["products"]]
        rules = [Rule(**item) for item in payload["rules"]]
        return cls(documents=documents, products=products, rules=rules)

    def match_products(self, query: str) -> List[Product]:
        query_norm = normalize_text(query)
        matches: List[Product] = []
        for product in self.products:
            candidates = [product.name, *product.aliases]
            if any(normalize_text(candidate) in query_norm for candidate in candidates):
                matches.append(product)
        unique: List[Product] = []
        seen = set()
        for product in matches:
            if product.id not in seen:
                seen.add(product.id)
                unique.append(product)
        return unique

    def search_documents(self, query: str, top_k: int = 3) -> List[Evidence]:
        ranked = sorted(
            (
                Evidence(
                    source_type="document",
                    source_id=document.id,
                    title=document.title,
                    content=document.content,
                    score=overlap_score(query, document.title + " " + document.content) + keyword_boost(query, document.content),
                    route="kb",
                )
                for document in self.documents
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        return [item for item in ranked[:top_k] if item.score > 0]

    def search_rules(self, query: str, top_k: int = 3) -> List[Evidence]:
        ranked = sorted(
            (
                Evidence(
                    source_type="rule",
                    source_id=rule.id,
                    title=rule.title,
                    content=rule.content,
                    score=overlap_score(query, rule.title + " " + rule.content) + keyword_boost(query, rule.content),
                    route="rule",
                )
                for rule in self.rules
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        return [item for item in ranked[:top_k] if item.score > 0]

    def get_products(self, query: str, fallback_names: Iterable[str] | None = None) -> List[Product]:
        products = self.match_products(query)
        if products or not fallback_names:
            return products

        wanted = {normalize_text(name) for name in fallback_names}
        matched: List[Product] = []
        for product in self.products:
            if normalize_text(product.name) in wanted:
                matched.append(product)
        return matched

    def product_evidence(self, product: Product, route: str = "db") -> Evidence:
        content = (
            f"{product.name}：月付 {product.price_monthly} 元；"
            f"部署方式：{product.deployment}；"
            f"发票：{product.invoice_support}；"
            f"说明：{product.description}"
        )
        return Evidence(
            source_type="product",
            source_id=product.id,
            title=product.name,
            content=content,
            score=1.0,
            route=route,
        )

    def best_sentence(self, query: str, text: str) -> str:
        sentences = split_sentences(text)
        if not sentences:
            return text.strip()
        ranked = sorted(sentences, key=lambda sentence: overlap_score(query, sentence), reverse=True)
        return ranked[0]
