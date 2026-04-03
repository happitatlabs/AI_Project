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
        expected_execution_plan_hash="326689871d29c7c2ae1d0ef9f95725d5160522aa",
        expected_design_options_hash="5ee6adb76bc211136ed8ad6d8497ec5fab7fef64",
        expected_recommended_option_hash="1e5260914876e716722eea179d0b8cfc98d2ac77",
    ),
    GoldenSampleExpectation(
        sample_name="01. java_order_closure_case_01",
        fallback_goal="",
        expected_primary_judgment="state_transition",
        expected_report_purpose="상태 전이 규칙과 처리 흐름을 분석하기 위한 보고서입니다.",
        expected_recommended_strategy="리팩터링 우선",
        expected_first_entry_point="usecase:이_jsp_java",
        expected_decision_count=4,
        expected_top_decision_type="refactor",
        expected_top_priority_score=12,
        expected_top_decision_rule="detector_id=ui_data_access_coupling 기준으로 기본 refactor 규칙에 분기했습니다.",
        expected_execution_plan_hash="ca5de017988d630e6a0fd65c924991444e2431b3",
        expected_design_options_hash="7ced99f3796f265b667d993db1390f3dfb394159",
        expected_recommended_option_hash="380575d2955ba37ef0048817f223df976b322912",
    ),
    GoldenSampleExpectation(
        sample_name="02. python_claim_adjustment_case_01",
        fallback_goal="",
        expected_primary_judgment="query_filter",
        expected_report_purpose="권한 체계, 승인 주체, 조직별 처리 범위를 분석하기 위한 보고서입니다.",
        expected_recommended_strategy="재설계 우선",
        expected_first_entry_point="usecase:이_python_flask",
        expected_decision_count=19,
        expected_top_decision_type="redesign",
        expected_top_priority_score=15,
        expected_top_decision_rule="detector_id=state_transition_leak 기준으로 다중 컴포넌트/광범위 영향 조건을 확인해 redesign으로 분기했습니다.",
        expected_execution_plan_hash="e28453741d0fc8e76fcbd58436bb45e54411c339",
        expected_design_options_hash="75eb9b9c068052a7c1d485723a569d0049c08fdf",
        expected_recommended_option_hash="e8e8df624c7a64c503c94361aea84ade63be7aaf",
    ),
    GoldenSampleExpectation(
        sample_name="04. amount_limit",
        fallback_goal="금액 한도형 샘플",
        expected_primary_judgment="validation",
        expected_report_purpose="금액 기준, 한도 정책, 경계 조건을 분석하기 위한 보고서입니다.",
        expected_recommended_strategy="리팩터링 우선",
        expected_first_entry_point="usecase:금액_한도형_샘플",
        expected_decision_count=1,
        expected_top_decision_type="refactor",
        expected_top_priority_score=9,
        expected_top_decision_rule="detector_id=mixed_responsibility 기준으로 기본 refactor 규칙에 분기했습니다.",
        expected_execution_plan_hash="647b3f32501d37ecb9576e57272de1429fd5dca4",
        expected_design_options_hash="588b63fffbe0fcf6a701924cd5ccb5625850cb92",
        expected_recommended_option_hash="dd81cdcdfd395959b1d638eff9cb0f372225bdc5",
    ),
    GoldenSampleExpectation(
        sample_name="01_success_full",
        fallback_goal="전산회계 MVP 기능을 재구성",
        expected_primary_judgment="validation",
        expected_report_purpose="외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다.",
        expected_recommended_strategy="리팩터링 우선",
        expected_first_entry_point="usecase:전산회계_mvp_기능을",
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
