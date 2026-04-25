from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .question_guard_schemas import (
    GuardedUserQuestion,
    QuestionGuardSummary,
    SourceQuestionCandidate,
)
from .schemas import AnalysisContextBundle

_COST_KEYWORDS = (
    "원가",
    "원가분석",
    "원가계산",
    "재료비",
    "노무비",
    "제조경비",
    "배부",
    "배부기준",
    "손익",
    "손익분석",
)
_PROBLEM_HINTS = ("현행", "문제", "한계", "이슈", "개선 필요", "개선필요", "미흡")
_STRATEGY_HINTS = ("개선", "고도화", "방향", "to-be", "구축", "재구성", "재설계", "확장")
_OPTION_HINTS = ("대안", "선택지", "비교", "옵션", "현행 vs", "as-is", "to-be")
_CRITERIA_HINTS = ("기준", "원칙", "배부기준", "판단 기준", "비교 기준")
_MISSING_HINTS = ("누락", "추가 자료", "추가자료", "확인 필요", "근거 부족", "미정")
_PROFIT_HINTS = ("손익", "손익분석", "손익 분석", "확장")
_FORCING_PATTERNS = (
    r"전면\s*재구축",
    r"무조건",
    r"반드시",
    r"꼭\s*.*해야",
    r"to-be\s*시스템으로\s*전환",
    r"재구축해야\s*하는가",
    r"전환해야\s*하는가",
)
_MISMATCH_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("product_validation", ("product", "제품 저장", "저장 전 검증", "입력 검증 로직", "save validation")),
    ("sql_parameter", ("sql 파라미터", "sql parameter", "파라미터 검증", "query parameter", "where clause")),
    ("product_domain", ("product 기능", "제품 도메인", "상품 저장")),
)
_AXIS_CALC_HINTS = ("산식", "공식", "수식", "계산 규칙", "계산식", "fifo", "환율", "환차손익")
_AXIS_JOURNAL_HINTS = ("전표", "gl", "분개", "journal", "회계 연계", "reference")


@dataclass
class SourceQuestionGuardArtifacts:
    source_question_candidates: list[SourceQuestionCandidate]
    blocked_user_questions: list[GuardedUserQuestion]
    review_user_questions: list[GuardedUserQuestion]
    question_guard_summary: QuestionGuardSummary
    effective_goal: str
    effective_constraints: list[str]
    preferred_question_axis: str


class SourceQuestionGuardService:
    _FALLBACK_MIN_SOURCE_CHARS = 120

    def evaluate(
        self,
        *,
        analysis_context: AnalysisContextBundle,
        raw_goal: str,
        raw_constraints: Iterable[str] | None = None,
    ) -> SourceQuestionGuardArtifacts:
        blocks = self._analysis_blocks(analysis_context)
        source_text = "\n".join(block["content"] for block in blocks if block["content"]).strip()
        source_char_count = len(source_text)
        uploaded_asset_count = len(list(analysis_context.assets or []))
        has_pptx_asset = any(
            str(getattr(asset, "name", "") or "").lower().endswith((".ppt", ".pptx"))
            for asset in list(analysis_context.assets or [])
        )
        sml_text_length = sum(
            len(str(block["content"] or ""))
            for block in blocks
            if str(block.get("source_stage") or "") == "sml"
        )
        no_candidate_reasons: list[str] = []
        if not blocks:
            no_candidate_reasons.append("no_safe_source_text")
        elif source_char_count < self._FALLBACK_MIN_SOURCE_CHARS:
            no_candidate_reasons.append("insufficient_source_text")
        source_domain_terms = self._source_domain_terms(source_text)
        candidates = self._extract_candidates(blocks, source_domain_terms)
        if blocks and source_char_count >= self._FALLBACK_MIN_SOURCE_CHARS and not source_domain_terms:
            fallback_candidates = self._generic_fallback_candidates(blocks)
            if fallback_candidates:
                no_candidate_reasons.append("no_domain_terms_detected")
                if not candidates:
                    candidates = fallback_candidates
                else:
                    candidates = self._dedupe_candidates(candidates + fallback_candidates)
        if not candidates and blocks and all(block.get("source_stage") not in {"sml", "document"} for block in blocks):
            no_candidate_reasons.append("unsupported_source_kind")
        allowed_user_questions: list[str] = []
        blocked_user_questions: list[GuardedUserQuestion] = []
        review_user_questions: list[GuardedUserQuestion] = []

        for item in self._user_questions(raw_goal=raw_goal, raw_constraints=raw_constraints):
            decision = self._guard_user_question(
                item,
                source_text=source_text,
                source_domain_terms=source_domain_terms,
                candidates=candidates,
            )
            if decision.status == "blocked":
                blocked_user_questions.append(decision)
            elif decision.status == "needs_review":
                review_user_questions.append(decision)
            else:
                allowed_user_questions.append(item)

        selected_questions = self._selected_questions(candidates, allowed_user_questions)
        preferred_question_axis = self._preferred_question_axis(source_text=source_text, candidates=candidates)
        if not selected_questions:
            selected_questions = ["입력 소스에서 확인 가능한 문제와 개선 방향은 무엇인가?"]
        applied_source = "source_candidates"
        if "no_domain_terms_detected" in no_candidate_reasons and candidates:
            applied_source = "generic_fallback"
        elif candidates and allowed_user_questions:
            applied_source = "mixed_with_user"
        elif not candidates:
            applied_source = "generic_fallback"

        summary = QuestionGuardSummary(
            safe_question_count=len(selected_questions),
            blocked_question_count=len(blocked_user_questions),
            review_question_count=len(review_user_questions),
            candidate_count=len(candidates),
            source_question_candidate_count=len(candidates),
            allowed_user_question_count=len(allowed_user_questions),
            needs_review=bool(review_user_questions) or len(candidates) == 0,
            source_question_shortage=len(candidates) == 0,
            uploaded_asset_count=uploaded_asset_count,
            has_pptx_asset=has_pptx_asset,
            has_safe_source_text=bool(source_text),
            safe_source_count=len(blocks),
            guard_input_source_count=len(blocks),
            guard_input_total_chars=source_char_count,
            sml_text_length=sml_text_length,
            no_candidate_reasons=self._dedupe_strings(no_candidate_reasons),
            selected_questions=selected_questions,
            selected_question_types=self._selected_question_types(candidates, selected_questions),
            source_domain_terms=source_domain_terms,
            preferred_question_axis=preferred_question_axis,
            applied_question_source=applied_source,
        )
        return SourceQuestionGuardArtifacts(
            source_question_candidates=candidates,
            blocked_user_questions=blocked_user_questions,
            review_user_questions=review_user_questions,
            question_guard_summary=summary,
            effective_goal=selected_questions[0],
            effective_constraints=selected_questions[1:4],
            preferred_question_axis=preferred_question_axis,
        )

    def _analysis_blocks(self, analysis_context: AnalysisContextBundle) -> list[dict[str, str]]:
        blocks: list[dict[str, str]] = []
        for source in list(analysis_context.source_blocks or []):
            content = str(source.content or source.excerpt or "").strip()
            if not content:
                continue
            asset_name = str(source.asset_name or source.locator or source.asset_id or "").strip()
            source_stage = "document"
            lowered = content.lower()
            asset_type = str(source.asset_type or "").strip().lower()
            if lowered.startswith("[sml v1]") or asset_name.lower().endswith((".ppt", ".pptx")):
                source_stage = "sml"
            elif asset_type in {"source", "sql", "schema", "ui"}:
                source_stage = "code"
            blocks.append(
                {
                    "asset_id": str(source.asset_id or "").strip(),
                    "asset_name": asset_name,
                    "asset_type": asset_type,
                    "source_stage": source_stage,
                    "content": content,
                }
            )
        return blocks

    def _source_domain_terms(self, source_text: str) -> list[str]:
        lowered = str(source_text or "").lower()
        found = [term for term in _COST_KEYWORDS if term.lower() in lowered]
        return found[:8]

    def _extract_candidates(
        self,
        blocks: list[dict[str, str]],
        source_domain_terms: list[str],
    ) -> list[SourceQuestionCandidate]:
        joined = "\n".join(block["content"] for block in blocks)
        lowered = joined.lower()
        candidates: list[SourceQuestionCandidate] = []

        if len(source_domain_terms) >= 2:
            candidates.append(
                self._make_candidate(
                    question="현행 원가체계의 한계는 무엇인가?",
                    question_type="problem_definition",
                    blocks=blocks,
                    keywords=source_domain_terms + list(_PROBLEM_HINTS),
                    default_stage="sml",
                    confidence="high",
                )
            )
            candidates.append(
                self._make_candidate(
                    question="문서가 제안하는 원가계산 개선 방향은 무엇인가?",
                    question_type="strategy",
                    blocks=blocks,
                    keywords=source_domain_terms + list(_STRATEGY_HINTS),
                    default_stage="sml",
                    confidence="high",
                )
            )
            if all(term in lowered for term in ("재료비", "노무비", "제조경비")) and ("배부" in lowered or "배부기준" in lowered):
                candidates.append(
                    self._make_candidate(
                        question="재료비, 노무비, 제조경비 배부 기준은 어떻게 달라지는가?",
                        question_type="decision_criteria",
                        blocks=blocks,
                        keywords=["재료비", "노무비", "제조경비", "배부", "배부기준"],
                        default_stage="sml",
                        confidence="high",
                    )
                )
            if any(term in lowered for term in _PROFIT_HINTS):
                candidates.append(
                    self._make_candidate(
                        question="원가계산 결과를 손익분석까지 확장할 근거가 있는가?",
                        question_type="scope",
                        blocks=blocks,
                        keywords=["원가", "손익", "손익분석", "확장"],
                        default_stage="sml",
                        confidence="medium",
                    )
                )

        if not candidates and any(hint in lowered for hint in _PROBLEM_HINTS):
            candidates.append(
                self._make_candidate(
                    question="현행 구조의 한계는 무엇인가?",
                    question_type="problem_definition",
                    blocks=blocks,
                    keywords=list(_PROBLEM_HINTS),
                    confidence="medium",
                )
            )
        if not candidates and any(hint in lowered for hint in _STRATEGY_HINTS):
            candidates.append(
                self._make_candidate(
                    question="문서가 제안하는 개선 방향은 무엇인가?",
                    question_type="strategy",
                    blocks=blocks,
                    keywords=list(_STRATEGY_HINTS),
                    confidence="medium",
                )
            )
        if any(hint in lowered for hint in _OPTION_HINTS):
            candidates.append(
                self._make_candidate(
                    question="비교 가능한 선택지는 무엇인가?",
                    question_type="option_comparison",
                    blocks=blocks,
                    keywords=list(_OPTION_HINTS),
                    confidence="medium",
                )
            )
        if any(hint in lowered for hint in _CRITERIA_HINTS):
            candidates.append(
                self._make_candidate(
                    question="판단 기준은 무엇인가?",
                    question_type="decision_criteria",
                    blocks=blocks,
                    keywords=list(_CRITERIA_HINTS),
                    confidence="medium",
                )
            )
        if any(hint in lowered for hint in _MISSING_HINTS):
            candidates.append(
                self._make_candidate(
                    question="누락된 정보는 무엇인가?",
                    question_type="missing_information",
                    blocks=blocks,
                    keywords=list(_MISSING_HINTS),
                    confidence="low",
                )
            )
        return self._dedupe_candidates(candidates)

    def _generic_fallback_candidates(self, blocks: list[dict[str, str]]) -> list[SourceQuestionCandidate]:
        return [
            self._make_candidate(
                question="이 문서는 어떤 문제를 해결하려는가?",
                question_type="problem_definition",
                blocks=blocks,
                keywords=list(_PROBLEM_HINTS) + ["목적", "배경", "필요성", "과제"],
                default_stage="document",
                confidence="medium",
            ),
            self._make_candidate(
                question="현행 구조의 한계는 무엇인가?",
                question_type="problem_definition",
                blocks=blocks,
                keywords=list(_PROBLEM_HINTS) + ["현행", "as-is"],
                default_stage="document",
                confidence="medium",
            ),
            self._make_candidate(
                question="문서에서 제시하는 개선 방향은 무엇인가?",
                question_type="strategy",
                blocks=blocks,
                keywords=list(_STRATEGY_HINTS) + ["방향", "개선", "전략", "고도화"],
                default_stage="document",
                confidence="medium",
            ),
            self._make_candidate(
                question="판단에 필요한 누락 정보는 무엇인가?",
                question_type="missing_information",
                blocks=blocks,
                keywords=list(_MISSING_HINTS) + ["추가 확인", "확인 필요", "검토 필요"],
                default_stage="document",
                confidence="low",
            ),
        ]

    def _make_candidate(
        self,
        *,
        question: str,
        question_type: str,
        blocks: list[dict[str, str]],
        keywords: list[str],
        default_stage: str = "document",
        confidence: str = "medium",
    ) -> SourceQuestionCandidate:
        asset_id, stage, snippet = self._find_snippet(blocks, keywords, default_stage=default_stage)
        return SourceQuestionCandidate(
            question=question,
            source_asset_id=asset_id,
            source_stage=stage,
            evidence_snippet=snippet,
            confidence=confidence,
            question_type=question_type,
        )

    def _find_snippet(
        self,
        blocks: list[dict[str, str]],
        keywords: list[str],
        *,
        default_stage: str,
    ) -> tuple[str | None, str, str]:
        normalized_keywords = [str(keyword or "").strip().lower() for keyword in keywords if str(keyword or "").strip()]
        for block in blocks:
            content = str(block["content"] or "")
            for raw_line in content.splitlines():
                line = re.sub(r"\s+", " ", raw_line).strip()
                if not line:
                    continue
                lowered = line.lower()
                if any(keyword in lowered for keyword in normalized_keywords):
                    return block["asset_id"] or None, block.get("source_stage") or default_stage, line[:220]
        if not blocks:
            return None, default_stage, ""
        first = blocks[0]
        fallback_line = re.sub(r"\s+", " ", str(first["content"]).splitlines()[0]).strip()[:220] if str(first["content"]).splitlines() else ""
        return first["asset_id"] or None, first.get("source_stage") or default_stage, fallback_line

    def _guard_user_question(
        self,
        question: str,
        *,
        source_text: str,
        source_domain_terms: list[str],
        candidates: list[SourceQuestionCandidate],
    ) -> GuardedUserQuestion:
        normalized = str(question or "").strip()
        lowered = normalized.lower()
        matched_candidate = self._matched_candidate(question, candidates)
        if self._is_source_domain_mismatch(lowered, source_domain_terms=source_domain_terms):
            return GuardedUserQuestion(
                question=normalized,
                status="blocked",
                blocked_reason="source_domain_mismatch",
                matched_source_question=matched_candidate.question if matched_candidate else "",
                evidence_snippet=matched_candidate.evidence_snippet if matched_candidate else "",
            )
        if self._is_conclusion_forcing(lowered):
            return GuardedUserQuestion(
                question=normalized,
                status="needs_review",
                blocked_reason="conclusion_forcing",
                matched_source_question=matched_candidate.question if matched_candidate else "",
                evidence_snippet=matched_candidate.evidence_snippet if matched_candidate else "",
            )
        if matched_candidate is not None:
            return GuardedUserQuestion(
                question=normalized,
                status="allowed",
                matched_source_question=matched_candidate.question,
                evidence_snippet=matched_candidate.evidence_snippet,
            )
        if source_domain_terms and any(term.lower() in lowered for term in source_domain_terms):
            return GuardedUserQuestion(question=normalized, status="allowed")
        if normalized.endswith("?") or normalized.endswith("가") or normalized.endswith("까"):
            return GuardedUserQuestion(question=normalized, status="needs_review", blocked_reason="weak_source_grounding")
        return GuardedUserQuestion(question=normalized, status="allowed")

    def _matched_candidate(
        self,
        question: str,
        candidates: list[SourceQuestionCandidate],
    ) -> SourceQuestionCandidate | None:
        lowered = str(question or "").lower()
        for candidate in candidates:
            candidate_lower = candidate.question.lower()
            if candidate_lower == lowered:
                return candidate
        for candidate in candidates:
            overlaps = 0
            for token in re.findall(r"[a-z가-힣][a-z0-9가-힣]+", candidate.question.lower(), flags=re.IGNORECASE):
                if len(token) < 2:
                    continue
                if token in lowered:
                    overlaps += 1
            if overlaps >= 2:
                return candidate
        return None

    def _is_source_domain_mismatch(self, lowered_question: str, *, source_domain_terms: list[str]) -> bool:
        source_has_cost = bool(source_domain_terms)
        for _, patterns in _MISMATCH_PATTERNS:
            if any(pattern in lowered_question for pattern in patterns):
                if source_has_cost:
                    return True
        return False

    def _is_conclusion_forcing(self, lowered_question: str) -> bool:
        return any(re.search(pattern, lowered_question, flags=re.IGNORECASE) for pattern in _FORCING_PATTERNS)

    def _selected_questions(
        self,
        candidates: list[SourceQuestionCandidate],
        allowed_user_questions: list[str],
    ) -> list[str]:
        selected = [candidate.question for candidate in candidates if candidate.confidence in {"high", "medium"}]
        for question in allowed_user_questions:
            if question not in selected:
                selected.append(question)
        return selected[:4]

    def _selected_question_types(
        self,
        candidates: list[SourceQuestionCandidate],
        selected_questions: list[str],
    ) -> list[str]:
        question_map = {candidate.question: candidate.question_type for candidate in candidates}
        selected_types: list[str] = []
        for question in selected_questions:
            question_type = question_map.get(question, "problem_definition")
            if question_type not in selected_types:
                selected_types.append(question_type)
        return selected_types

    def _preferred_question_axis(
        self,
        *,
        source_text: str,
        candidates: list[SourceQuestionCandidate],
    ) -> str:
        lowered = str(source_text or "").lower()
        calc_hits = sum(1 for token in _AXIS_CALC_HINTS if token in lowered)
        journal_hits = sum(1 for token in _AXIS_JOURNAL_HINTS if token in lowered)
        cost_hits = sum(1 for token in _COST_KEYWORDS if token.lower() in lowered)
        if journal_hits >= 3 and cost_hits < 4:
            return "journal_linkage"
        if calc_hits >= 3 and any(candidate.question_type == "decision_criteria" for candidate in candidates):
            return "calculation_rule"
        return "processing_flow"

    def _user_questions(
        self,
        *,
        raw_goal: str,
        raw_constraints: Iterable[str] | None,
    ) -> list[str]:
        items: list[str] = []
        goal = str(raw_goal or "").strip()
        if goal:
            items.append(goal)
        for item in list(raw_constraints or []):
            question = str(item or "").strip()
            if question:
                items.append(question)
        return items

    def _dedupe_candidates(self, candidates: list[SourceQuestionCandidate]) -> list[SourceQuestionCandidate]:
        deduped: list[SourceQuestionCandidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.question.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    def _dedupe_strings(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for item in items:
            key = str(item or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(key)
        return deduped
