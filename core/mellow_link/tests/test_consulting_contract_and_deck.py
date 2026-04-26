from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from mellow_link.tests import test_phase3_explanation_and_qa as _phase3_preload  # noqa: F401
from mellow_link.modules.rebuild_assistant.postprocess.consulting_contract import (
    build_consulting_min_contract,
)
from mellow_link.modules.rebuild_assistant.postprocess.consulting_deck import (
    build_consulting_deck,
)
from mellow_link.modules.rebuild_assistant.postprocess.schemas import ConsultingMinContract
from mellow_link.modules.rebuild_assistant.schemas import RebuildAssetsPayload
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.routers.projects import (
    _result_package_markdown,
    _surface_filtered_result_package,
    build_result_package,
)


def _sample_result():
    service = RebuildAssistantService()
    prepared = service.prepare_input(
        goal="주문 조회 흐름을 재구성해줘",
        assets=RebuildAssetsPayload(
            source_code="""
class OrderService:
    def submit(self, order, repo):
        if order.status == "READY":
            repo.save(order)

class OrderQueryService:
    def search(self, keyword, status, page, repo):
        return repo.find(keyword=keyword, status=status, page=page)
            """,
            database_schema="""
CREATE TABLE orders (
    id bigint primary key,
    status varchar(20),
    amount numeric(18, 2)
);
            """,
            sql_queries="""
SELECT id, status, amount
FROM orders
WHERE status = :status
ORDER BY id DESC
            """,
            ui_template="""
<form>
  <input name="keyword" />
  <select name="status"></select>
</form>
            """,
            framework_info="JSP + Spring MVC",
        ),
        constraints=["고객 요청: 조회 조건은 유지", "선호 방향: API 경계 분리"],
    )
    return service.build_result(prepared)


def _sample_project():
    return SimpleNamespace(
        id="proj_consulting_contract",
        project_name="컨설팅 계약 테스트",
        client_name="ACME",
        template_key="rebuild_assistant",
        constraints_json='["고객 요청: 조회 조건은 유지", "선호 방향: API 경계 분리"]',
        status="completed",
        created_at=datetime.now(timezone.utc),
    )


def test_build_consulting_min_contract_maps_source_and_dedupes():
    source = {
        "report_purpose": "조회 구조 판단을 정리합니다.",
        "report_scope": ["주문 조회 흐름"],
        "report_questions": ["조회 모델을 분리할지 판단해야 합니다."],
        "customer_intent": {"items": ["조회 조건은 유지", "API 경계 분리"]},
        "analysis_summary": ["조회 조건이 화면과 SQL에 분산됩니다.", "조회 조건이 화면과 SQL에 분산됩니다."],
        "core_conclusion": "핵심 결론",
        "primary_judgment_reason": "현재 구조와 목표 구조 간 차이를 먼저 줄여야 합니다.",
        "grounded_business_rules": [
            {"title": "조회 조건 분리", "description": "조회 정책을 한 곳에서 관리해야 합니다."},
            {"title": "조회 조건 분리", "description": "조회 정책을 한 곳에서 관리해야 합니다."},
        ],
        "retained_contracts": [{"item": "조회 파라미터 계약"}],
        "decision_items": [
            {"statement": "조회 모델을 먼저 분리합니다.", "rationale": "현재 구조와 목표 구조 간 차이를 먼저 줄여야 합니다."},
            {"statement": "조회 모델을 먼저 분리합니다.", "rationale": "현재 구조와 목표 구조 간 차이를 먼저 줄여야 합니다."},
        ],
        "priority_split_items": [{"reason": "판단 기준은 정합성과 실행 가능성입니다."}],
        "design_options": [
            {"name": "옵션 A. 조회 모델 분리", "structure_summary": "조회 정책을 API 경계로 이동합니다."},
            {"name": "옵션 B. 현행 유지", "structure_summary": "화면과 SQL 분산 구조를 유지합니다."},
        ],
        "recommended_option": {"name": "옵션 A. 조회 모델 분리", "selection_reason": "판단 기준은 정합성과 실행 가능성입니다."},
        "execution_plan": [
            {"week_label": "1주차", "goal": "조회 조건을 정리합니다."},
            {"week_label": "1주차", "goal": "조회 조건을 정리합니다."},
        ],
        "recommended_directions": ["조회 API를 정리합니다."],
        "risks": ["조회 누락 위험이 있습니다.", "조회 누락 위험이 있습니다."],
        "missing_context_details": [{"required_material": "추가 SQL", "reason": "추가 SQL 근거가 필요합니다."}],
    }

    contract = build_consulting_min_contract(source)

    assert contract.as_is == ["조회 조건이 화면과 SQL에 분산됩니다."]
    assert contract.process_flow == ["1주차: 조회 조건을 정리합니다."]
    assert contract.rules == ["조회 조건 분리: 조회 정책을 한 곳에서 관리해야 합니다."]
    assert contract.risks == ["조회 누락 위험이 있습니다."]
    assert contract.gap == ["현재 구조와 목표 구조 간 차이를 먼저 줄여야 합니다."]
    assert contract.actions == ["조회 모델을 먼저 분리합니다.", "조회 조건을 정리합니다."]
    assert contract.context == [
        "조회 구조 판단을 정리합니다.",
        "범위: 주문 조회 흐름",
        "검토 질문: 조회 모델을 분리할지 판단해야 합니다.",
        "사용자 의도: 조회 조건은 유지",
        "사용자 의도: API 경계 분리",
    ]
    assert contract.problem_definition == ["조회 조건이 화면과 SQL에 분산됩니다."]
    assert contract.decision_question == ["조회 모델을 분리할지 판단해야 합니다."]
    assert contract.options == [
        "옵션 A. 조회 모델 분리: 조회 정책을 API 경계로 이동합니다.",
        "옵션 B. 현행 유지: 화면과 SQL 분산 구조를 유지합니다.",
    ]
    assert contract.decision_criteria == ["판단 기준은 정합성과 실행 가능성입니다."]
    assert contract.conclusion == ["핵심 결론"]
    assert "현재 구조와 목표 구조 간 차이를 먼저 줄여야 합니다." in contract.key_reasons
    assert contract.evidence[0] == "조회 조건이 화면과 SQL에 분산됩니다."
    assert contract.assumptions == []
    assert contract.missing_information == ["추가 SQL: 추가 SQL 근거가 필요합니다."]


def test_build_consulting_min_contract_leaves_unsafe_optional_slots_empty_and_keeps_customer_intent_in_context_only():
    source = {
        "report_purpose": "구조 방향을 검토합니다.",
        "customer_intent": {"items": ["전면 재구축을 원함"]},
        "analysis_summary": ["조회 조건이 화면과 SQL에 분산됩니다."],
        "decision_items": [{"statement": "조회 모델 검토", "rationale": "먼저 정리해야 합니다."}],
        "priority_split_items": [{"reason": "먼저 정리해야 합니다."}],
        "design_options": [{"name": "옵션 A. 현행 유지"}],
        "missing_context_details": [{"reason": "추가 로그 확인 필요"}],
    }

    contract = build_consulting_min_contract(source)

    assert contract.context == ["구조 방향을 검토합니다.", "사용자 의도: 전면 재구축을 원함"]
    assert contract.options == []
    assert contract.decision_criteria == []
    assert contract.assumptions == []
    assert contract.conclusion == []


def test_build_consulting_deck_inserts_placeholders_and_keeps_chapter_order():
    deck = build_consulting_deck(
        ConsultingMinContract(),
        project_name="빈 계약",
        client_name="ACME",
        surface_mode="internal",
    )

    assert [chapter["chapter_key"] for chapter in deck["chapters"]] == [
        "overview",
        "approach",
        "implementation",
        "design",
        "vision",
    ]
    assert deck["surface_mode"] == "internal"
    assert deck["chapters"][0]["title"] == "컨설팅 개요"
    assert deck["chapters"][0]["sections"][0]["title"] == "상황 / 목적"
    assert deck["chapters"][0]["sections"][0]["items"] == ["현재 상태 요약 정보가 충분하지 않습니다."]
    assert deck["chapters"][1]["sections"][0]["items"] == ["현재 구조와 목표 구조 간 차이를 추가 확인해야 합니다."]
    assert deck["chapters"][4]["sections"][0]["items"] == ["후속 실행 항목은 추가 분석 후 확정이 필요합니다."]


def test_build_consulting_deck_external_placeholders_follow_surface_policy():
    deck = build_consulting_deck(
        ConsultingMinContract(),
        project_name="빈 계약",
        client_name="ACME",
        surface_mode="external",
    )

    assert deck["surface_mode"] == "external"
    assert deck["chapters"][0]["title"] == "컨설팅 개요"
    assert deck["chapters"][1]["sections"][0]["items"] == ["현재 구조와 목표 구조 간 차이는 추가 확인 전입니다."]
    assert deck["chapters"][4]["sections"][0]["items"] == ["후속 실행 항목은 추가 분석 후 확정 전입니다."]


def test_build_consulting_deck_reduces_repetition_and_filters_fx_fifo_overview_noise():
    contract = ConsultingMinContract(
        context=["외화 FIFO 운영 판단을 정리합니다."],
        problem_definition=["입금 lot 잔량과 출금 lot 소진 순서를 분리해야 동일 거래 계산이 흔들리지 않습니다."],
        decision_question=["현행 FIFO 기준을 유지할지 판단해야 합니다."],
        decision_criteria=["비교 기준은 계산 재현성과 회계 연결 검증 가능성입니다."],
        conclusion=["현행 FIFO 기준 유지와 예외 검증 보강"],
        key_reasons=["거래 기준번호와 회계 연결 기준을 함께 검증할 수 있습니다."],
        evidence=["입금 lot 원장과 출금 lot 소진 순서가 분리돼 있지 않습니다."],
        missing_information=["실거래 예외 케이스 추가 확인 필요"],
        as_is=[
            "SQL 또는 데이터 접근 로직이 UI 가깝게 결합되어 있습니다.",
            "대표 도메인 범위는 외화 입출금 FIFO 중심으로 정리하는 편이 적절합니다.",
            "기존 스키마 호환성을 유지해야 하므로 API 백엔드 분리 시 DB 계약을 우선 보존해야 합니다.",
        ],
        process_flow=[
            "1주차: 입금 lot 원장과 출금 lot 소진 순서를 구조화합니다.",
            "2주차: FIFO 계산·회계 연계 분리 구조 기준으로 환차손익 계산과 회계 연계 구조를 설계합니다.",
            "3주차: 외화 입출금 FIFO 계산 서비스와 전표 생성 흐름에 핵심 규칙을 반영합니다.",
            "4주차: 외화 입출금 FIFO lot 추적, 환차손익, 전표 정합성을 규칙 기준으로 검증합니다.",
        ],
        rules=[
            "통화 및 계좌 식별값 유지: 통화 코드와 계좌 식별 값은 lot 계산, 전표, GL 반영 전 과정에서 일관되게 유지해야 합니다.",
            "환차손익 계산: lot별 취득 환율과 출금 환율 차이로 환차손익을 계산해야 합니다.",
        ],
        risks=[
            "FIFO lot 소진 순서가 바뀌면 동일 출금 건의 원가와 lot 추적 결과가 달라질 수 있습니다.",
        ],
        gap=[
            "입금 lot 잔량과 출금 lot 소진 순서를 분리해야 동일 거래의 원가 계산과 lot 추적이 흔들리지 않습니다.",
        ],
        actions=[
            "외화 입출금 FIFO 흐름의 입금 lot 적재와 출금 lot 소진 계산을 별도 FIFO 계산 계층으로 분리하는 것이 필요합니다.",
            "외화 입출금 FIFO 흐름의 환차손익 계산을 lot별 취득 환율과 출금 환율 비교 정책으로 고정하는 것이 필요합니다.",
            "외화 입출금 FIFO 흐름의 전표 생성과 GL_INTERFACE 적재를 계산 결과와 같은 거래 기준번호로 연결하는 것이 필요합니다.",
            "입금 lot 원장과 출금 lot 소진 순서를 구조화합니다.",
        ],
    )

    deck = build_consulting_deck(
        contract,
        project_name="선입선출 외화관리",
        client_name="ACME",
        surface_mode="internal",
    )

    overview_items = deck["chapters"][0]["sections"][0]["items"]
    judgment_items = deck["chapters"][1]["sections"][0]["items"]
    risk_items = deck["chapters"][1]["sections"][1]["items"]
    implementation_action_items = deck["chapters"][2]["sections"][1]["items"]
    design_rule_items = deck["chapters"][3]["sections"][0]["items"]
    design_flow_items = deck["chapters"][3]["sections"][1]["items"]
    vision_items = deck["chapters"][4]["sections"][0]["items"]

    assert overview_items == [
        "[상황 / 목적] 외화 FIFO 운영 판단을 정리합니다",
        "[문제 정의] 입금 lot 잔량과 출금 lot 소진 순서를 분리해야 동일 거래 계산이 흔들리지 않습니다",
    ]
    assert "[판단 질문] 현행 FIFO 기준을 유지할지 판단해야 합니다" in judgment_items
    assert "[결론] 검증 후 적용: 현행 FIFO 기준 유지와 예외 검증 보강" in judgment_items
    assert any(item.startswith("[누락된 정보]") for item in risk_items)
    assert implementation_action_items == [
        "[중점 실행 과제] 입금 lot 적재와 출금 lot 소진 계산을 별도 FIFO 계산 계층으로 분리",
        "환차손익 계산을 lot별 취득 환율과 출금 환율 비교 정책으로 고정",
        "전표 생성과 GL_INTERFACE 적재를 계산 결과와 같은 거래 기준번호로 연결",
    ]
    assert design_rule_items[0] == "[근거] 입금 lot 원장과 출금 lot 소진 순서가 분리돼 있지 않습니다"
    assert any(item.startswith("[핵심 규칙]") for item in design_rule_items)
    assert design_flow_items == [
        "[설계 흐름] 입금 lot 원장과 출금 lot 소진 순서를 구조화합니다",
        "FIFO 계산·회계 연계 분리 구조 기준으로 환차손익 계산과 회계 연계 구조를 설계합니다",
        "외화 입출금 FIFO 계산 서비스와 전표 생성 흐름에 핵심 규칙을 반영합니다",
    ]
    assert vision_items[0] == "[적용 방향] 입금 lot 적재와 출금 lot 소진 계산을 별도 FIFO 계산 계층으로 분리 체계"
    assert any(item.startswith("[후속 판단 포인트]") for item in vision_items)


def test_build_consulting_deck_softens_conclusion_when_missing_information_exists():
    deck = build_consulting_deck(
        ConsultingMinContract(
            decision_question=["조회 모델을 분리할지 판단해야 합니다."],
            conclusion=["옵션 A. 조회 모델 분리"],
            missing_information=["추가 호출 로그 확인 필요"],
        ),
        project_name="판단 구조",
        client_name="ACME",
        surface_mode="internal",
    )

    judgment_items = deck["chapters"][1]["sections"][0]["items"]
    risk_items = deck["chapters"][1]["sections"][1]["items"]

    assert "[결론] 검증 후 적용: 옵션 A. 조회 모델 분리" in judgment_items
    assert any(item.startswith("[누락된 정보]") for item in risk_items)


def test_build_consulting_deck_external_surface_simplifies_internal_labels():
    deck = build_consulting_deck(
        ConsultingMinContract(
            context=["주문 생성 구조 판단을 정리합니다."],
            problem_definition=["상태 전이 로직이 여러 위치에 분산됩니다."],
            decision_question=["주문 생성 경계를 분리할지 판단해야 합니다."],
            options=["옵션 A: 서비스 경계 분리"],
            decision_criteria=["정합성과 실행 가능성을 우선합니다."],
            conclusion=["옵션 A를 우선 적용합니다."],
            key_reasons=["상태 전이 로직이 여러 위치에 분산됩니다."],
            missing_information=["실운영 예외 케이스: 추가 확인 필요"],
        ),
        project_name="판단 구조",
        client_name="ACME",
        surface_mode="external",
    )

    overview_items = deck["chapters"][0]["sections"][0]["items"]
    judgment_items = deck["chapters"][1]["sections"][0]["items"]
    risk_items = deck["chapters"][1]["sections"][1]["items"]

    assert all("[" not in item for item in overview_items + judgment_items + risk_items)
    assert overview_items[0] == "주문 생성 구조 판단을 정리합니다"
    assert any(item.startswith("문제: ") for item in overview_items)
    assert len(judgment_items) <= 3
    assert any(item.startswith("검증 후 적용: ") or item.startswith("조건 확인 후 실행: ") or item.startswith("실행 착수 가능: ") or item.startswith("실행 불가: ") for item in judgment_items)
    assert any(item.startswith("이유: ") for item in judgment_items)
    assert all(len(item) <= 40 for item in judgment_items)
    assert not any("검증 후 적용: 검증 후 적용:" in item for item in judgment_items)
    assert "우선 검토안" not in " ".join(judgment_items)
    assert "후보" not in " ".join(judgment_items)
    assert any(item.startswith("추가 확인 필요: ") for item in risk_items)


def test_build_consulting_deck_external_surface_uses_technical_style_for_code_like_contract():
    deck = build_consulting_deck(
        ConsultingMinContract(
            problem_definition=["저장 전 차단 조건과 예외 처리 규칙이 한 흐름에 섞여 있습니다."],
            risks=["차단 조건 누락 시 저장 흐름이 흔들릴 수 있습니다."],
            actions=["검증 규칙을 별도 계층으로 분리합니다."],
            rules=["저장 전 차단 조건을 먼저 검증해야 합니다."],
            evidence=["SQL 조건 매핑과 저장 규칙이 같은 경계에 섞여 있습니다."],
            process_flow=["1주차: 검증 규칙 구조화", "2주차: 저장 흐름 검증"],
        ),
        project_name="기술 판단",
        client_name="ACME",
        surface_mode="external",
    )

    sections = {
        (chapter["chapter_key"], section["section_key"]): section
        for chapter in deck["chapters"]
        for section in chapter["sections"]
    }
    assert sections[("overview", "as_is")]["title"] == "핵심 문제"
    assert sections[("approach", "risks")]["title"] == "영향"
    assert sections[("implementation", "actions")]["title"] == "권장 조치"
    assert sections[("design", "rules")]["title"] == "검증 포인트"
    assert any(item.startswith("핵심 문제: ") for item in sections[("overview", "as_is")]["items"])


def test_build_consulting_deck_external_surface_uses_mixed_style_for_document_plus_code_contract():
    deck = build_consulting_deck(
        ConsultingMinContract(
            context=["컨설팅 개요와 기술 적용 기준을 함께 설명합니다."],
            problem_definition=["현행 문서 설명과 저장 검증 규칙이 함께 존재합니다."],
            evidence=["SQL 조건 매핑과 개선 방향 문서가 함께 확인됩니다."],
            process_flow=["1단계: 개선 방향 정리", "2단계: SQL 검증 포인트 확인"],
            rules=["저장 전 차단 조건을 먼저 검증해야 합니다."],
        ),
        project_name="혼합 판단",
        client_name="ACME",
        surface_mode="external",
    )

    sections = {
        (chapter["chapter_key"], section["section_key"]): section
        for chapter in deck["chapters"]
        for section in chapter["sections"]
    }
    assert sections[("implementation", "process_flow")]["title"] == "코드 분석 포인트"
    assert sections[("design", "rules")]["title"] == "코드 검증 포인트"


def test_build_result_package_includes_consulting_contract_and_internal_deck():
    result = _sample_result()
    pkg = build_result_package(
        _sample_project(),
        {"status": "completed", "run_id": "run_consulting_contract"},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    contract = pkg["consulting_min_contract"]
    deck = pkg["consulting_deck"]
    slide_schema = pkg["slide_schema"]

    assert {
        "as_is",
        "process_flow",
        "rules",
        "risks",
        "gap",
        "actions",
        "context",
        "problem_definition",
        "decision_question",
        "options",
        "decision_criteria",
        "conclusion",
        "key_reasons",
        "evidence",
        "assumptions",
        "missing_information",
    } <= set(contract.keys())
    assert isinstance(contract["as_is"], list)
    assert isinstance(deck["chapters"], list)
    assert isinstance(slide_schema["slides"], list)
    assert deck["surface_mode"] == "internal"
    assert deck["chapters"][0]["title"] == "컨설팅 개요"
    assert deck["chapters"][2]["title"] == "컨설팅 구현"
    slide_types = [slide["slide_type"] for slide in slide_schema["slides"]]
    assert slide_types[0] == "overview"
    assert {"overview", "as_is_gap", "flow", "design", "vision"} <= set(slide_types)


def test_surface_filtered_result_package_rebuilds_consulting_deck_for_external_surface():
    result = _sample_result()
    pkg = build_result_package(
        _sample_project(),
        {"status": "completed", "run_id": "run_consulting_contract_surface"},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    filtered = _surface_filtered_result_package(pkg, surface_mode="external")

    assert filtered["consulting_deck"]["surface_mode"] == "external"
    assert filtered["slide_schema"]["surface_mode"] == "external"
    assert filtered["consulting_deck"]["chapters"][0]["title"] == "컨설팅 개요"
    assert filtered["consulting_deck"]["chapters"][1]["title"] == "컨설팅 전개"
    assert filtered["consulting_deck"]["chapters"][2]["title"] == "컨설팅 구현"


def test_result_package_markdown_prefers_consulting_deck_and_separates_internal_appendix():
    result = _sample_result()
    pkg = build_result_package(
        _sample_project(),
        {"status": "completed", "run_id": "run_consulting_contract_markdown"},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    internal_markdown = _result_package_markdown(pkg, surface_mode="internal")
    internal_full_markdown = _result_package_markdown(pkg, surface_mode="internal", internal_export_mode="full")
    external_markdown = _result_package_markdown(pkg, surface_mode="external")

    assert "## 컨설팅 개요" in internal_markdown
    assert "## 컨설팅 전개" in internal_markdown
    assert "## 컨설팅 설계" in internal_markdown
    assert "## 컨설팅 비전" in internal_markdown
    assert "## 컨설팅 구현" in internal_markdown
    assert "## 참고 구조 비교" not in internal_markdown
    assert "### 문서 맥락" not in internal_markdown
    assert "### 상황 / 목적" in internal_markdown
    assert "[판단 질문]" in internal_markdown

    assert "## 참고 구조 비교" in internal_full_markdown
    assert "### 문서 맥락" in internal_full_markdown

    assert "## 컨설팅 개요" in external_markdown
    assert "## 컨설팅 전개" in external_markdown
    assert "## 컨설팅 구현" in external_markdown
    assert "필요합니다" not in external_markdown
    assert "[판단 질문]" not in external_markdown
    assert "[결론]" not in external_markdown
    assert "[핵심 이유]" not in external_markdown
    assert "## 참고 구조 비교" not in external_markdown


def test_generic_consulting_deck_markdown_keeps_chapter_order_without_duplicate_intro_blocks():
    result = _sample_result()
    pkg = build_result_package(
        _sample_project(),
        {"status": "completed", "run_id": "run_consulting_contract_markdown_order"},
        result,
        assets=[],
        polish_bundle=None,
        app_version="0.1.0",
    )

    markdown = _result_package_markdown(pkg, surface_mode="internal")
    headings = [line.strip() for line in markdown.splitlines() if line.startswith("## ")]

    assert headings == [
        "## 컨설팅 개요",
        "## 컨설팅 전개",
        "## 컨설팅 구현",
        "## 컨설팅 설계",
        "## 컨설팅 비전",
    ]
    assert markdown.count("## 컨설팅 개요") == 1
    assert markdown.count("## 컨설팅 전개") == 1
    assert markdown.count("### 상황 / 목적") == 1
    assert "\n\n\n" not in markdown
