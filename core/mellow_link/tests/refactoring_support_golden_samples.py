from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenSampleExpectation:
    sample_name: str
    fallback_goal: str
    expected_primary_judgment: str
    expected_report_purpose: str
    expected_recommended_strategy: str
    expected_first_entry_point: str
    expected_decision_count: int
    expected_top_decision_type: str | None
    expected_top_priority_score: int | None
    expected_top_decision_rule: str | None
    expected_execution_plan_hash: str
    expected_design_options_hash: str
    expected_recommended_option_hash: str
    expected_accounting_can_calculate: bool | None = None


GOLDEN_SAMPLE_EXPECTATIONS: tuple[GoldenSampleExpectation, ...] = (
    GoldenSampleExpectation(
        sample_name="00. rca_exception_case_01",
        fallback_goal="",
        expected_primary_judgment="workflow",
        expected_report_purpose="승인 트리거, 승인 단계, 예외 처리 흐름을 분석하기 위한 보고서입니다.",
        expected_recommended_strategy="재설계 우선",
        expected_first_entry_point="ui:LegacyPage#submit",
        expected_decision_count=19,
        expected_top_decision_type="redesign",
        expected_top_priority_score=12,
        expected_top_decision_rule="detector_id=state_transition_leak 기준으로 다중 컴포넌트/광범위 영향 조건을 확인해 redesign으로 분기했습니다.",
        expected_execution_plan_hash="3106dcfb72e529015acd29860b5307cb3dd001ec",
        expected_design_options_hash="e700271e07ed685a6c32eaa38c471ad6bc7f525d",
        expected_recommended_option_hash="070f62770a8c78431784aad7bb86350621c40cb7",
    ),
    GoldenSampleExpectation(
        sample_name="01. java_order_closure_case_01",
        fallback_goal="",
        expected_primary_judgment="state_transition",
        expected_report_purpose="상태 전이 규칙과 처리 흐름을 분석하기 위한 보고서입니다.",
        expected_recommended_strategy="리팩터링 우선",
        expected_first_entry_point="usecase:order_close_service",
        expected_decision_count=4,
        expected_top_decision_type="refactor",
        expected_top_priority_score=12,
        expected_top_decision_rule="detector_id=ui_data_access_coupling 기준으로 기본 refactor 규칙에 분기했습니다.",
        expected_execution_plan_hash="ca5de017988d630e6a0fd65c924991444e2431b3",
        expected_design_options_hash="22018f0263412d23f55971b55db787cb66eb8544",
        expected_recommended_option_hash="5e3e314bcee7322303e8acff41e7a1a4479a3ce4",
    ),
    GoldenSampleExpectation(
        sample_name="02. python_claim_adjustment_case_01",
        fallback_goal="",
        expected_primary_judgment="query_filter",
        expected_report_purpose="권한 체계, 승인 주체, 조직별 처리 범위를 분석하기 위한 보고서입니다.",
        expected_recommended_strategy="재설계 우선",
        expected_first_entry_point="usecase:claim_adjustment",
        expected_decision_count=19,
        expected_top_decision_type="redesign",
        expected_top_priority_score=15,
        expected_top_decision_rule="detector_id=state_transition_leak 기준으로 다중 컴포넌트/광범위 영향 조건을 확인해 redesign으로 분기했습니다.",
        expected_execution_plan_hash="364cc6049b30dbb93d8426f55f78564710297d92",
        expected_design_options_hash="1fd04aae3f3d698b66175d9a34b865b9ac48a345",
        expected_recommended_option_hash="494d0b28390eb7c3b09d670873a9bb66aa943b2e",
    ),
    GoldenSampleExpectation(
        sample_name="04. amount_limit",
        fallback_goal="금액 한도형 샘플",
        expected_primary_judgment="validation",
        expected_report_purpose="금액 기준, 한도 정책, 경계 조건을 분석하기 위한 보고서입니다.",
        expected_recommended_strategy="리팩터링 우선",
        expected_first_entry_point="usecase:cs_expense_policy",
        expected_decision_count=1,
        expected_top_decision_type="refactor",
        expected_top_priority_score=9,
        expected_top_decision_rule="detector_id=mixed_responsibility 기준으로 기본 refactor 규칙에 분기했습니다.",
        expected_execution_plan_hash="647b3f32501d37ecb9576e57272de1429fd5dca4",
        expected_design_options_hash="53186b26b15e58839731522f43b25e4a71d6902b",
        expected_recommended_option_hash="1b3be67c22e777a6e1513ac3bf6d1209bf5744ed",
    ),
    GoldenSampleExpectation(
        sample_name="01_success_full",
        fallback_goal="전산회계 MVP 기능을 재구성",
        expected_primary_judgment="validation",
        expected_report_purpose="외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다.",
        expected_recommended_strategy="리팩터링 우선",
        expected_first_entry_point="usecase:legacy_flow",
        expected_decision_count=0,
        expected_top_decision_type=None,
        expected_top_priority_score=None,
        expected_top_decision_rule=None,
        expected_execution_plan_hash="147dfc031bc3e756e0417cf65ab36057a5f13f09",
        expected_design_options_hash="da4eaeff6172c713b745116bdc6301bc6a9a3574",
        expected_recommended_option_hash="9c90dd147bfb8c7063de62b03361ae04f9bd2a35",
        expected_accounting_can_calculate=True,
    ),
)
