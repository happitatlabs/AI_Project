from __future__ import annotations

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

from .refactoring_support_test_utils import load_expansion_sample_case


def test_query_filter_low_intensity_sample_stays_neutral():
    service = RebuildAssistantService()
    case = load_expansion_sample_case("01_crud_simple")
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )

    result = service.build_result(prepared)
    decisions = result.decision_summary.get("decisions", [])
    rendered = " ".join(
        [result.primary_judgment_reason, result.one_line_conclusion]
        + list(result.executive_summary_v2)
        + [item for item in result.risks]
        + [week.goal for week in result.execution_plan]
        + list(result.recommended_directions)
    )

    assert service._resolve_domain_anchor(prepared) is None
    assert service._primary_concept(prepared) == "조회/필터"
    assert result.primary_judgment == "query_filter"
    assert result.extensions.get("narrative", {}).get("axis") == "query_filter"
    if result.family_classification.family == "operational_source":
        assert result.report_purpose == "현행 운영 로직, 데이터 흐름, 처리 순서를 분석하기 위한 보고서입니다."
        assert result.one_line_conclusion.startswith("본 자산은")
        assert result.executive_summary_v2[0].startswith("현행 분석:")
    else:
        assert result.report_purpose == "조회 조건, 필터 조합, 정렬 및 결과 구성 규칙을 분석하기 위한 보고서입니다."
    assert len(decisions) == 0
    assert result.decision_items == []
    if result.family_classification.family == "operational_source":
        assert result.primary_judgment_reason == "입력 자산이 실제 운영 처리와 후속 반영을 담당하는 현행 자산이므로 현재 단계에서는 현행 업무 규칙과 처리 흐름 복원이 우선입니다."
    else:
        assert result.primary_judgment_reason == "직접 확인된 강한 구조 결정은 없지만 조회 조건과 필터 조합 신호가 가장 뚜렷하게 확인됐습니다."
        assert result.one_line_conclusion == "조회/필터 기능은 현재 자산 기준으로 조회 조건, 필터 조합, 결과 목록 구성을 한곳에서 정리하는 방향을 우선 검토하는 편이 적절합니다."
    assert "주문 마감" not in rendered


def test_query_filter_low_intensity_sample_summary_has_no_immediate_decision():
    service = RebuildAssistantService()
    case = load_expansion_sample_case("01_crud_simple")
    prepared = service.prepare_safe_bundle_input(
        goal=case["goal"],
        safe_bundle=case["safe_bundle"],
        constraints=case["constraints"],
    )

    result = service.build_result(prepared)
    summary = service.format_user_summary(
        result,
        scope_limited=prepared.scope_limited,
        needs_more_input=bool(result.missing_context),
    )

    assert "## 실행 조치" in summary
    assert "즉시 결정할 항목이 없습니다." not in summary
    assert "주문 마감" not in summary
