from __future__ import annotations

import sys
from pathlib import Path

_SQL_ENGINE_ROOT = Path(__file__).resolve().parents[2] / "sql_ai_decision_engine"
if str(_SQL_ENGINE_ROOT) not in sys.path:
    sys.path.append(str(_SQL_ENGINE_ROOT))

from app.schemas.request import AnalyzeRequest
from app.services.analysis_pipeline import AnalysisPipeline


class SQLAnalyticsService:
    def __init__(self) -> None:
        self._pipeline = AnalysisPipeline()

    def analyze(self, question: str, input_type: str = "natural_language") -> dict:
        req = AnalyzeRequest(query=question, input_type=input_type)
        return self._pipeline.run(req)

    def format_user_summary(self, result: dict, question: str) -> str:
        decision = str(result.get("decision") or "normal")
        normalized = result.get("normalized_request") or {}
        filters = getattr(normalized, "filters", None) or normalized.get("filters") or {}
        sql_results = result.get("sql_results") or {}
        rows = sql_results.get("rows") or []
        rule_results = result.get("rule_results") or []
        matched = [item for item in rule_results if item.get("matched")]

        conclusion_map = {
            "high_risk": "즉시 확인이 필요한 위험 상태입니다.",
            "warning": "추가 확인이 필요한 주의 상태입니다.",
            "normal": "즉시 이상 징후가 크지 않은 상태입니다.",
        }
        conclusion = conclusion_map.get(decision, f"현재 판단 결과는 {decision}입니다.")

        metric_parts: list[str] = []
        if rows:
            row = rows[0]
            metric_labels = {
                "refund_rate": "환불률",
                "inquiry_growth": "문의 증가율",
                "churn_rate": "이탈률",
            }
            for key, label in metric_labels.items():
                value = row.get(key)
                if value is None:
                    continue
                if isinstance(value, (int, float)):
                    metric_parts.append(f"{label} {value * 100:.1f}%")
                else:
                    metric_parts.append(f"{label} {value}")

        summary_line = "조회된 지표가 충분하지 않아 기본 판정만 제공됩니다."
        if metric_parts:
            segment = filters.get("segment") or "all"
            summary_line = f"질문 '{question[:80]}' 기준으로 세그먼트 {segment}에서 {', '.join(metric_parts[:3])}를 확인했습니다."

        issues = matched[:3]
        issue_line = (
            "; ".join(str(item.get("message") or "").strip() for item in issues if item.get("message"))
            if issues
            else "규칙 임계치를 넘는 항목은 확인되지 않았습니다."
        )

        next_action = (
            "기준치를 넘긴 지표를 기간별·세그먼트별로 다시 조회하고, 필요하면 원본 테이블과 세부 드릴다운을 추가 확인하세요."
            if matched
            else "기간을 넓히거나 다른 세그먼트를 선택해 비교 기준을 보강하세요."
        )

        return (
            f"한 줄 결론: {conclusion}\n"
            f"핵심 요약: {summary_line}\n"
            f"주요 쟁점: {issue_line}\n"
            f"다음 액션: {next_action}"
        )
