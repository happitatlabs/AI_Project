from __future__ import annotations

from typing import Iterable

from mellow_link.modules.rebuild_assistant.schemas import GroundedBusinessRule, RetainedContract

from .decision_catalog import JudgmentTemplateId

WORKFLOW_KEYWORDS = (
    "approver",
    "approverrole",
    "approvalstep",
    "approvallevel",
    "reviewer",
    "approve",
    "approved",
    "reject",
    "hold",
    "delegate",
    "approval",
    "승인",
    "반려",
    "보류",
    "대리 승인",
    "단계",
    "예외 승인",
)
STATE_KEYWORDS = (
    "status",
    "state",
    "closed",
    "cancelled",
    "ready",
    "pending",
    "review_required",
    "상태",
    "전이",
    "마감",
)
ACCESS_CONTROL_KEYWORDS = (
    "role",
    "dept",
    "claim_audit",
    "hq",
    "hq_reviewer",
    "branch_manager",
    "권한",
    "부서",
    "본사",
    "지점",
    "전담",
)
QUERY_FILTER_KEYWORDS = (
    "search",
    "filter",
    "query",
    "where",
    "order by",
    "sort",
    "paging",
    "page",
    "조회",
    "검색",
    "필터",
    "정렬",
    "페이징",
    "목록",
)
AMOUNT_THRESHOLD_KEYWORDS = (
    "amount",
    "threshold",
    "limit",
    "order_amount",
    "claim_amount",
    "금액",
    "한도",
    "고액",
    "5000000",
    "7000000",
    "10000000",
    "본사 승인",
    "검토",
)
VALIDATION_KEYWORDS = (
    "amount",
    "한도",
    "duplicate",
    "중복",
    "exists",
    "count",
    "save",
    "저장",
    "차단",
    "선행",
    "invalid",
    "required",
    "blocked",
    "hold",
    "검증",
)
NARRATIVE_PRIORITY: tuple[JudgmentTemplateId, ...] = (
    "workflow",
    "access_control",
    "amount_threshold",
    "state_transition",
    "query_filter",
    "validation",
)
FEATURE_MODE_TO_AXIS: dict[str, JudgmentTemplateId] = {
    "status_permissions": "access_control",
    "search_filters": "query_filter",
    "save_validation": "validation",
}


def _keyword_hit_count(text: str, keywords: Iterable[str]) -> int:
    lowered = (text or "").lower()
    return sum(1 for keyword in keywords if keyword in lowered)


class NarrativeAxisResolver:
    def select_axis(
        self,
        prepared,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        primary_judgment: str,
    ) -> str:
        scores: dict[str, int] = {axis: 0 for axis in NARRATIVE_PRIORITY}
        if primary_judgment in scores:
            scores[primary_judgment] += 3
        feature_mode = str(getattr(getattr(prepared, "signals", None), "primary_feature_mode", "") or "").strip()
        mapped_axis = FEATURE_MODE_TO_AXIS.get(feature_mode)
        if mapped_axis:
            scores[mapped_axis] += 2

        for item in grounded_rules[:5]:
            self._apply_text_scores(scores, f"{item.title} {item.description} {' '.join(item.design_targets)}", weight=2)
        for item in retained_contracts[:5]:
            self._apply_text_scores(scores, f"{item.item} {item.basis}", weight=2)

        query_score = scores["query_filter"]
        amount_score = scores["amount_threshold"]
        if amount_score > 0 and query_score > 0 and amount_score <= query_score:
            scores["amount_threshold"] = max(0, amount_score - 1)

        if primary_judgment in {"workflow", "state_transition"}:
            return primary_judgment
        if scores["access_control"] >= scores["query_filter"] + 2 and scores["access_control"] >= 4:
            return "access_control"
        if scores["amount_threshold"] >= scores["validation"] + 1 and scores["amount_threshold"] >= 4:
            return "amount_threshold"
        if scores["workflow"] >= scores["state_transition"] + 1 and scores["workflow"] >= 4:
            return "workflow"
        if scores["state_transition"] >= 4 and scores["state_transition"] >= scores["validation"] + 1:
            return "state_transition"
        if primary_judgment in {"workflow", "state_transition"} and scores.get(primary_judgment, 0) >= 3:
            competing = max(scores[axis] for axis in NARRATIVE_PRIORITY if axis != primary_judgment)
            if scores[primary_judgment] >= competing:
                return primary_judgment

        best_axis = max(
            NARRATIVE_PRIORITY,
            key=lambda axis: (
                scores[axis],
                1 if axis == primary_judgment else 0,
                -NARRATIVE_PRIORITY.index(axis),
            ),
        )
        if scores[best_axis] <= 0:
            return primary_judgment or "validation"
        return best_axis

    def prioritize_rule_texts(
        self,
        narrative_axis: str,
        grounded_rules: list[GroundedBusinessRule],
        fallback: list[str],
    ) -> list[str]:
        prioritized = [
            item.description.strip()
            for item in grounded_rules
            if item.description.strip() and self.rule_matches_axis(item, narrative_axis)
        ]
        if prioritized:
            return self._dedupe(prioritized)[:4]
        fallback_rules = [item.description.strip() for item in grounded_rules if item.description.strip()]
        return self._dedupe(fallback_rules or fallback)[:4]

    def prioritize_contracts(
        self,
        narrative_axis: str,
        retained_contracts: list[RetainedContract],
    ) -> list[RetainedContract]:
        prioritized = [
            item for item in retained_contracts if self.contract_matches_axis(item, narrative_axis)
        ]
        if prioritized:
            retained_contracts = prioritized
        deduped: list[RetainedContract] = []
        seen: set[str] = set()
        for item in retained_contracts:
            key = f"{item.item}::{item.basis}".strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def rule_matches_axis(self, rule: GroundedBusinessRule, narrative_axis: str) -> bool:
        text = " ".join([rule.title, rule.description, " ".join(rule.design_targets)])
        return self._matches_axis(text, narrative_axis)

    def contract_matches_axis(self, contract: RetainedContract, narrative_axis: str) -> bool:
        return self._matches_axis(f"{contract.item} {contract.basis}", narrative_axis)

    def _matches_axis(self, text: str, narrative_axis: str) -> bool:
        query_hits = _keyword_hit_count(text, QUERY_FILTER_KEYWORDS)
        amount_hits = _keyword_hit_count(text, AMOUNT_THRESHOLD_KEYWORDS)
        if narrative_axis == "workflow":
            return _keyword_hit_count(text, WORKFLOW_KEYWORDS) > 0
        if narrative_axis == "access_control":
            return _keyword_hit_count(text, ACCESS_CONTROL_KEYWORDS) > 0
        if narrative_axis == "query_filter":
            return query_hits > 0
        if narrative_axis == "amount_threshold":
            return amount_hits > 0 and query_hits == 0
        if narrative_axis == "state_transition":
            return _keyword_hit_count(text, STATE_KEYWORDS) > 0
        if narrative_axis == "validation":
            return _keyword_hit_count(text, VALIDATION_KEYWORDS) > 0
        return True

    def _apply_text_scores(self, scores: dict[str, int], text: str, *, weight: int) -> None:
        scores["workflow"] += _keyword_hit_count(text, WORKFLOW_KEYWORDS) * weight
        scores["state_transition"] += _keyword_hit_count(text, STATE_KEYWORDS) * weight
        scores["access_control"] += _keyword_hit_count(text, ACCESS_CONTROL_KEYWORDS) * weight
        scores["query_filter"] += _keyword_hit_count(text, QUERY_FILTER_KEYWORDS) * weight
        scores["amount_threshold"] += _keyword_hit_count(text, AMOUNT_THRESHOLD_KEYWORDS) * weight
        scores["validation"] += _keyword_hit_count(text, VALIDATION_KEYWORDS) * weight

    def _dedupe(self, items: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for item in items:
            key = " ".join((item or "").split()).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output
