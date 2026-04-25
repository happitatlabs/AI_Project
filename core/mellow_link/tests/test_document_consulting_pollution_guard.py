from __future__ import annotations

import json

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService

from .refactoring_support_test_utils import build_safe_bundle


def _run_document_result(*, name: str, content: str):
    service = RebuildAssistantService()
    safe_bundle = build_safe_bundle([{"name": name, "content": content}])
    prepared = service.prepare_safe_bundle_input(goal="", safe_bundle=safe_bundle, constraints=[])
    result = service.build_result(prepared)
    return prepared, json.dumps(result.model_dump(mode="json"), ensure_ascii=False)


def test_document_only_cost_sml_blocks_save_and_sql_pollution():
    prepared, result_text = _run_document_result(
        name="3부산우유컨설팅구현.ppt",
        content="""
[SML v1]
presentation_file: 3부산우유컨설팅구현.ppt
slide_count: 1

[SLIDE 1]
title: 원가계산 구현 방향
texts:
- 원가 계산과 손익 분석 연결 구조
- 재료비 노무비 제조경비 배부 기준 정리
- insert into temp_cost_result
- update tb_cost_summary set total_amt = :amt where cost_cd = :cost_cd
- save before validation
""".strip(),
    )
    assert prepared.signals.primary_feature_mode == "general"
    assert prepared.selected_narrative_judgment == ""
    assert "저장 전 검증" not in result_text
    assert "sql 파라미터" not in result_text.lower()
    assert "product 기능" not in result_text.lower()
    assert any(keyword in result_text for keyword in ("원가", "배부", "손익"))


def test_document_only_cost_doc_does_not_promote_product_feature():
    prepared, result_text = _run_document_result(
        name="2부산우유컨설팅전개.ppt",
        content="""
[SML v1]
presentation_file: 2부산우유컨설팅전개.ppt
slide_count: 1

[SLIDE 1]
title: 부산우유 원가 컨설팅 전개
texts:
- Product Lifecycles
- 원가 분석 방향과 재료비 노무비 제조경비 배부 기준
- 손익 분석 연결 구조
""".strip(),
    )
    assert prepared.signals.primary_feature_mode == "general"
    assert prepared.selected_narrative_judgment == ""
    assert "product 기능" not in result_text.lower()
    assert "저장 전 검증" not in result_text


def test_document_only_generic_consulting_uses_neutral_fallback():
    prepared, result_text = _run_document_result(
        name="0업무구성도.ppt",
        content="""
[SML v1]
presentation_file: 0업무구성도.ppt
slide_count: 1

[SLIDE 1]
title: 업무 구성도
texts:
- 현행 구조와 개선 방향
- 판단 기준과 비교 항목
- 단계별 계획과 누락 정보
""".strip(),
    )
    assert prepared.signals.primary_feature_mode == "general"
    assert prepared.selected_primary_judgment == ""
    assert prepared.selected_narrative_judgment == ""
    assert "저장 전 검증" not in result_text
    assert "sql 파라미터" not in result_text.lower()
    assert "현행" in result_text
    assert "개선" in result_text
