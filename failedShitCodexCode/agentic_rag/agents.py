from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .knowledge_base import KnowledgeRepository, normalize_text, overlap_score
from .models import AnswerItem, Evidence, PipelineResult, Product, SubQuestion


QUESTION_CUES = (
    "怎么",
    "如何",
    "多久",
    "多少",
    "哪些",
    "哪个",
    "是否",
    "能不能",
    "可不可以",
    "支持",
    "区别",
    "对比",
    "比较",
    "退款",
    "发票",
    "价格",
    "部署",
)


def contains_question_cue(text: str) -> bool:
    return any(keyword in text for keyword in QUESTION_CUES)


def safe_strip(text: str) -> str:
    return text.strip(" ，,。；;！？!?")


class PlannerAgent:
    def decompose(self, query: str) -> List[str]:
        primary_parts = re.split(r"[？?!！；;\n]+", query)
        candidates: List[str] = []
        for part in primary_parts:
            cleaned = safe_strip(part)
            if not cleaned:
                continue
            comma_parts = [safe_strip(item) for item in re.split(r"[，,]+", cleaned) if safe_strip(item)]
            if len(comma_parts) > 1 and sum(1 for item in comma_parts if contains_question_cue(item)) >= 2:
                candidates.extend(comma_parts)
            else:
                candidates.append(cleaned)
        return candidates or [safe_strip(query)]


class ContextResolver:
    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    def resolve_shared_context(self, query: str) -> Dict[str, object]:
        products = self.repository.match_products(query)
        return {
            "products": [product.name for product in products],
            "product_count": len(products),
        }

    def resolve_question(
        self,
        question: str,
        shared_context: Dict[str, object],
        previous_question_id: str | None,
        previous_question_text: str | None,
    ) -> Dict[str, object]:
        dependencies: List[str] = []
        if previous_question_id and any(token in question for token in ("它", "这个产品", "前者", "后者")):
            dependencies.append(previous_question_id)
        context_products = shared_context.get("products", [])
        carry_over_terms: List[str] = []
        if previous_question_text:
            if any(token in question for token in ("多久", "多长时间", "要几天")) and "退款" in previous_question_text:
                carry_over_terms.append("退款")
            if "开发票" in question and "发票" not in question:
                carry_over_terms.append("发票")
        return {
            "dependencies": dependencies,
            "context_products": context_products,
            "carry_over_terms": carry_over_terms,
        }


class RouterAgent:
    def classify_intent(self, question: str) -> str:
        if any(word in question for word in ("区别", "对比", "比较")):
            return "compare"
        if any(word in question for word in ("价格", "多少钱", "月付", "费用")):
            return "structured_lookup"
        if any(word in question for word in ("发票", "是否支持", "能不能", "可不可以")):
            return "policy_check"
        if any(word in question for word in ("怎么", "如何", "步骤", "流程", "多久到账", "退款")):
            return "procedural"
        return "general_lookup"

    def select_route(self, question: str, intent: str) -> str:
        if intent in ("compare", "structured_lookup"):
            return "db"
        if intent == "policy_check":
            return "rule"
        if intent in ("procedural", "general_lookup"):
            return "kb"
        return "kb"


class KnowledgeRetrieverAgent:
    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    def run(self, question: SubQuestion) -> List[Evidence]:
        return self.repository.search_documents(question.resolved_text)


class DatabaseAgent:
    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    def run(self, question: SubQuestion) -> List[Evidence]:
        products = self.repository.get_products(question.resolved_text, question.context.get("context_products"))
        return [self.repository.product_evidence(product) for product in products]


class RuleAgent:
    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    def run(self, question: SubQuestion) -> List[Evidence]:
        evidences = self.repository.search_rules(question.resolved_text)
        products = self.repository.get_products(question.resolved_text, question.context.get("context_products"))
        evidences.extend(self.repository.product_evidence(product, route="rule") for product in products)
        return evidences


class SynthesizerAgent:
    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    def answer(self, question: SubQuestion, evidences: List[Evidence]) -> AnswerItem:
        if question.route == "db":
            return self._answer_db(question, evidences)
        if question.route == "rule":
            return self._answer_rule(question, evidences)
        return self._answer_kb(question, evidences)

    def _answer_kb(self, question: SubQuestion, evidences: List[Evidence]) -> AnswerItem:
        if not evidences:
            return self._insufficient(question, evidences)
        best = evidences[0]
        if "到账" in question.text or "时效" in question.text:
            best = max(evidences, key=lambda item: overlap_score("退款 到账 工作日 时效", item.content))
        answer = self.repository.best_sentence(question.resolved_text, best.content)
        if "退款" in question.text and "多久" in question.text:
            answer = f"{self.repository.best_sentence('退款 到账 时间', best.content)}。通常审核通过后会按原路退款。"
        elif "到账" in question.text or "时效" in question.text:
            answer = f"{self.repository.best_sentence('退款 到账 工作日 时效', best.content)}。"
        elif "怎么退款" in question.text or ("退款" in question.text and "怎么" in question.text):
            policy_sentence = self.repository.best_sentence("退款 申请", best.content)
            path_sentence = self.repository.best_sentence("退款 路径 订单中心", best.content)
            answer = f"{policy_sentence}。{path_sentence}。"
        return AnswerItem(
            question_id=question.id,
            question=question.text,
            resolved_question=question.resolved_text,
            intent=question.intent,
            route=question.route,
            answer=answer,
            status="answered",
            confidence=min(0.95, 0.55 + best.score / 2),
            evidence=evidences,
        )

    def _answer_db(self, question: SubQuestion, evidences: List[Evidence]) -> AnswerItem:
        products = self.repository.get_products(question.resolved_text, question.context.get("context_products"))
        if not products:
            return self._insufficient(question, evidences)

        if len(products) >= 2 and any(word in question.text for word in ("区别", "对比", "比较", "价格", "部署")):
            lines: List[str] = []
            price_requested = any(word in question.text for word in ("价格", "多少钱", "费用"))
            deploy_requested = "部署" in question.text
            generic_compare = any(word in question.text for word in ("区别", "对比", "比较")) and not (price_requested or deploy_requested)
            if price_requested or generic_compare:
                price_part = "；".join(f"{product.name}月付 {product.price_monthly} 元" for product in products)
                lines.append(f"价格方面：{price_part}。")
            if deploy_requested or generic_compare:
                deploy_part = "；".join(f"{product.name}采用 {product.deployment}" for product in products)
                lines.append(f"部署方面：{deploy_part}。")
            if not lines:
                lines.append("；".join(evidence.content for evidence in evidences))
            answer = " ".join(lines)
        else:
            product = products[0]
            if any(word in question.text for word in ("价格", "多少钱", "费用")):
                answer = f"{product.name}当前月付价格为 {product.price_monthly} 元。"
            elif "部署" in question.text:
                answer = f"{product.name}的部署方式是：{product.deployment}。"
            else:
                answer = product.description

        return AnswerItem(
            question_id=question.id,
            question=question.text,
            resolved_question=question.resolved_text,
            intent=question.intent,
            route=question.route,
            answer=answer,
            status="answered",
            confidence=0.9,
            evidence=evidences,
        )

    def _answer_rule(self, question: SubQuestion, evidences: List[Evidence]) -> AnswerItem:
        products = self.repository.get_products(question.resolved_text, question.context.get("context_products"))
        if "发票" in question.text:
            if products:
                product_lines = [f"{product.name}：{product.invoice_support}" for product in products]
                rule_text = self.repository.best_sentence(question.resolved_text, evidences[0].content) if evidences else "未命中更详细的规则。"
                answer = f"{'；'.join(product_lines)}。补充规则：{rule_text}"
            elif evidences:
                answer = self.repository.best_sentence(question.resolved_text, evidences[0].content)
            else:
                return self._insufficient(question, evidences)
        else:
            if not evidences:
                return self._insufficient(question, evidences)
            answer = self.repository.best_sentence(question.resolved_text, evidences[0].content)

        return AnswerItem(
            question_id=question.id,
            question=question.text,
            resolved_question=question.resolved_text,
            intent=question.intent,
            route=question.route,
            answer=answer,
            status="answered",
            confidence=0.88,
            evidence=evidences,
        )

    def _insufficient(self, question: SubQuestion, evidences: List[Evidence]) -> AnswerItem:
        return AnswerItem(
            question_id=question.id,
            question=question.text,
            resolved_question=question.resolved_text,
            intent=question.intent,
            route=question.route,
            answer="没有找到足够证据来可靠回答这个子问题。",
            status="insufficient_evidence",
            confidence=0.2,
            evidence=evidences,
        )


class VerifierAgent:
    def verify(self, answers: List[AnswerItem]) -> List[str]:
        warnings: List[str] = []
        for item in answers:
            if item.status != "answered":
                warnings.append(f"{item.question_id} 未被充分回答。")
            if item.status == "answered" and not item.evidence:
                warnings.append(f"{item.question_id} 缺少可追溯证据。")
        return warnings


class AnswerAssembler:
    def render(self, original_query: str, answers: List[AnswerItem], warnings: List[str]) -> str:
        lines = [f"原始问题：{original_query}", "", "回答："]
        for index, item in enumerate(answers, start=1):
            lines.append(f"{index}. {item.question}")
            lines.append(f"   - 路由：{item.route} | 意图：{item.intent} | 状态：{item.status}")
            lines.append(f"   - 答案：{item.answer}")
            if item.evidence:
                top = item.evidence[0]
                lines.append(f"   - 证据：{top.title} -> {top.content}")
        if warnings:
            lines.append("")
            lines.append("校验告警：")
            for warning in warnings:
                lines.append(f"- {warning}")
        return "\n".join(lines)


@dataclass
class AgenticRAGPipeline:
    repository: KnowledgeRepository
    planner: PlannerAgent
    context_resolver: ContextResolver
    router: RouterAgent
    kb_agent: KnowledgeRetrieverAgent
    db_agent: DatabaseAgent
    rule_agent: RuleAgent
    synthesizer: SynthesizerAgent
    verifier: VerifierAgent
    assembler: AnswerAssembler

    @classmethod
    def from_path(cls, path: str | Path) -> "AgenticRAGPipeline":
        repository = KnowledgeRepository.from_path(path)
        return cls(
            repository=repository,
            planner=PlannerAgent(),
            context_resolver=ContextResolver(repository),
            router=RouterAgent(),
            kb_agent=KnowledgeRetrieverAgent(repository),
            db_agent=DatabaseAgent(repository),
            rule_agent=RuleAgent(repository),
            synthesizer=SynthesizerAgent(repository),
            verifier=VerifierAgent(),
            assembler=AnswerAssembler(),
        )

    def build_sub_questions(self, query: str) -> List[SubQuestion]:
        raw_questions = self.planner.decompose(query)
        shared_context = self.context_resolver.resolve_shared_context(query)
        sub_questions: List[SubQuestion] = []
        previous_question_id: str | None = None
        previous_question_text: str | None = None

        for index, text in enumerate(raw_questions, start=1):
            context = self.context_resolver.resolve_question(text, shared_context, previous_question_id, previous_question_text)
            resolved_text = self._enrich_question(text, context)
            intent = self.router.classify_intent(text)
            route = self.router.select_route(text, intent)
            sub_question = SubQuestion(
                id=f"q{index}",
                text=text,
                resolved_text=resolved_text,
                intent=intent,
                route=route,
                dependencies=context["dependencies"],
                context=context,
            )
            sub_questions.append(sub_question)
            previous_question_id = sub_question.id
            previous_question_text = sub_question.resolved_text
        return sub_questions

    def run(self, query: str) -> PipelineResult:
        shared_context = self.context_resolver.resolve_shared_context(query)
        sub_questions = self.build_sub_questions(query)
        answers: List[AnswerItem] = []

        for sub_question in sub_questions:
            evidences = self._dispatch(sub_question)
            answers.append(self.synthesizer.answer(sub_question, evidences))

        warnings = self.verifier.verify(answers)
        rendered_answer = self.assembler.render(query, answers, warnings)
        return PipelineResult(
            original_query=query,
            shared_context=shared_context,
            sub_questions=sub_questions,
            answers=answers,
            warnings=warnings,
            rendered_answer=rendered_answer,
        )

    def _dispatch(self, sub_question: SubQuestion) -> List[Evidence]:
        if sub_question.route == "db":
            return self.db_agent.run(sub_question)
        if sub_question.route == "rule":
            return self.rule_agent.run(sub_question)
        return self.kb_agent.run(sub_question)

    def _enrich_question(self, question: str, context: Dict[str, object]) -> str:
        context_products = context.get("context_products", [])
        carry_over_terms = context.get("carry_over_terms", [])
        additions: List[str] = []
        if carry_over_terms:
            additions.extend(carry_over_terms)

        normalized_question = normalize_text(question)
        if context_products and not any(normalize_text(product_name) in normalized_question for product_name in context_products):
            additions.append(f"上下文产品：{'、'.join(context_products)}")

        if not additions:
            return question
        return f"{question}。{'；'.join(additions)}"
