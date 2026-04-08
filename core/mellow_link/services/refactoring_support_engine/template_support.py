from __future__ import annotations

import re
from typing import Any

from mellow_link.modules.rebuild_assistant.schemas import (
    AppliedJudgmentTemplate,
    DecisionItem,
    DesignOption,
    EvidenceRef,
    ExecutionPlanWeek,
    GroundedBusinessRule,
    LayeredListResult,
    PrioritySplitItem,
    RecommendedOption,
    RetainedContract,
    VerificationItem,
)

from .decision_catalog import JudgmentTemplateId, get_judgment_template_spec
from .schemas import PreparedRebuildInput


class TemplateSupport:
    def _active_narrative_judgment(self, prepared: PreparedRebuildInput) -> str:
            return (
                (prepared.selected_narrative_judgment or "").strip()
                or (prepared.selected_primary_judgment or "").strip()
            )

    def _primary_template(
        self,
        prepared: PreparedRebuildInput,
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> AppliedJudgmentTemplate | None:
            from mellow_link.services.refactoring_support_engine.judgment_synthesizer import JudgmentSynthesizer

            return JudgmentSynthesizer(self).primary_template(prepared, applied_templates)

    def _ordered_templates_for_generation(
        self,
        prepared: PreparedRebuildInput,
        applied_templates: list[AppliedJudgmentTemplate],
        grounded_rules: list[GroundedBusinessRule] | None = None,
    ) -> list[AppliedJudgmentTemplate]:
            from mellow_link.services.refactoring_support_engine.judgment_synthesizer import JudgmentSynthesizer

            return JudgmentSynthesizer(self).ordered_templates_for_generation(
                prepared,
                applied_templates,
                grounded_rules,
            )

    def infer_target_architecture(self, prepared: PreparedRebuildInput) -> list[str]:
            concept = self._primary_concept(prepared)
            primary = prepared.signals.primary_feature_mode
            secondary = prepared.signals.secondary_feature_mode
            strategy = [
                f"{concept} 기능을 단일 범위에서 화면, 업무 처리 API, 데이터 접근 책임으로 분리하는 구조로 재구성합니다.",
                f"화면은 업무 흐름 중심으로 나누고, 상태 판단은 공통 규칙에 따라 일관되게 처리하도록 구성합니다.",
                f"백엔드는 {concept} 전용 API, 업무 서비스, 데이터 접근 계층으로 나눠 기존 SQL 의존도를 단계적으로 축소합니다.",
            ]
            if primary == "status_permissions":
                strategy.append("권한과 상태 전이 규칙을 핵심 흐름으로 보고, 처리 가능 여부 판단을 정책 계층으로 분리합니다.")
            elif primary == "search_filters":
                strategy[1] = "화면은 조회 조건 입력 영역과 결과 표시 영역으로 나누고 검색 상태를 별도로 관리하도록 구성합니다."
                strategy[2] = f"백엔드는 {concept} 조회 API와 데이터 접근 규칙을 분리해 검색 조건과 SQL 조건 매핑을 명확히 합니다."
                strategy.append("조회 조건 규칙을 핵심 흐름으로 보고 조회 파라미터, 필터 상태, 정렬 규칙을 별도 조회 모델로 분리합니다.")
            elif primary == "save_validation":
                strategy.append("저장 검증 규칙을 핵심 흐름으로 보고 입력 검증, 중복 체크, 저장 전 차단 규칙을 별도 검증 계층으로 분리합니다.")
            if secondary == "status_permissions":
                strategy.append("보조 신호로 권한 및 상태 규칙이 감지되어 액션 노출과 상태 전이 규칙도 함께 정리합니다.")
            elif secondary == "search_filters":
                strategy.append("보조 신호로 조회 조건 규칙이 감지되어 필터 상태와 조회 파라미터 정규화도 함께 반영합니다.")
            elif secondary == "save_validation":
                strategy.append("보조 신호로 저장 검증 규칙이 감지되어 저장 전 차단 규칙과 중복 체크도 함께 반영합니다.")
            if prepared.scope_limited:
                strategy.insert(0, "요청 범위가 V0 한계를 넘으므로 전체 마이그레이션 대신 단일 기능 재구성 전략으로 축소합니다.")
            return strategy[:6]
    
    def build_layer_reconstruction(self, prepared: PreparedRebuildInput) -> LayeredListResult:
            concept = self._primary_concept(prepared)
            resource = self._resource_name(prepared)
            primary = prepared.signals.primary_feature_mode
            secondary = prepared.signals.secondary_feature_mode
            database = [
                f"{concept} 관련 테이블과 컬럼 계약은 유지하되 조회와 저장 책임을 데이터 접근 계층으로 이동합니다.",
            ]
            if primary == "search_filters":
                database.append("조회 조건과 필터 조합을 명시적 SQL 조건 매핑 규칙으로 정리하고 동적 문자열 결합을 제거합니다.")
            elif primary == "save_validation":
                database.append("중복 체크와 저장 전 선행 조회는 저장 커맨드와 분리된 제약 검사 쿼리로 정리합니다.")
            elif primary == "status_permissions":
                database.append("상태 전이와 권한 판정에 필요한 상태 기준 컬럼은 읽기 모델에서 명시적으로 조회합니다.")
            else:
                database.append("복잡한 조인과 조건식은 재사용 가능한 조회 규칙 또는 읽기 전용 조회 구조로 정리합니다.")
            if secondary == "save_validation" and primary != "save_validation":
                database.append("중복 체크와 저장 전 선행 조회는 저장 커맨드와 분리된 제약 검사 쿼리로 정리합니다.")
            elif secondary == "search_filters" and primary != "search_filters":
                database.append("보조 조회 신호를 반영해 주요 검색 조건은 파라미터 바인딩으로 고정합니다.")
            if prepared.assets.database_schema or prepared.assets.sql_queries:
                database.append("스키마 변경은 최소화하고 V0에서는 호환 레이어를 우선 설계합니다.")
    
            backend = [
                f"{concept} 기능 전용 API와 업무 서비스 계층을 분리합니다.",
            ]
            if primary == "status_permissions":
                backend.append("역할별 처리 가능 여부 판단을 정책 서비스로 추출합니다.")
                backend.append("상태 전이 허용 여부를 transition policy로 분리해 화면 분기와 저장 로직에서 공용 사용합니다.")
            elif primary == "search_filters":
                backend[0] = f"{concept} 검색 전용 API와 조회 서비스 계층을 분리합니다."
                backend.append("검색 조건 입력은 정렬, 페이징, 필터 항목으로 나누어 명시적으로 매핑합니다.")
                backend.append("동적 검색 조건은 조회 규칙 표에 따라 관리합니다.")
            elif primary == "save_validation":
                backend.append("저장 전 차단 규칙, 중복 체크, 입력 검증을 별도 검증 계층으로 분리합니다.")
                backend.append("저장 전 제약 검사는 저장 처리와 분리해 선행 검증 단계에서 수행합니다.")
            if secondary == "status_permissions" and primary != "status_permissions":
                backend.append("보조 정책 신호를 반영해 주요 액션 노출 조건은 policy service에서 계산합니다.")
            elif secondary == "search_filters" and primary != "search_filters":
                backend.append("보조 조회 신호를 반영해 query DTO를 함께 둡니다.")
            elif secondary == "save_validation" and primary != "save_validation":
                backend.append("보조 저장 신호를 반영해 핵심 저장 경로에 validator를 둡니다.")
            if primary == "general":
                backend.append("서비스 계층에서 JSP 내 조건문과 분기 로직을 명시적 비즈니스 규칙으로 추출합니다.")
    
            frontend = [
                f"{concept} 화면을 기준으로 상위 화면과 하위 업무 구성 요소를 분리합니다.",
            ]
            if primary == "status_permissions":
                frontend.append("사용자 역할과 엔티티 상태에 따른 버튼 노출/비활성화 규칙을 UI policy hook으로 분리합니다.")
            elif primary == "search_filters":
                frontend[0] = f"{concept} 화면을 기준으로 조회 조건 입력 영역과 결과 목록 영역을 분리합니다."
                frontend.append("검색 필터 상태, 폼 값, 결과 목록 상태를 별도 query state 모델로 관리합니다.")
            elif primary == "save_validation":
                frontend.append("저장 폼 검증 메시지와 제출 가드를 view model 또는 form schema 기준으로 분리합니다.")
            if secondary == "status_permissions" and primary != "status_permissions":
                frontend.append("보조 정책 신호를 반영해 액션 버튼 가시성 계산을 분리합니다.")
            elif secondary == "search_filters" and primary != "search_filters":
                frontend.append("보조 조회 신호를 반영해 필터 상태를 별도 query state로 유지합니다.")
            elif secondary == "save_validation" and primary != "save_validation":
                frontend.append("보조 저장 신호를 반영해 제출 전 검증 메시지를 분리합니다.")
            if not (prepared.assets.source_code or prepared.assets.ui_template):
                frontend = ["화면 자산이 부족하므로 프론트엔드는 API 계약 기준의 최소 컴포넌트 분해만 제안합니다."]
            return LayeredListResult(database=database[:4], backend=backend[:4], frontend=frontend[:4])
    
    def build_recomposition_draft(
            self,
            prepared: PreparedRebuildInput,
            applied_templates: list[AppliedJudgmentTemplate] | None = None,
        ) -> LayeredListResult:
            concept = self._primary_concept(prepared)
            primary = prepared.signals.primary_feature_mode
            secondary = prepared.signals.secondary_feature_mode
            primary_template = self._primary_template(prepared, applied_templates or [])
            primary_template_id = primary_template.template_id if primary_template else ""
            if self._should_force_amount_threshold_narrative(prepared, []):
                primary_template_id = "amount_threshold"
    
            if primary_template_id == "workflow":
                database = [
                    f"예시: {concept} 승인 트리거, 승인 주체, 단계별 승인 상태를 워크플로우 기준 컬럼으로 분리합니다.",
                ]
            elif primary_template_id == "state_transition":
                database = [
                    f"예시: {concept} 상태 컬럼, 처리 가능 상태, 전이 결과 반영 기준을 읽기/쓰기 경계로 분리합니다.",
                ]
            elif primary_template_id == "access_control":
                database = [
                    f"예시: {concept} 승인 주체, 부서별 처리 권한, 예외 승인 경로를 정책 기준 컬럼으로 정리합니다.",
                ]
            elif primary_template_id == "query_filter":
                database = [
                    f"예시: {self._compose_concept_goal(concept, '조회 조건, 정렬 기준, 페이징 규칙을 조회 모델 경계로 분리합니다.')}",
                ]
            elif primary_template_id == "amount_threshold":
                database = [
                    f"예시: {concept} 금액 구간, 한도 임계값, 고액 처리 기준을 정책 기준 컬럼으로 정리합니다.",
                ]
            else:
                database = [
                    f"예시: {concept} 조회 경로와 저장 경로를 분리해 데이터 접근 책임을 명확히 합니다.",
                ]
            if primary_template_id == "workflow":
                database.append("예시: 승인 단계, 승인 주체, 예외 승인 경로를 워크플로우 기준 컬럼으로 명시해 조회합니다.")
            elif primary == "search_filters":
                database.append("예시: 조회 조건 매핑 규칙을 두고 WHERE 절은 바인딩 파라미터로만 조립합니다.")
            elif primary_template_id == "validation":
                database.append("예시: 저장 전 중복 여부와 상태 충돌을 확인하는 선행 검사 쿼리를 분리합니다.")
            elif primary_template_id == "access_control":
                database.append("예시: 승인 주체, 부서별 처리 권한, 예외 승인 경로를 정책 기준 컬럼으로 명시해 조회합니다.")
            elif primary_template_id == "query_filter":
                database.append("예시: 필터 조건과 정렬 기준은 조회 파라미터 규칙으로 명시해 조회합니다.")
            elif primary_template_id == "amount_threshold":
                database.append("예시: 금액 한도와 임계값 비교에 필요한 컬럼을 정책 기준으로 명시해 조회합니다.")
            elif primary_template_id == "state_transition" or primary == "status_permissions":
                database.append("예시: 상태 표시와 처리 가능 여부 계산에 필요한 컬럼을 읽기 전용 조회 구조로 묶어 관리합니다.")
            if secondary == "search_filters" and primary != "search_filters":
                database.append("예시: 보조 조회 신호를 반영해 조회 조건 매핑 규칙을 함께 둡니다.")
            elif secondary == "save_validation" and primary_template_id not in {"state_transition", "access_control", "validation", "query_filter", "amount_threshold"} and primary != "save_validation":
                database.append("예시: 보조 저장 신호를 반영해 중복 검사 쿼리를 추가합니다.")
            if not prepared.assets.database_schema and not prepared.assets.sql_queries:
                database = [f"DB 자산이 부족하므로 {concept} 데이터 접근 인터페이스와 파라미터 계약 초안만 제공합니다."]
    
            if primary_template_id == "workflow":
                backend = [
                    f"예시: {concept} 승인 요청 API와 승인 처리 API를 분리해 워크플로우 기본 구조를 정리합니다.",
                ]
            elif primary_template_id == "state_transition":
                backend = [
                    f"예시: {concept} 상태 전이 API와 처리 가능 상태 판단 API를 분리해 기본 구조를 정리합니다.",
                ]
            elif primary_template_id == "access_control":
                backend = [
                    f"예시: {concept} 승인 판단 API와 일반 처리 API를 분리해 기본 구조를 정리합니다.",
                ]
            elif primary_template_id == "query_filter":
                backend = [
                    f"예시: {self._compose_concept_goal(concept, '조회 API와 결과 목록 API를 분리하고 조회 모델을 기준으로 기본 구조를 정리합니다.')}",
                ]
            elif primary_template_id == "amount_threshold":
                backend = [
                    f"예시: {concept} 한도 판단 API와 일반 처리 API를 분리해 기본 구조를 정리합니다.",
                ]
            else:
                backend = [
                    f"예시: {concept} 조회 API, 상세 API, 처리 API를 분리해 기본 구조를 정리합니다.",
                ]
            if primary_template_id == "workflow":
                backend.append("예시: 승인 트리거와 승인 주체를 별도 워크플로우 서비스에서 계산합니다.")
                backend.append("예시: 승인, 반려, 보류, 예외 승인 경로를 단계별 워크플로우로 분리합니다.")
            elif primary_template_id == "access_control":
                backend.append("예시: 승인 주체와 부서별 처리 권한을 정책 서비스에서 계산합니다.")
                backend.append("예시: 일반 처리 경로와 예외 승인 경로를 별도 승인 흐름으로 분리합니다.")
            elif primary_template_id == "state_transition" or primary == "status_permissions":
                backend.append("예시: 역할과 상태에 따른 처리 가능 여부를 정책 서비스에서 계산합니다.")
                backend.append("예시: 승인, 반려, 마감, 취소 같은 상태 전이 규칙을 별도 상태 전이 계층으로 분리합니다.")
            elif primary_template_id == "query_filter":
                backend.append("예시: 조회 조건 모델과 SQL 조건 매핑 규칙을 별도 조회 계층으로 분리합니다.")
                backend.append("예시: 정렬과 페이징 기본값을 조회 정책으로 분리합니다.")
            elif primary_template_id == "amount_threshold":
                backend.append("예시: 금액 구간과 한도 비교를 별도 정책 서비스에서 계산합니다.")
                backend.append("예시: 고액 처리와 한도 초과 결과를 정책 결과로 분리합니다.")
            elif primary == "search_filters":
                backend[0] = f"예시: {self._compose_concept_goal(concept, '검색 API와 상세 조회 API를 나눠 조회 구조를 정리합니다.')}"
                backend.append("예시: 조회 파라미터, 검색 조건, 정렬 규칙을 별도 조회 모델로 수집합니다.")
                backend.append("예시: SQL 조건 매핑 규칙과 조회 조건 해석을 분리합니다.")
            elif primary_template_id == "validation":
                backend.append("예시: 저장 전 차단 규칙, 중복 체크, 업무 규칙 검증을 별도 검증 계층으로 분리합니다.")
                backend.append("예시: 저장 처리 계층은 검증 완료 후 실제 저장만 담당하도록 분리합니다.")
            if secondary == "status_permissions" and primary_template_id not in {"state_transition", "access_control"} and primary != "status_permissions":
                backend.append("예시: 보조 정책 신호를 반영해 처리 가능 여부 판단 계층을 함께 둡니다.")
            elif secondary == "search_filters" and primary_template_id not in {"state_transition", "access_control", "validation", "query_filter", "amount_threshold"} and primary != "search_filters":
                backend.append("예시: 보조 조회 신호를 반영해 조회 조건 모델을 함께 둡니다.")
            elif secondary == "save_validation" and primary_template_id not in {"state_transition", "access_control", "validation", "query_filter", "amount_threshold"} and primary != "save_validation":
                backend.append("예시: 보조 저장 신호를 반영해 입력 검증 계층을 함께 둡니다.")
            if prepared.scope_limited:
                backend.insert(0, "전체 코드 생성 대신 단일 기능 endpoint 초안만 제공합니다.")
    
            if primary_template_id == "workflow":
                frontend = [
                    f"예시: {concept} 화면을 승인 요청 영역, 승인 단계 안내 영역, 예외 처리 안내 영역으로 나눕니다.",
                ]
            elif primary_template_id == "state_transition":
                frontend = [
                    f"예시: {concept} 화면을 상태 표시 영역, 처리 가능 상태 안내 영역, 전이 액션 영역으로 나눕니다.",
                ]
            elif primary_template_id == "access_control":
                frontend = [
                    f"예시: {concept} 화면을 승인 주체 안내 영역, 처리 경로 안내 영역, 액션 영역으로 나눕니다.",
                ]
            elif primary_template_id == "query_filter":
                frontend = [
                    f"예시: {self._compose_concept_goal(concept, '화면을 검색 조건 영역, 결과 목록 영역, 정렬/페이징 영역으로 나눕니다.')}",
                ]
            elif primary_template_id == "amount_threshold":
                frontend = [
                    f"예시: {concept} 화면을 한도 안내 영역, 처리 결과 안내 영역, 액션 영역으로 나눕니다.",
                ]
            else:
                frontend = [
                    f"예시: {concept} 화면을 목록 영역, 상세 영역, 처리 영역으로 나눠 화면 골격을 구성합니다.",
                ]
            if primary_template_id == "workflow":
                frontend.append("예시: 승인 주체, 단계 상태, 예외 승인 안내를 워크플로우 결과에 따라 분리해 표시합니다.")
            elif primary == "search_filters":
                frontend[0] = f"예시: {self._compose_concept_goal(concept, '화면을 검색 조건 영역과 결과 목록 영역으로 나눕니다.')}"
                frontend.append("예시: 검색 필터와 조회 조건은 별도 화면 상태로 관리합니다.")
            elif primary_template_id == "access_control":
                frontend.append("예시: 승인 주체, 부서 책임, 처리 경로 안내를 정책 결과에 따라 분리해 표시합니다.")
            elif primary_template_id == "query_filter":
                frontend.append("예시: 조회 조건과 정렬/페이징 상태를 별도 화면 상태로 관리합니다.")
            elif primary_template_id == "amount_threshold":
                frontend.append("예시: 금액 한도 안내와 한도 초과 메시지를 정책 결과에 따라 분리해 표시합니다.")
            elif primary_template_id == "state_transition" or primary == "status_permissions":
                frontend.append("예시: 액션 버튼 노출 여부는 역할과 상태 규칙에 따라 분리해 계산합니다.")
            elif primary_template_id == "validation":
                frontend.append("예시: 입력 검증, 중복 경고, 제출 차단 규칙을 화면에서 분리해 처리합니다.")
            if secondary == "search_filters" and primary_template_id not in {"state_transition", "access_control", "validation", "query_filter", "amount_threshold"} and primary != "search_filters":
                frontend.append("예시: 보조 조회 신호를 반영해 조회 조건 입력 영역을 함께 둡니다.")
            elif secondary == "status_permissions" and primary_template_id not in {"state_transition", "access_control", "query_filter", "amount_threshold"} and primary != "status_permissions":
                frontend.append("예시: 보조 정책 신호를 반영해 액션 노출 계산 영역을 함께 둡니다.")
            elif secondary == "save_validation" and primary_template_id not in {"state_transition", "access_control", "validation", "query_filter", "amount_threshold"} and primary != "save_validation":
                frontend.append("예시: 보조 저장 신호를 반영해 화면 입력 검증 로직을 함께 둡니다.")
    
            return LayeredListResult(database=database[:4], backend=backend[:4], frontend=frontend[:4])
    
    def build_risks(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
            retained_contracts: list[RetainedContract],
            applied_templates: list[AppliedJudgmentTemplate],
        ) -> list[str]:
            return self._build_template_risks(prepared, grounded_rules, retained_contracts, applied_templates)
    
    def _has_amount_threshold_focus(self, prepared: PreparedRebuildInput) -> bool:
            lowered = self._combined_evidence_text(prepared).lower()
            amount_hits = sum(
                1
                for token in (
                    "claim_amount",
                    "order_amount",
                    "amount >=",
                    "amount <=",
                    ">= 3000000",
                    ">= 5000000",
                    ">= 7000000",
                    ">= 10000000",
                    "3000000",
                    "5000000",
                    "7000000",
                    "10000000",
                    "금액",
                    "한도",
                    "threshold",
                    "limit",
                )
                if token in lowered
            )
            validation_hits = sum(
                1
                for token in ("duplicate", "exists", "blocked", "forbidden", "invalid", "delivery_hold", "중복", "차단", "선행", "save(")
                if token in lowered
            )
            access_hits = sum(
                1
                for token in ("claim_audit", "hq_reviewer", "dept_code", "reviewer", "branch_manager")
                if token in lowered
            )
            return (
                amount_hits >= 2
                and validation_hits == 0
                and access_hits == 0
                and not self._has_explicit_state_transition_signal(prepared)
                and prepared.signals.primary_feature_mode != "search_filters"
            )
    
    def _workflow_signal_text(self, prepared: PreparedRebuildInput) -> str:
            parts = [
                prepared.assets.source_code,
                prepared.assets.ui_template,
                prepared.assets.sql_queries,
                prepared.assets.database_schema,
                prepared.assets.framework_info,
                prepared.legacy_bundle,
            ]
            return "\n".join(part for part in parts if part).lower()
    
    def _workflow_actor_signal_count(self, prepared: PreparedRebuildInput) -> int:
            text = self._workflow_signal_text(prepared)
            patterns = [
                r"\bapproverrole\b",
                r"\bapprover_role\b",
                r"\bapproval_role\b",
                r"\bapprover\b",
                r"\breviewer\b",
                r"\bdelegateapprover\b",
                r"\bdelegate_approver\b",
                r"(?:approverrole|approver_role|approval_role)\s*(?:==|=|!=|equals|eq)",
                r"(?:approvalstep|approval_step|approvallevel|approval_level)[^\n]{0,80}(?:approver|reviewer|manager|finance)",
            ]
            korean_patterns = [
                "승인자",
                "결재자",
                "대리 승인자",
            ]
            count = sum(1 for pattern in patterns if re.search(pattern, text))
            count += sum(1 for token in korean_patterns if token in text)
            role_literals = {
                token
                for token in ("manager", "finance", "hr", "director", "team_lead", "auditor")
                if re.search(rf"""["']{re.escape(token)}["']""", text)
            }
            if role_literals:
                count += 1
            if len(role_literals) >= 2:
                count += 1
            return count
    
    def _workflow_stage_signal_count(self, prepared: PreparedRebuildInput) -> int:
            text = self._workflow_signal_text(prepared)
            direct_groups = [
                ("approvalstep", "approval_step", "approvallevel", "approval_level", "approvalstage", "approval_stage"),
                ("단계", "순차", "다단계", "multi-step", "multistep"),
                ("1차", "2차", "3차", "first approval", "second approval"),
                ("sequential", "parallel", "병렬"),
            ]
            count = sum(1 for tokens in direct_groups if any(token in text for token in tokens))
            if re.search(r"\bstep\b", text):
                count += 1
            if re.search(r"\bstage\b", text):
                count += 1
            if re.search(r"\blevel\b", text):
                count += 1
            if "getnextstep" in text or "nextstep" in text:
                count += 1
            if re.search(r"""["'](?:[a-z0-9]+_(?:approval|approved)[a-z0-9_]*|pending_delegate_assignment)["']""", text):
                count += 1
            return count
    
    def _workflow_gate_signal_count(self, prepared: PreparedRebuildInput) -> int:
            text = self._workflow_signal_text(prepared)
            groups = [
                ("approve(", ".approve(", "approved", "\"approved\"", "'approved'", "승인", "auto_approved", "자동 승인"),
                ("reject", "rejected", "반려"),
                ("hold", "on_hold", "보류"),
                ("delegate", "delegated", "대리 승인", "위임"),
                ("escalation", "escalate"),
            ]
            return sum(1 for tokens in groups if any(token in text for token in tokens))
    
    def _workflow_progression_signal_count(self, prepared: PreparedRebuildInput) -> int:
            text = self._workflow_signal_text(prepared)
            groups = [
                ("requested", "submitted", "request_status"),
                ("approvalstep", "approval_step", "approvallevel", "approval_level", "getnextstep", "nextstep"),
                ("delegate", "delegated", "pending_delegate_assignment"),
                ("reject", "rejected", "hold", "on_hold"),
            ]
            return sum(1 for tokens in groups if any(token in text for token in tokens))

    def _has_workflow_pattern(self, prepared: PreparedRebuildInput) -> bool:
            actor_count = self._workflow_actor_signal_count(prepared)
            stage_count = self._workflow_stage_signal_count(prepared)
            gate_count = self._workflow_gate_signal_count(prepared)
            progression_count = self._workflow_progression_signal_count(prepared)
            satisfied = sum(
                (
                    actor_count >= 1,
                    stage_count >= 1,
                    gate_count >= 1,
                )
            )
            return satisfied >= 2 and progression_count >= 1
    
    def _should_force_access_control_narrative(self, grounded_rules: list[GroundedBusinessRule]) -> bool:
            text = " ".join(f"{item.title} {item.description}" for item in grounded_rules)
            lowered = text.lower()
            matched = {
                token
                for token in ("fraud", "claim_audit", "hq_reviewer", "b99")
                if token in lowered
            }
            return len(matched) >= 2
    
    def _should_force_amount_threshold_narrative(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
        ) -> bool:
            combined = self._combined_evidence_text(prepared).lower()
            text = " ".join(
                [
                    combined,
                    " ".join(f"{item.title} {item.description}" for item in grounded_rules),
                ]
            ).lower()
            threshold_matches = re.findall(
                r"(?:order_amount|claim_amount|amount|dailylimit|limit_amount)[^0-9]{0,24}(?:>=|>|<=|<|=)\s*(\d{4,})",
                text,
                flags=re.IGNORECASE,
            )
            amount_hits = self._amount_threshold_keyword_hit_count(text)
            query_bias_hits = sum(
                1
                for token in ("request.getparameter", "@requestparam", "search", "filter", "paging", "page", "검색", "조회", "필터", "정렬", "페이징")
                if token in combined
            )
            access_hits = sum(
                1
                for token in ("claim_audit", "hq_reviewer", "dept_code", "branch_manager", "fraud", "b99")
                if token in text
            )
            return (
                len(threshold_matches) >= 2
                and amount_hits >= 3
                and query_bias_hits == 0
                and access_hits == 0
                and not self._has_explicit_state_transition_signal(prepared)
            )
    
    def build_recommended_directions(self, prepared: PreparedRebuildInput) -> list[str]:
            concept = self._primary_concept(prepared)
            narrative = self._active_narrative_judgment(prepared)
            if narrative == "workflow":
                return [
                    f"{concept} 기능의 승인 트리거와 승인 단계를 먼저 확정하는 것이 필요합니다.",
                    "승인 주체와 예외 승인 경로를 같은 워크플로우 기준으로 정리하는 것이 필요합니다.",
                    "상태 전이와 승인 결과 연결 기준을 후속 단계에서 확정하는 것이 필요합니다.",
                ]
            if narrative == "access_control":
                return [
                    f"{concept} 기능의 승인 주체와 부서별 처리 범위를 먼저 확정하는 것이 필요합니다.",
                    "예외 승인 경로와 조직별 심사 책임을 같은 권한 정책 기준으로 정리하는 것이 필요합니다.",
                    "권한 계약과 승인 경로를 유지한 상태에서 후속 구조를 정리하는 것이 필요합니다.",
                ]
            if narrative == "query_filter":
                return [
                    f"{concept} 기능의 조회 조건과 필터 조합을 먼저 확정하는 것이 필요합니다.",
                    "정렬과 페이징 기준을 같은 조회 정책으로 정리하는 것이 필요합니다.",
                    "조회 파라미터와 SQL 조건 매핑을 후속 단계에서 고정하는 것이 필요합니다.",
                ]
            if narrative == "amount_threshold":
                return [
                    f"{concept} 기능의 금액 구간과 한도 기준을 먼저 확정하는 것이 필요합니다.",
                    "승인 경계와 고액 처리 기준을 같은 금액 정책으로 정리하는 것이 필요합니다.",
                    "재계산 또는 후속 처리 기준을 후속 단계에서 고정하는 것이 필요합니다.",
                ]
            if narrative == "state_transition":
                return [
                    f"{concept} 기능의 상태 전이와 처리 가능 상태를 먼저 확정하는 것이 필요합니다.",
                    "후속 처리 흐름과 상태별 차단 조건을 같은 전이 기준으로 정리하는 것이 필요합니다.",
                    "운영 메시지와 화면 상태 표시를 후속 단계에서 고정하는 것이 필요합니다.",
                ]
            if narrative == "validation":
                return [
                    f"{concept} 기능의 차단 조건과 저장 전 검증 순서를 먼저 확정하는 것이 필요합니다.",
                    "선행 조건과 예외 처리 기준을 같은 검증 흐름으로 정리하는 것이 필요합니다.",
                    "운영 메시지와 재시도 기준을 후속 단계에서 고정하는 것이 필요합니다.",
                ]
            primary_label = self._feature_mode_label(prepared.signals.primary_feature_mode)
            directions = [
                f"{concept} 기능을 단일 현대화 범위로 고정하고 화면, 정책, 데이터 계약 기준으로 정리하는 것이 필요합니다.",
                f"숨은 업무 규칙은 {primary_label}을 우선으로 분리하고 나머지 규칙은 검증 가능한 표준 규칙으로 정리하는 것이 필요합니다.",
                "고객사 표준을 기준으로 화면, API, 정책 서비스, 데이터 계약의 분리 경계를 먼저 확정하는 것이 필요합니다.",
            ]
            if prepared.missing_context:
                directions[0] = f"{concept} 기능 범위를 유지하되 추가 자료를 먼저 보강한 뒤 상세 설계를 확정하는 것이 필요합니다."
            if prepared.scope_limited:
                directions[2] = "전체 전환 대신 단일 기능 파일럿 구조와 단계적 전환 초안을 우선 확정하는 것이 필요합니다."
            return directions[:3]
    
    def _primary_concept(self, prepared: PreparedRebuildInput) -> str:
            anchored = self._resolve_domain_anchor(prepared)
            if anchored:
                return anchored
            if prepared.accounting_input is not None:
                return "회계"
            if prepared.signals.primary_feature_mode == "search_filters":
                selected_judgment = str(
                    getattr(prepared, "selected_primary_judgment", "") or getattr(prepared, "selected_narrative_judgment", "")
                ).strip()
                if selected_judgment in {"workflow", "access_control", "state_transition"}:
                    concept_map = {
                        "order": "주문",
                        "orders": "주문",
                        "report": "보고서",
                        "reports": "보고서",
                        "request": "요청",
                        "requests": "요청",
                        "approval": "결재",
                        "approvals": "결재",
                        "claim": "청구",
                        "claims": "청구",
                        "policy": "권한",
                        "policies": "권한",
                        "user": "사용자",
                        "users": "사용자",
                    }
                    for raw in prepared.signals.concepts:
                        normalized = str(raw or "").strip().lower()
                        if normalized in {"search", "filter", "query", "validation", "submit"}:
                            continue
                        if normalized:
                            return concept_map.get(normalized, str(raw or "").strip())
                return "조회/필터"
            if self._has_amount_threshold_focus(prepared):
                return "금액/한도"
            return prepared.signals.concepts[0] if prepared.signals.concepts else "legacy"

    def _feature_mode_label(self, mode: str) -> str:
            mapping = {
                "status_permissions": "권한 및 상태 규칙",
                "search_filters": "조회 조건 규칙",
                "save_validation": "저장 검증 규칙",
                "general": "일반 기능",
            }
            return mapping.get(mode, "일반 기능")

    def _resolve_domain_anchor(self, prepared: PreparedRebuildInput) -> str | None:
            text = " ".join(
                [
                    " ".join(prepared.asset_presence.source_asset_names),
                    " ".join(prepared.asset_presence.ui_asset_names),
                    " ".join(prepared.asset_presence.schema_asset_names),
                    " ".join(prepared.asset_presence.sql_asset_names),
                    prepared.assets.source_code,
                    prepared.assets.ui_template,
                    prepared.assets.sql_queries,
                    prepared.assets.database_schema,
                ]
            ).lower()
            claim_adjust_patterns = (
                r"claim\s*[_/\-\.]?\s*adjust",
                r"adjust\s*[_/\-\.]?\s*claim",
                r"claimadjust",
                r"adjustclaim",
                r"청구.{0,10}조정",
                r"조정.{0,10}청구",
            )
            order_close_patterns = (
                r"order\s*[_/\-\.]?\s*(close|closure)",
                r"(close|closure)\s*[_/\-\.]?\s*order",
                r"orderclose",
                r"orderclosure",
                r"closeorder",
                r"closureorder",
                r"주문.{0,10}마감",
                r"마감.{0,10}주문",
            )
            if any(re.search(pattern, text) for pattern in claim_adjust_patterns) or any(
                token in text for token in ("fraud", "claim_audit", "b99")
            ):
                return "청구 조정"
            if any(re.search(pattern, text) for pattern in order_close_patterns) or any(
                token in text for token in ("vip", "agency", "deliveryhold", "review_required", "배송보류")
            ):
                return "주문 마감"
            return None
    
    def _resource_name(self, prepared: PreparedRebuildInput) -> str:
            concept = self._primary_concept(prepared)
            slug = re.sub(r"[^a-z0-9]+", "_", concept.lower()).strip("_")
            mapping = {
                "주문 마감": "order_closures",
                "청구 조정": "claim_adjustments",
                "주문": "orders",
                "결재": "approvals",
                "요청": "requests",
                "사용자": "users",
                "회원": "members",
                "상품": "products",
                "고객": "customers",
                "문서": "documents",
                "계약": "contracts",
                "환불": "refunds",
                "예약": "reservations",
                "보고서": "reports",
                "권한": "policies",
                "상태": "statuses",
            }
            return mapping.get(concept, slug or "legacy_feature")
    
    def _page_name(self, prepared: PreparedRebuildInput) -> str:
            resource = self._resource_name(prepared)
            parts = [part.capitalize() for part in resource.split("_") if part]
            base = "".join(parts) or "LegacyFeature"
            if prepared.signals.primary_feature_mode == "search_filters":
                if base.endswith("s") and len(base) > 1:
                    base = base[:-1]
                return base + "SearchPage"
            if base.endswith("s") and len(base) > 1:
                return base[:-1] + "Page"
            return base + "Page"
    
    def _filter_bar_name(self, prepared: PreparedRebuildInput) -> str:
            page = self._page_name(prepared)
            return page.replace("Page", "FilterBar")
    
    def _results_table_name(self, prepared: PreparedRebuildInput) -> str:
            page = self._page_name(prepared)
            return page.replace("Page", "ResultsTable")
    
    def _query_dto_name(self, prepared: PreparedRebuildInput) -> str:
            page = self._page_name(prepared)
            return page + "QueryDTO"
    
    def _query_mapper_name(self, prepared: PreparedRebuildInput) -> str:
            return f"{self._resource_name(prepared)}_query_mapper"
    
    def _singular_resource(self, resource: str) -> str:
            if resource.endswith("ies"):
                return resource[:-3] + "y"
            if resource.endswith("s") and len(resource) > 1:
                return resource[:-1]
            return resource
    
    def _is_validation_primary(self, prepared: PreparedRebuildInput) -> bool:
            if self._has_explicit_state_transition_signal(prepared):
                return False
            return prepared.signals.primary_feature_mode == "save_validation" or len(prepared.signals.save_validation) >= 2
    
    def _has_explicit_state_transition_signal(
            self,
            prepared: PreparedRebuildInput,
        ) -> bool:
            bundle = " ".join(
                [
                    prepared.assets.source_code,
                    prepared.assets.ui_template,
                    prepared.assets.sql_queries,
                    prepared.assets.database_schema,
                ]
            )
            lowered = bundle.lower()
            transition_patterns = (
                r"\.setstatus\s*\(",
                r"\bsetstatus\s*\(",
                r"\bset\s+status\b",
                r"\bupdate\b[\s\S]{0,80}\bset\s+status\b",
                r"상태\s*변경",
                r"상태\s*전이",
                r"전이\s*결과",
            )
            if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in transition_patterns):
                return True
            if "review_required" in lowered and any(
                token in lowered
                for token in ("setstatus", "set status", "update", "전이", "상태 변경")
            ):
                return True
            return False
    
    def _keywords_from_text(self, text: str) -> tuple[str, ...]:
            tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}|[가-힣]{2,}", text or "")
            keywords: list[str] = []
            for token in tokens:
                lowered = token.lower()
                if lowered not in keywords:
                    keywords.append(lowered)
            return tuple(keywords[:8])
    
    def _count_validation_biased_rules(self, grounded: list[GroundedBusinessRule]) -> int:
            return sum(1 for rule in grounded if self._validation_keyword_hit_count(f"{rule.title} {rule.description}") > 0)
    
    def _count_access_control_biased_rules(self, grounded: list[GroundedBusinessRule]) -> int:
            return sum(1 for rule in grounded if self._access_control_keyword_hit_count(f"{rule.title} {rule.description}") > 0)
    
    def _count_access_control_axes(self, grounded: list[GroundedBusinessRule]) -> int:
            axes = {
                axis
                for rule in grounded
                for axis in [self._access_control_rule_axis(f"{rule.title} {rule.description}")]
                if axis
            }
            return len(axes)
    
    def _validation_keyword_hit_count(self, text: str) -> int:
            lowered = (text or "").lower()
            keywords = ("amount", "한도", "duplicate", "중복", "exists", "count", "save", "저장", "차단", "선행", "invalid", "required", "blocked", "hold", "검증")
            return sum(1 for keyword in keywords if keyword in lowered)
    
    def _state_keyword_hit_count(self, text: str) -> int:
            lowered = (text or "").lower()
            keywords = ("status", "state", "closed", "cancelled", "ready", "pending", "review_required", "상태", "전이", "마감")
            return sum(1 for keyword in keywords if keyword in lowered)
    
    def _access_control_keyword_hit_count(self, text: str) -> int:
            lowered = (text or "").lower()
            keywords = (
                "role",
                "dept",
                "claim_audit",
                "hq",
                "hq_reviewer",
                "branch_manager",
                "reviewer",
                "권한",
                "부서",
                "승인",
                "본사",
                "지점",
                "전담",
            )
            return sum(1 for keyword in keywords if keyword in lowered)
    
    def _query_filter_keyword_hit_count(self, text: str) -> int:
            lowered = (text or "").lower()
            keywords = ("search", "filter", "query", "where", "order by", "sort", "paging", "page", "조회", "검색", "필터", "정렬", "페이징", "목록")
            return sum(1 for keyword in keywords if keyword in lowered)
    
    def _amount_threshold_keyword_hit_count(self, text: str) -> int:
            lowered = (text or "").lower()
            keywords = ("amount", "threshold", "limit", "order_amount", "claim_amount", "금액", "한도", "고액", "5000000", "7000000", "10000000", "본사 승인", "검토")
            return sum(1 for keyword in keywords if keyword in lowered)
    
    def _access_control_rule_axis(self, text: str) -> str:
            lowered = (text or "").lower()
            if any(token in lowered for token in ("10000000", "1천만원", "3000000", "300만원", "고액", "한도", "claim_amount")):
                return "amount"
            if any(token in lowered for token in ("승인 주체", "hq_reviewer", "branch_manager", "reviewer", "본사", "지점", "부서", "권한")):
                return "approver"
            if any(token in lowered for token in ("경로", "route", "path", "선승인", "예외 승인", "urgent", "처리 경로")):
                return "route"
            return ""
    
    def _access_control_candidate_rule_specs(
            self,
            prepared: PreparedRebuildInput,
            core_rules: list[str],
        ) -> list[dict[str, object]]:
            combined = self._combined_evidence_text(prepared).lower()
            specs: list[dict[str, object]] = []
            if "10000000" in combined or "1천만원" in combined:
                specs.append(
                    {
                        "title": "금액 기준 권한 제한",
                        "description": "고액 처리 조건은 전담 부서 또는 지정 권한으로만 처리해야 합니다.",
                        "keywords": ("10000000", "1천만원", "claim_audit", "dept_code", "hq", "전담"),
                        "design_targets": ("정책 서비스", "권한 모델", "API"),
                    }
                )
            if any(token in combined for token in ("hq_reviewer", "user_role", "branch_manager", "reviewer", "본사", "지점", "승인 주체", "부서별")):
                specs.append(
                    {
                        "title": "승인 주체 분리",
                        "description": "처리 권한이 있는 부서와 일반 처리 주체를 분리해야 합니다.",
                        "keywords": ("hq_reviewer", "user_role", "branch_manager", "reviewer", "본사", "지점", "승인 주체"),
                        "design_targets": ("정책 서비스", "권한 모델", "예외 승인 흐름"),
                    }
                )
            if any(token in combined for token in ("urgent", "선승인", "예외 승인", "경로", "route", "path", "hq_reviewer", "branch_manager", "본사")):
                specs.append(
                    {
                        "title": "처리 경로 분기",
                        "description": "조건에 따라 일반 처리와 예외 승인 경로를 분리해야 합니다.",
                        "keywords": ("urgent", "선승인", "예외 승인", "경로", "route", "path", "hq_reviewer", "branch_manager", "본사"),
                        "design_targets": ("예외 승인 흐름", "정책 서비스", "API"),
                    }
                )
            if not specs:
                for rule in core_rules:
                    lowered = rule.lower()
                    if any(token in lowered for token in ("권한", "부서", "승인", "claim_audit", "hq")):
                        specs.append(
                            {
                                "title": "승인 주체 분리",
                                "description": rule,
                                "keywords": self._keywords_from_text(rule),
                                "design_targets": ("정책 서비스", "권한 모델", "API"),
                            }
                        )
            return specs
    
    def _should_enrich_access_control(
            self,
            prepared: PreparedRebuildInput,
            grounded: list[GroundedBusinessRule],
            *,
            applied_templates: list[AppliedJudgmentTemplate] | None = None,
        ) -> bool:
            if applied_templates is not None:
                primary = self._primary_template(prepared, applied_templates)
                if primary and primary.template_id == "access_control":
                    return True
            if self._should_force_amount_threshold_narrative(prepared, grounded):
                return False
            if self._is_access_control_primary(prepared, grounded):
                return True
            if self._has_explicit_state_transition_signal(prepared) or self._is_validation_primary(prepared):
                return False
            if "access_control" not in self._candidate_template_ids(prepared, grounded):
                return False
            return prepared.signals.primary_feature_mode == "status_permissions" or self._count_access_control_biased_rules(grounded) >= 1

    def _is_access_control_primary(
            self,
            prepared: PreparedRebuildInput,
            grounded: list[GroundedBusinessRule],
        ) -> bool:
            if self._has_explicit_state_transition_signal(prepared) or self._is_validation_primary(prepared):
                return False
            if prepared.signals.primary_feature_mode == "status_permissions" and self._count_access_control_axes(grounded) >= 2:
                return True
            return self._count_access_control_axes(grounded) >= 2 and self._count_access_control_biased_rules(grounded) >= 2

    def _has_claim_access_control_focus(
            self,
            prepared: PreparedRebuildInput,
            grounded: list[GroundedBusinessRule],
        ) -> bool:
            if self._primary_concept(prepared) != "청구 조정":
                return False
            combined = " ".join(
                [
                    self._combined_evidence_text(prepared),
                    " ".join(f"{item.title} {item.description}" for item in grounded),
                ]
            ).lower()
            actor_hits = sum(
                1
                for token in ("branch_manager", "hq_reviewer", "claim_audit", "reviewer", "manager", "본사", "지점장", "심사", "부서", "권한")
                if token in combined
            )
            route_hits = sum(
                1
                for token in ("b99", "fraud", "선승인", "예외 승인", "긴급", "심사전담", "처리 경로")
                if token in combined
            )
            amount_actor_hits = sum(
                1
                for token in ("3000000", "300만원", "10000000", "1천만원")
                if token in combined
            )
            return actor_hits >= 2 and (route_hits >= 1 or amount_actor_hits >= 1)
    
    def _accumulate_signal_template_scores(
            self,
            prepared: PreparedRebuildInput,
            scores: dict[str, float],
            signal_hits: dict[str, set[str]],
        ) -> None:
            status_score = float(prepared.signals.scores.get("status_permissions", 0.0))
            search_score = float(prepared.signals.scores.get("search_filters", 0.0))
            validation_score = float(prepared.signals.scores.get("save_validation", 0.0))
            if status_score:
                scores["state_transition"] += min(3.2, status_score * 0.58)
                scores["access_control"] += min(3.0, status_score * 0.52)
                signal_hits["state_transition"].add("status_permissions")
                signal_hits["access_control"].add("status_permissions")
                if self._has_workflow_pattern(prepared):
                    scores["workflow"] += min(3.4, status_score * 0.62)
                    signal_hits["workflow"].add("status_permissions")
            if search_score:
                scores["query_filter"] += min(3.2, search_score * 0.78)
                signal_hits["query_filter"].add("search_filters")
            if validation_score:
                scores["validation"] += min(3.2, validation_score * 0.72)
                signal_hits["validation"].add("save_validation")
            if self._has_amount_threshold_focus(prepared):
                scores["amount_threshold"] += max(1.8, min(3.0, validation_score * 0.68))
                signal_hits["amount_threshold"].add("amount_threshold")
            signal_text = " ".join(
                prepared.signals.status_permissions
                + prepared.signals.search_filters
                + prepared.signals.save_validation
                + prepared.signals.technical
                + prepared.signals.concepts
            )
            for template_id, label in self._template_keyword_hits(signal_text):
                scores[template_id] += 0.7
                signal_hits[template_id].add(label)
    
    def _accumulate_rule_template_scores(
            self,
            grounded_rules: list[GroundedBusinessRule],
            scores: dict[str, float],
            signal_hits: dict[str, set[str]],
            rule_hits: dict[str, list[str]],
        ) -> None:
            for rule in grounded_rules:
                text = f"{rule.title} {rule.description}"
                for template_id, label in self._template_keyword_hits(text):
                    scores[template_id] += 1.35
                    signal_hits[template_id].add(label)
                    rule_hits[template_id].append(rule.title)
                for target in rule.design_targets:
                    mapped = self._template_ids_for_design_target(target)
                    for template_id in mapped:
                        scores[template_id] += 0.9
                        signal_hits[template_id].add(target)
                        rule_hits[template_id].append(rule.title)
                if rule.confidence == "확정":
                    for template_id in self._template_ids_for_rule(rule):
                        scores[template_id] += 0.35
    
    def _accumulate_contract_template_scores(
            self,
            retained_contracts: list[RetainedContract],
            scores: dict[str, float],
            signal_hits: dict[str, set[str]],
            contract_hits: dict[str, list[str]],
        ) -> None:
            for contract in retained_contracts:
                text = f"{contract.item} {contract.basis}"
                for template_id, label in self._template_keyword_hits(text):
                    scores[template_id] += 1.1
                    signal_hits[template_id].add(label)
                    contract_hits[template_id].append(contract.item)
    
    def _template_keyword_hits(self, text: str) -> list[tuple[JudgmentTemplateId, str]]:
            lowered = (text or "").lower()
            matches: list[tuple[JudgmentTemplateId, str]] = []
            keyword_map: dict[JudgmentTemplateId, tuple[str, ...]] = {
                "workflow": ("approval", "approver", "approverrole", "reviewer", "approvalstep", "approvallevel", "reject", "hold", "delegate", "escalation", "승인", "반려", "보류", "대리 승인"),
                "state_transition": ("status", "state", "ready", "review_required", "closed", "cancelled", "전이", "상태", "마감"),
                "access_control": ("role", "dept", "org", "hq", "권한", "본사", "부서", "승인", "reviewer", "claim_audit", "agency", "지점장"),
                "validation": ("amount", "limit", "flag", "hold", "검증", "차단", "한도", "선행", "delivery_hold", "불가", "urgent", "fraud"),
                "query_filter": ("search", "filter", "query", "where", "order by", "sort", "paging", "page", "검색", "조회", "필터", "정렬", "페이징"),
                "amount_threshold": ("amount", "threshold", "limit", "claim_amount", "order_amount", "고액", "금액", "한도", "3000000", "5000000", "7000000", "10000000"),
            }
            for template_id, keywords in keyword_map.items():
                for keyword in keywords:
                    if keyword in lowered:
                        matches.append((template_id, keyword))
                        break
            return matches
    
    def _workflow_keyword_hit_count(self, text: str) -> int:
            lowered = (text or "").lower()
            keywords = (
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
            return sum(1 for keyword in keywords if keyword in lowered)
    
    def _template_ids_for_design_target(self, target: str) -> list[JudgmentTemplateId]:
            lowered = (target or "").lower()
            matched: list[JudgmentTemplateId] = []
            if any(token in lowered for token in ("상태 전이", "status", "transition")):
                matched.append("state_transition")
            if any(token in lowered for token in ("승인 단계", "approval", "approver", "reject", "반려", "보류", "workflow", "대리 승인")):
                matched.append("workflow")
            if any(token in lowered for token in ("권한", "policy", "예외 승인", "승인", "권한 모델")):
                matched.append("access_control")
            if any(token in lowered for token in ("검증", "validation", "선행", "save", "차단")):
                matched.append("validation")
            if any(token in lowered for token in ("조회", "검색", "필터", "query", "sort", "paging", "정렬")):
                matched.append("query_filter")
            if any(token in lowered for token in ("금액", "한도", "amount", "threshold", "limit")):
                matched.append("amount_threshold")
            return matched
    
    def _template_ids_for_rule(self, rule: GroundedBusinessRule) -> list[JudgmentTemplateId]:
            matched = [template_id for template_id, _ in self._template_keyword_hits(f"{rule.title} {rule.description}")]
            return list(dict.fromkeys(matched))
    
    def _fallback_verification_template(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
        ) -> JudgmentTemplateId | None:
            if self._has_workflow_pattern(prepared):
                return "workflow"
            if self._has_explicit_state_transition_signal(prepared):
                return "state_transition"
            if self._should_force_amount_threshold_narrative(prepared, grounded_rules):
                return "amount_threshold"
            if self._is_validation_primary(prepared):
                return "validation"
            if self._count_access_control_biased_rules(grounded_rules) >= 1:
                return "access_control"
            if self._is_access_control_primary(prepared, grounded_rules):
                return "access_control"
            candidate_ids = self._candidate_template_ids(prepared, grounded_rules)
            return candidate_ids[0] if candidate_ids else None
    
    def _build_recommended_selection_reason(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
            retained_contracts: list[RetainedContract],
            recommended: DesignOption,
            applied_templates: list[AppliedJudgmentTemplate],
        ) -> str:
            ordered_templates = self._ordered_templates_for_generation(prepared, applied_templates, grounded_rules)
            primary_template = ordered_templates[0] if ordered_templates else self._primary_template(prepared, applied_templates)
            narrative_templates = [primary_template] if primary_template else ordered_templates or applied_templates
            rule_phrases = self._selection_rule_phrases(narrative_templates, grounded_rules)
            contract_phrases = self._selection_contract_phrases(retained_contracts, narrative_templates)
            axis_phrase = self._selection_axis_phrase(narrative_templates)
            option_phrase = self._selection_option_preference_phrase(narrative_templates, recommended.name)
    
            lines = []
            if rule_phrases:
                joined_rules = ", ".join(rule_phrases[:2])
                lines.append(f"이 샘플에서는 {joined_rules} 규칙이 직접 확인되었습니다.")
            lines.append(
                f"따라서 {self._attach_object_particle(self._option_label(recommended.name))} 우선안으로 두고 {axis_phrase}를 먼저 고정해야 합니다."
            )
            if contract_phrases:
                lines.append(f"이 안은 {', '.join(contract_phrases[:2])} 계약을 유지하면서도 분리 범위를 통제하기 쉽습니다.")
            lines.append(option_phrase)
            return " ".join(lines)
    
    def _selection_rule_phrases(self, applied_templates: list[AppliedJudgmentTemplate], grounded_rules: list[GroundedBusinessRule]) -> list[str]:
            priorities = self._selection_priority_keywords(applied_templates)
            primary_id = applied_templates[0].template_id if applied_templates else ""
            ordered: list[str] = []
            for keyword in priorities:
                for rule in grounded_rules:
                    text = f"{rule.title} {rule.description}"
                    if keyword.lower() in text.lower():
                        phrase = self._selection_rule_phrase(rule)
                        if primary_id == "access_control" and phrase == "금액 한도 제한":
                            phrase = "고액 승인 제한"
                        if phrase not in ordered:
                            ordered.append(phrase)
            for rule in grounded_rules:
                phrase = self._selection_rule_phrase(rule)
                if primary_id == "access_control" and phrase == "금액 한도 제한":
                    phrase = "고액 승인 제한"
                if phrase not in ordered:
                    ordered.append(phrase)
            return ordered[:3]
    
    def _selection_rule_phrase(self, rule: GroundedBusinessRule) -> str:
            description = (rule.description or "").strip().rstrip(".")
            lowered = f"{rule.title} {description}".lower()
            if any(token in lowered for token in ("승인 주체", "hq_reviewer", "branch_manager", "reviewer", "본사 승인")):
                return "승인 주체 분리"
            if any(token in lowered for token in ("approvalstep", "approval_level", "승인 단계", "다단계", "1차", "2차", "순차 승인")):
                return "승인 단계 구조"
            if any(token in lowered for token in ("approve", "reject", "hold", "반려", "보류", "자동 승인")):
                return "의사결정 게이트"
            if any(token in lowered for token in ("delegate", "대리 승인", "긴급", "예외 승인", "escalation")):
                return "예외 승인 흐름"
            if any(token in lowered for token in ("처리 경로", "예외 승인", "선승인", "경로 분기", "route")):
                return "처리 경로 분기"
            if any(token in lowered for token in ("3000000", "10000000", "1천만원", "300만원", "한도")):
                return "금액 한도 제한"
            if any(token in lowered for token in ("claim_audit", "hq_reviewer", "권한", "승인")):
                return "승인 권한 제한"
            if any(token in lowered for token in ("검색", "조회", "필터", "query", "sort", "paging", "정렬")):
                return "조회 조건 분리"
            if any(token in lowered for token in ("amount", "금액", "고액", "threshold", "limit")):
                return "금액 한도 정책"
            if any(token in lowered for token in ("closed", "cancelled", "조정 불가", "상태")):
                return "상태 제한"
            return description or (rule.title or "").strip()
    
    def _selection_contract_phrases(
            self,
            retained_contracts: list[RetainedContract],
            applied_templates: list[AppliedJudgmentTemplate],
        ) -> list[str]:
            primary = applied_templates[0].template_id if applied_templates else ""
            preferred_keywords = {
                "validation": ("중복", "차단", "검증 순서", "선행 조건", "한도"),
                "workflow": ("승인", "approver", "approval", "단계", "delegate", "반려", "보류"),
                "access_control": ("claim_audit", "승인", "권한", "dept_code", "channel_code"),
                "state_transition": ("status", "review_required", "delivery_hold", "상태값"),
                "query_filter": ("조회", "검색", "필터", "정렬", "페이징", "query"),
                "amount_threshold": ("금액", "한도", "amount", "limit", "threshold"),
            }.get(primary, ())
            phrases: list[str] = []
            prioritized = []
            fallback = []
            for item in retained_contracts:
                text = (item.item or "").strip()
                text = text.replace("은 유지하는 것이 필요합니다.", "").replace("는 유지하는 것이 필요합니다.", "")
                text = text.replace(" 계약", "").strip()
                text = self._normalize_contract_display(text)
                if not text:
                    continue
                if preferred_keywords and any(keyword.lower() in text.lower() for keyword in preferred_keywords):
                    prioritized.append(text)
                else:
                    fallback.append(text)
            if primary == "access_control":
                return prioritized[:2]
            if primary in {"query_filter", "amount_threshold"}:
                return prioritized[:2] or fallback[:2]
            for text in prioritized + fallback:
                if text and text not in phrases:
                    phrases.append(text)
            return phrases[:3]
    
    def _normalize_contract_display(self, text: str) -> str:
            normalized = (text or "").strip()
            normalized = re.sub(r"^\.", "", normalized)
            normalized = re.sub(r"\b[A-Z_0-9]+\.status\b", "status 컬럼", normalized)
            normalized = re.sub(r"\b[a-zA-Z_][a-zA-Z0-9_]*\.status\b", "status 컬럼", normalized)
            normalized = re.sub(r"\.status\b", "status 컬럼", normalized)
            normalized = re.sub(r"\bstatus 값\(", "status 컬럼의 상태값(", normalized)
            normalized = re.sub(r"\bstatus 컬럼 컬럼\b", "status 컬럼", normalized)
            normalized = re.sub(r"\bstatus 컬럼 컬럼의 상태값\b", "status 컬럼의 상태값", normalized)
            normalized = re.sub(r"\b값 값\b", "값", normalized)
            normalized = re.sub(r"\b계약 계약\b", "계약", normalized)
            normalized = re.sub(r"\s{2,}", " ", normalized)
            return normalized.strip()
    
    def _primary_template_axis_phrase(self, primary_template: AppliedJudgmentTemplate | None) -> str:
            if not primary_template:
                return ""
            if primary_template.template_id == "workflow":
                return "승인 트리거와 승인 단계"
            if primary_template.template_id == "state_transition":
                return "상태 전이"
            if primary_template.template_id == "access_control":
                return "승인 권한과 승인 주체"
            if primary_template.template_id == "validation":
                return "차단 조건과 검증 순서"
            if primary_template.template_id == "query_filter":
                return "조회 조건과 필터 규칙"
            if primary_template.template_id == "amount_threshold":
                return "금액 구간과 한도 규칙"
            return ""
    
    def _selection_axis_phrase(self, applied_templates: list[AppliedJudgmentTemplate]) -> str:
            primary_template = applied_templates[0] if applied_templates else None
            if primary_template:
                if primary_template.template_id == "workflow":
                    return "승인 트리거, 승인 주체, 승인 단계 구조를 중심으로 통제할 수 있는 구조"
                if primary_template.template_id == "state_transition":
                    return "상태 전이와 처리 가능 상태를 중심으로 통제할 수 있는 구조"
                if primary_template.template_id == "access_control":
                    return "권한, 부서, 승인 주체를 중심으로 통제할 수 있는 구조"
                if primary_template.template_id == "validation":
                    return "차단 조건과 검증 순서를 중심으로 통제할 수 있는 구조"
                if primary_template.template_id == "query_filter":
                    return "조회 조건, 필터 조합, 결과 목록을 중심으로 통제할 수 있는 구조"
                if primary_template.template_id == "amount_threshold":
                    return "금액 구간과 한도 정책을 중심으로 통제할 수 있는 구조"
            axis_phrases = []
            for item in applied_templates[:2]:
                if item.template_id == "state_transition":
                    axis_phrases.append("상태 전이와 처리 가능 상태")
                elif item.template_id == "workflow":
                    axis_phrases.append("승인 트리거와 승인 단계 구조")
                elif item.template_id == "access_control":
                    axis_phrases.append("승인 권한과 승인 주체")
                elif item.template_id == "validation":
                    axis_phrases.append("차단 조건과 검증 순서")
                elif item.template_id == "query_filter":
                    axis_phrases.append("조회 조건과 필터 규칙")
                elif item.template_id == "amount_threshold":
                    axis_phrases.append("금액 구간과 한도 규칙")
            if not axis_phrases:
                return "핵심 규칙과 데이터 계약을 함께 통제할 수 있는 구조"
            return f"{', '.join(axis_phrases)}를 함께 통제할 수 있는 구조"
    
    def _selection_option_preference_phrase(self, applied_templates: list[AppliedJudgmentTemplate], option_name: str) -> str:
            ids = [item.template_id for item in applied_templates[:2]]
            option_label = self._option_label(option_name)
            if ids[:2] == ["state_transition", "access_control"]:
                return f"상태 전이와 권한 규칙을 하나의 정책 계층에서 함께 다뤄야 하므로 {self._attach_object_particle(option_label)} 우선 적용해야 합니다."
            if ids and ids[0] == "workflow":
                return f"승인 트리거, 승인 주체, 단계별 의사결정 게이트를 같은 워크플로우 계층으로 묶어야 하므로 {self._attach_object_particle(option_label)} 우선 적용해야 합니다."
            if ids[:2] in (["validation", "access_control"], ["access_control", "validation"]):
                return f"금액 한도와 승인 권한을 함께 분리해야 하므로 {self._attach_object_particle(option_label)} 우선 적용해야 합니다."
            if ids and ids[0] == "access_control":
                return f"승인 주체, 부서 책임, 처리 경로를 같은 권한 정책으로 묶어야 하므로 {self._attach_object_particle(option_label)} 우선 적용해야 합니다."
            if ids and ids[0] == "validation":
                return f"선행 차단 조건과 저장 전 검증 순서를 함께 정리해야 하므로 {self._attach_object_particle(option_label)} 우선 적용해야 합니다."
            if ids and ids[0] == "query_filter":
                return f"조회 조건, 정렬, 페이징 규칙을 같은 조회 모델로 묶어야 하므로 {self._attach_object_particle(option_label)} 우선 적용해야 합니다."
            if ids and ids[0] == "amount_threshold":
                return f"금액 구간과 한도 정책을 같은 정책 계층으로 묶어야 하므로 {self._attach_object_particle(option_label)} 우선 적용해야 합니다."
            return f"핵심 규칙과 유지 계약을 함께 반영해야 하므로 {self._attach_object_particle(option_label)} 우선 적용해야 합니다."
    
    def _build_non_recommended_selection_reason(self, option_name: str, applied_templates: list[AppliedJudgmentTemplate]) -> str:
            label = self._option_label(option_name)
            ids = [item.template_id for item in applied_templates[:2]]
            if "화면" in option_name:
                return f"{label}는 화면 개선 효과는 빠르지만 핵심 규칙 분리를 뒤로 미루므로 후순위로 둬야 합니다."
            if ids[:2] == ["state_transition", "access_control"]:
                return f"{label}는 승인 경로 분리에는 장점이 있지만 상태 전이와 권한 규칙을 동시에 묶는 현재 우선순위보다 뒤에 두어야 합니다."
            if ids and ids[0] == "workflow":
                return f"{label}는 일부 승인 흐름에는 유효하지만 이번 승인 구조 중심 워크플로우보다 뒤에 두어야 합니다."
            if ids[:2] in (["validation", "access_control"], ["access_control", "validation"]):
                return f"{label}는 일부 예외 승인 규칙 정리에는 도움이 되지만 금액 한도와 승인 권한을 함께 분리하는 현재 우선순위보다 뒤에 두어야 합니다."
            if ids and ids[0] == "query_filter":
                return f"{label}는 일부 조회 흐름에는 유효하지만 이번 조회/필터 중심 구조보다 뒤에 두어야 합니다."
            if ids and ids[0] == "amount_threshold":
                return f"{label}는 일부 한도 정책에는 유효하지만 이번 금액/한도 중심 구조보다 뒤에 두어야 합니다."
            return f"{label}는 보조 구조로는 활용할 수 있지만 핵심 규칙과 유지 계약을 동시에 반영하는 현재 우선순위보다 뒤에 두어야 합니다."
    
    def _option_label(self, option_name: str) -> str:
            text = (option_name or "").strip()
            return re.sub(r"^옵션\s+[A-Z]\.\s*", "", text).strip() or text
    
    def _attach_object_particle(self, text: str) -> str:
            value = (text or "").strip()
            if not value:
                return value
            last = value[-1]
            code = ord(last)
            if 0xAC00 <= code <= 0xD7A3:
                has_batchim = (code - 0xAC00) % 28 != 0
                return value + ("을" if has_batchim else "를")
            return value + "를"
    
    def _pick_linked_rule_titles(self, titles: list[str], keywords: tuple[str, ...]) -> list[str]:
            picked: list[str] = []
            lowered_titles = [(title, title.lower()) for title in titles]
            for keyword in keywords:
                needle = keyword.lower()
                for original, lowered in lowered_titles:
                    if needle in lowered and original not in picked:
                        picked.append(original)
                        break
            if not picked:
                picked = titles[:2]
            return picked[:3]
    
    def _pick_linked_contracts(self, contracts: list[str], keywords: tuple[str, ...]) -> list[str]:
            picked: list[str] = []
            lowered_contracts = [(item, item.lower()) for item in contracts]
            for keyword in keywords:
                needle = keyword.lower()
                for original, lowered in lowered_contracts:
                    if needle in lowered and original not in picked:
                        picked.append(original)
                        break
            if not picked:
                picked = contracts[:1]
            return picked[:2]
    
    def _build_template_decision_items(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
            applied_templates: list[AppliedJudgmentTemplate],
            *,
            decision_count_hint: int | None = None,
        ) -> list[DecisionItem]:
            concept = self._primary_concept(prepared)
            evidence_index = {rule.title: rule.evidence for rule in grounded_rules}
            items: list[DecisionItem] = []
            primary = self._primary_template(prepared, applied_templates)
            if primary and primary.template_id == "query_filter" and decision_count_hint == 0:
                return []
            for template in applied_templates[:2]:
                lead_rule = template.matched_rule_titles[0] if template.matched_rule_titles else (grounded_rules[0].title if grounded_rules else "")
                if template.template_id == "workflow":
                    items.append(
                        DecisionItem(
                            statement=f"{concept} 기능의 승인 트리거와 승인 주체 규칙을 별도 워크플로우 계층으로 분리하는 것이 필요합니다.",
                            rationale=f"{lead_rule or '직접 확인된 승인 흐름 규칙'}을 처리 로직에서 분리해야 승인 경로와 예외 흐름을 일관되게 유지할 수 있습니다.",
                            linked_evidence=evidence_index.get(lead_rule, []),
                        )
                    )
                elif template.template_id == "state_transition":
                    items.append(
                        DecisionItem(
                            statement=f"{concept} 기능의 상태 전이 규칙을 별도 정책 계층으로 분리하는 것이 필요합니다.",
                            rationale=f"{lead_rule or '직접 확인된 상태 전이 규칙'}을 현재 화면과 저장 흐름에서 분리해야 예외 전이 누락을 줄일 수 있습니다.",
                            linked_evidence=evidence_index.get(lead_rule, []),
                        )
                    )
                elif template.template_id == "access_control":
                    items.append(
                        DecisionItem(
                            statement=f"{concept} 기능의 권한과 승인 주체 규칙을 별도 정책 서비스로 분리하는 것이 필요합니다.",
                            rationale=f"{lead_rule or '직접 확인된 승인 규칙'}을 처리 흐름과 분리해야 승인 경로를 일관되게 유지할 수 있습니다.",
                            linked_evidence=evidence_index.get(lead_rule, []),
                        )
                    )
                elif template.template_id == "validation":
                    items.append(
                        DecisionItem(
                            statement=f"{concept} 기능의 핵심 검증 규칙을 저장 흐름과 분리하는 것이 필요합니다.",
                            rationale=f"{lead_rule or '직접 확인된 차단 조건'}을 선행 검증으로 고정해야 처리 가능 범위를 안정적으로 통제할 수 있습니다.",
                            linked_evidence=evidence_index.get(lead_rule, []),
                        )
                    )
                elif template.template_id == "query_filter":
                    items.append(
                        DecisionItem(
                            statement=f"{concept} 기능의 조회 조건과 필터 조합 규칙을 별도 조회 모델로 분리하는 것이 필요합니다.",
                            rationale=f"{lead_rule or '직접 확인된 조회 조건 규칙'}을 화면과 SQL 조건 매핑에서 분리해야 조회 결과 일관성을 유지할 수 있습니다.",
                            linked_evidence=evidence_index.get(lead_rule, []),
                        )
                    )
                elif template.template_id == "amount_threshold":
                    items.append(
                        DecisionItem(
                            statement=f"{concept} 기능의 금액 구간과 한도 정책을 별도 정책 계층으로 분리하는 것이 필요합니다.",
                            rationale=f"{lead_rule or '직접 확인된 금액 한도 규칙'}을 처리 흐름과 분리해야 구간별 기준을 일관되게 유지할 수 있습니다.",
                            linked_evidence=evidence_index.get(lead_rule, []),
                        )
                    )
            if primary and primary.template_id == "validation":
                validation_defaults = [
                    (
                        f"{concept} 기능의 차단 조건을 별도 검증 계층으로 고정하는 것이 필요합니다.",
                        "직접 확인된 차단 조건을 저장 흐름 밖으로 분리해야 예외 누락을 줄일 수 있습니다.",
                    ),
                    (
                        f"{concept} 기능의 검증 순서를 API 진입 전 단계에서 명시하는 것이 필요합니다.",
                        "검증 순서를 고정해야 저장 전 차단과 후속 처리 조건이 흔들리지 않습니다.",
                    ),
                    (
                        f"{concept} 기능의 중복 방지 규칙을 저장 처리와 분리하는 것이 필요합니다.",
                        "중복 처리 차단 규칙을 별도 검증으로 고정해야 동일 대상 재처리를 막을 수 있습니다.",
                    ),
                ]
                for statement, rationale in validation_defaults:
                    if len(items) >= 3:
                        break
                    if any(item.statement == statement for item in items):
                        continue
                    items.append(
                        DecisionItem(
                            statement=statement,
                            rationale=rationale,
                            linked_evidence=[evidence for rule in grounded_rules[:2] for evidence in rule.evidence][:2],
                        )
                    )
            if primary and primary.template_id == "workflow":
                workflow_defaults = [
                    (
                        f"{concept} 기능의 승인 단계 구조와 의사결정 게이트를 워크플로우 계층으로 고정하는 것이 필요합니다.",
                        "단계별 승인, 반려, 보류 게이트를 분리해야 승인 순서와 처리 결과가 흔들리지 않습니다.",
                    ),
                    (
                        f"{concept} 기능의 승인 주체와 승인 권한 경계를 같은 워크플로우 정책으로 정리하는 것이 필요합니다.",
                        "승인 주체와 승인 권한 경계를 함께 고정해야 승인 누락과 권한 오남용을 줄일 수 있습니다.",
                    ),
                    (
                        f"{concept} 기능의 예외 승인 경로와 일반 승인 경로를 분리하는 것이 필요합니다.",
                        "대리 승인, 긴급 승인, 자동 승인 경로를 분리해야 운영 예외를 통제할 수 있습니다.",
                    ),
                ]
                for statement, rationale in workflow_defaults:
                    if len(items) >= 3:
                        break
                    if any(item.statement == statement for item in items):
                        continue
                    items.append(
                        DecisionItem(
                            statement=statement,
                            rationale=rationale,
                            linked_evidence=[evidence for rule in grounded_rules[:3] for evidence in rule.evidence][:2],
                        )
                    )
            if primary and primary.template_id == "state_transition":
                state_defaults = [
                    (
                        f"{concept} 기능의 처리 가능 상태와 전이 조건을 같은 정책 계층으로 고정하는 것이 필요합니다.",
                        "처리 가능 상태와 전이 조건을 분리된 정책 기준으로 고정해야 예외 전이 누락을 줄일 수 있습니다.",
                    ),
                    (
                        f"{concept} 기능의 전이 결과와 상태 표시 기준을 같은 상태 정책으로 정리하는 것이 필요합니다.",
                        "전이 결과와 화면 상태 표시를 같은 정책 기준으로 맞춰야 후속 처리 흐름이 흔들리지 않습니다.",
                    ),
                    (
                        f"{concept} 기능의 전이 차단 조건을 상태 정책과 함께 관리하는 것이 필요합니다.",
                        "전이 차단 조건을 상태 정책과 함께 관리해야 처리 가능 범위와 후속 전이 경계가 어긋나지 않습니다.",
                    ),
                ]
                for statement, rationale in state_defaults:
                    if len(items) >= 3:
                        break
                    if any(item.statement == statement for item in items):
                        continue
                    items.append(
                        DecisionItem(
                            statement=statement,
                            rationale=rationale,
                            linked_evidence=[evidence for rule in grounded_rules[:2] for evidence in rule.evidence][:2],
                        )
                    )
            if primary and primary.template_id == "access_control":
                access_defaults = [
                    (
                        f"{concept} 기능의 승인 주체와 부서 책임을 별도 정책 서비스로 고정하는 것이 필요합니다.",
                        "승인 주체와 부서 책임을 처리 흐름에서 분리해야 승인 경로를 일관되게 유지할 수 있습니다.",
                    ),
                    (
                        f"{concept} 기능의 고액 승인 조건과 부서별 처리 권한을 같은 권한 정책으로 정리하는 것이 필요합니다.",
                        "금액 기준 권한 제한과 부서별 승인 주체를 하나의 정책 기준으로 묶어야 예외 처리를 줄일 수 있습니다.",
                    ),
                    (
                        f"{concept} 기능의 예외 승인 경로를 일반 처리 경로와 분리하는 것이 필요합니다.",
                        "예외 승인 경로를 별도로 고정해야 부서 간 처리 책임이 섞이지 않습니다.",
                    ),
                ]
                for statement, rationale in access_defaults:
                    if len(items) >= 3:
                        break
                    if any(item.statement == statement for item in items):
                        continue
                    items.append(
                        DecisionItem(
                            statement=statement,
                            rationale=rationale,
                            linked_evidence=[evidence for rule in grounded_rules[:3] for evidence in rule.evidence][:2],
                        )
                    )
            if primary and primary.template_id == "query_filter":
                query_defaults = [
                    (
                        f"{concept} 기능의 조회 조건과 필터 상태를 별도 조회 모델로 고정하는 것이 필요합니다.",
                        "직접 확인된 조회 조건과 필터 조합을 분리해야 화면과 SQL 조건 매핑이 흔들리지 않습니다.",
                    ),
                    (
                        f"{concept} 기능의 정렬과 페이징 기본 규칙을 조회 정책으로 분리하는 것이 필요합니다.",
                        "정렬과 페이징을 조회 정책으로 고정해야 동일 조건의 결과 일관성을 유지할 수 있습니다.",
                    ),
                    (
                        f"{concept} 기능의 결과 목록 구성 규칙을 조회 API와 함께 고정하는 것이 필요합니다.",
                        "조회 조건과 결과 목록 구성을 함께 고정해야 필터 조합 누락을 줄일 수 있습니다.",
                    ),
                ]
                for statement, rationale in query_defaults:
                    if len(items) >= 3:
                        break
                    if any(item.statement == statement for item in items):
                        continue
                    items.append(
                        DecisionItem(
                            statement=statement,
                            rationale=rationale,
                            linked_evidence=[evidence for rule in grounded_rules[:2] for evidence in rule.evidence][:2],
                        )
                    )
            if primary and primary.template_id == "amount_threshold":
                amount_defaults = [
                    (
                        f"{concept} 기능의 금액 구간과 한도 규칙을 별도 정책 계층으로 고정하는 것이 필요합니다.",
                        "직접 확인된 금액 구간과 한도 조건을 분리해야 고액 처리 기준이 흔들리지 않습니다.",
                    ),
                    (
                        f"{concept} 기능의 한도 초과 처리 경계를 별도 정책 결과로 정리하는 것이 필요합니다.",
                        "구간별 후속 처리 경계를 고정해야 고액 조건의 예외 누락을 줄일 수 있습니다.",
                    ),
                    (
                        f"{concept} 기능의 금액 기준 메시지와 처리 결과를 같은 한도 정책으로 맞추는 것이 필요합니다.",
                        "금액 기준 결과를 같은 정책에서 계산해야 화면과 처리 흐름이 어긋나지 않습니다.",
                    ),
                ]
                for statement, rationale in amount_defaults:
                    if len(items) >= 3:
                        break
                    if any(item.statement == statement for item in items):
                        continue
                    items.append(
                        DecisionItem(
                            statement=statement,
                            rationale=rationale,
                            linked_evidence=[evidence for rule in grounded_rules[:2] for evidence in rule.evidence][:2],
                        )
                    )
            while len(items) < 3:
                items.append(
                    DecisionItem(
                        statement=f"{concept} 기능의 핵심 규칙과 유지 계약을 같은 실행 계획 안에서 고정하는 것이 필요합니다.",
                        rationale="핵심 규칙과 데이터 계약을 함께 정리해야 분리 순서가 흔들리지 않습니다.",
                        linked_evidence=[evidence for rule in grounded_rules[:1] for evidence in rule.evidence][:2],
                    )
                )
            deduped: list[DecisionItem] = []
            seen_statements: set[str] = set()
            for item in items:
                key = self._normalize_key(item.statement)
                if not key or key in seen_statements:
                    continue
                seen_statements.add(key)
                deduped.append(item)
            while len(deduped) < 3:
                fallback = DecisionItem(
                    statement=f"{concept} 기능의 핵심 규칙과 유지 계약을 같은 실행 계획 안에서 고정하는 것이 필요합니다.",
                    rationale="핵심 규칙과 데이터 계약을 함께 정리해야 분리 순서가 흔들리지 않습니다.",
                    linked_evidence=[evidence for rule in grounded_rules[:1] for evidence in rule.evidence][:2],
                )
                key = self._normalize_key(fallback.statement)
                if key in seen_statements:
                    break
                seen_statements.add(key)
                deduped.append(fallback)
            return deduped[:3]
    
    def _build_template_priority_split_items(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
            retained_contracts: list[RetainedContract],
            applied_templates: list[AppliedJudgmentTemplate],
        ) -> list[PrioritySplitItem]:
            concept = self._primary_concept(prepared)
            templates = applied_templates[:2]
            primary = self._primary_template(prepared, applied_templates)
            items: list[PrioritySplitItem] = []
            for index, template in enumerate(templates, start=1):
                spec = get_judgment_template_spec(template.template_id)
                default = spec.priority_split_defaults[0 if index == 1 else min(1, len(spec.priority_split_defaults) - 1)]
                items.append(
                    PrioritySplitItem(
                        priority=index,
                        item=f"{concept} 기능에서 {default['item']}",
                        title=f"{concept} {default['title']}",
                        reason=self._priority_reason(default["reason"], template, grounded_rules),
                        impact_scope=default["impact_scope"],
                        prerequisite=self._priority_prerequisite(default["prerequisite"], template, retained_contracts),
                        linked_rules=template.matched_rule_titles[:3] or [rule.title for rule in grounded_rules[:2]],
                        linked_contracts=template.matched_contract_items[:2] or [item.item for item in retained_contracts[:1]],
                    )
                )
            if primary and primary.template_id == "validation":
                existing_priorities = {item.priority for item in items}
                linked_rules = primary.matched_rule_titles[:3] or [rule.title for rule in grounded_rules[:3]]
                linked_contracts = primary.matched_contract_items[:2] or [item.item for item in retained_contracts[:2]]
                defaults = [
                    (
                        1,
                        f"{concept} 기능에서 핵심 차단 조건과 중복 방지 규칙을 먼저 분리하는 것이 필요합니다.",
                        f"{concept} 핵심 검증 규칙 분리",
                        "직접 확인된 차단 조건과 중복 처리 차단 규칙을 먼저 고정해야 저장 오류와 재처리를 줄일 수 있습니다.",
                        "차단 조건, 중복 방지, 선행 확인 흐름",
                        "검증 계약 확정",
                    ),
                    (
                        2,
                        f"{concept} 기능에서 검증 흐름과 검증 순서를 다음 단계로 정리하는 것이 필요합니다.",
                        f"{concept} 검증 순서 정리",
                        "저장 전 검증 순서를 명시적으로 고정해야 차단 메시지와 처리 순서 충돌을 줄일 수 있습니다.",
                        "검증 순서, 저장 전 차단, 예외 메시지 처리",
                        "핵심 검증 규칙 목록 정리",
                    ),
                ]
                for priority, item_text, title, reason, impact_scope, prerequisite in defaults:
                    if priority in existing_priorities:
                        continue
                    items.append(
                        PrioritySplitItem(
                            priority=priority,
                            item=item_text,
                            title=title,
                            reason=reason,
                            impact_scope=impact_scope,
                            prerequisite=prerequisite,
                            linked_rules=linked_rules,
                            linked_contracts=linked_contracts,
                        )
                    )
            if primary and primary.template_id == "state_transition":
                existing_priorities = {item.priority for item in items}
                linked_rules = primary.matched_rule_titles[:3] or [rule.title for rule in grounded_rules[:3]]
                linked_contracts = primary.matched_contract_items[:2] or [item.item for item in retained_contracts[:2]]
                defaults = [
                    (
                        2,
                        f"{concept} 기능에서 처리 가능 상태와 전이 조건을 다음 단계로 정리하는 것이 필요합니다.",
                        f"{concept} 전이 조건 정리",
                        "처리 가능 상태와 전이 조건을 명시적으로 고정해야 예외 전이와 화면 액션 노출이 흔들리지 않습니다.",
                        "처리 가능 상태, 전이 조건, 전이 결과 반영",
                        "핵심 상태 정책 목록 정리",
                    ),
                ]
                for priority, item_text, title, reason, impact_scope, prerequisite in defaults:
                    if priority in existing_priorities:
                        continue
                    items.append(
                        PrioritySplitItem(
                            priority=priority,
                            item=item_text,
                            title=title,
                            reason=reason,
                            impact_scope=impact_scope,
                            prerequisite=prerequisite,
                            linked_rules=linked_rules,
                            linked_contracts=linked_contracts,
                        )
                    )
            if primary and primary.template_id == "access_control":
                existing_priorities = {item.priority for item in items}
                linked_rules = primary.matched_rule_titles[:3] or [rule.title for rule in grounded_rules[:3]]
                linked_contracts = primary.matched_contract_items[:2] or [item.item for item in retained_contracts[:2]]
                defaults = [
                    (
                        2,
                        f"{concept} 기능에서 승인 주체와 부서별 처리 경계를 다음 단계로 정리하는 것이 필요합니다.",
                        f"{concept} 승인 주체 분리",
                        "승인 주체와 부서 책임을 명확히 고정해야 고액 처리와 예외 승인 경로가 섞이지 않습니다.",
                        "승인 주체 매핑, 부서별 처리 권한, 예외 승인 기준",
                        "핵심 권한 정책 목록 정리",
                    ),
                    (
                        3,
                        f"{concept} 기능의 처리 경로 안내와 승인 액션 노출을 마지막에 재구성하는 것이 필요합니다.",
                        f"{concept} 승인 경로 재구성",
                        "권한 정책과 승인 경로가 정리된 뒤 화면과 처리 경로 안내를 맞춰야 재작업을 줄일 수 있습니다.",
                        "승인 버튼 노출, 처리 경로 안내, 사용자 메시지",
                        "정책 API 계약 고정",
                    ),
                ]
                for priority, item_text, title, reason, impact_scope, prerequisite in defaults:
                    if priority in existing_priorities:
                        continue
                    items.append(
                        PrioritySplitItem(
                            priority=priority,
                            item=item_text,
                            title=title,
                            reason=reason,
                            impact_scope=impact_scope,
                            prerequisite=prerequisite,
                            linked_rules=linked_rules,
                            linked_contracts=linked_contracts,
                        )
                    )
            if primary and primary.template_id == "query_filter":
                existing_priorities = {item.priority for item in items}
                linked_rules = primary.matched_rule_titles[:3] or [rule.title for rule in grounded_rules[:3]]
                linked_contracts = primary.matched_contract_items[:2] or [item.item for item in retained_contracts[:2]]
                defaults = [
                    (
                        2,
                        f"{concept} 기능에서 정렬과 페이징 기본 규칙을 다음 단계로 정리하는 것이 필요합니다.",
                        f"{concept} 정렬 및 페이징 규칙 정리",
                        "정렬과 페이징 기준을 별도로 고정해야 같은 조회 요청의 결과 일관성을 유지할 수 있습니다.",
                        "정렬 규칙, 페이징 기본값, 결과 목록 정합성",
                        "조회 조건 모델 확정",
                    ),
                ]
                for priority, item_text, title, reason, impact_scope, prerequisite in defaults:
                    if priority in existing_priorities:
                        continue
                    items.append(
                        PrioritySplitItem(
                            priority=priority,
                            item=item_text,
                            title=title,
                            reason=reason,
                            impact_scope=impact_scope,
                            prerequisite=prerequisite,
                            linked_rules=linked_rules,
                            linked_contracts=linked_contracts,
                        )
                    )
            if primary and primary.template_id == "amount_threshold":
                existing_priorities = {item.priority for item in items}
                linked_rules = primary.matched_rule_titles[:3] or [rule.title for rule in grounded_rules[:3]]
                linked_contracts = primary.matched_contract_items[:2] or [item.item for item in retained_contracts[:2]]
                defaults = [
                    (
                        2,
                        f"{concept} 기능에서 금액 구간별 처리 경계와 후속 흐름을 다음 단계로 정리하는 것이 필요합니다.",
                        f"{concept} 한도 적용 흐름 정리",
                        "금액 구간별 후속 처리 경계를 고정해야 한도 정책 누락을 줄일 수 있습니다.",
                        "고액 처리, 한도 초과, 예외 메시지 기준",
                        "금액 한도 정책 확정",
                    ),
                ]
                for priority, item_text, title, reason, impact_scope, prerequisite in defaults:
                    if priority in existing_priorities:
                        continue
                    items.append(
                        PrioritySplitItem(
                            priority=priority,
                            item=item_text,
                            title=title,
                            reason=reason,
                            impact_scope=impact_scope,
                            prerequisite=prerequisite,
                            linked_rules=linked_rules,
                            linked_contracts=linked_contracts,
                        )
                    )
            ui_focus = "화면 액션 노출과 상태 표시" if any(item.template_id == "state_transition" for item in templates) else "화면 액션 노출과 입력 검증"
            if primary and primary.template_id == "workflow":
                ui_focus = "승인 단계 안내와 예외 처리 안내"
            elif primary and primary.template_id == "access_control":
                ui_focus = "화면 액션 노출과 승인 경로 안내"
            elif primary and primary.template_id == "query_filter":
                ui_focus = "조회 조건 입력과 결과 목록 정합성"
            elif primary and primary.template_id == "amount_threshold":
                ui_focus = "한도 안내와 처리 결과 메시지"
            items.append(
                PrioritySplitItem(
                    priority=3,
                    item=f"{concept} 기능의 {self._with_object_particle(ui_focus)} 마지막에 재구성하는 것이 필요합니다.",
                    title=f"{concept} 화면 재구성",
                    reason=(
                        "핵심 승인 정책과 단계 구조가 정리된 뒤 화면을 맞춰야 재작업을 줄일 수 있습니다."
                        if primary and primary.template_id == "workflow"
                        else "핵심 정책과 승인 경로가 정리된 뒤 화면을 맞춰야 재작업을 줄일 수 있습니다."
                        if primary and primary.template_id == "access_control"
                        else "핵심 상태 정책과 전이 규칙이 정리된 뒤 화면을 맞춰야 재작업을 줄일 수 있습니다."
                        if primary and primary.template_id == "state_transition"
                        else "핵심 조회 정책이 정리된 뒤 화면을 맞춰야 재작업을 줄일 수 있습니다."
                        if primary and primary.template_id == "query_filter"
                        else "핵심 금액 정책과 한도 경계가 정리된 뒤 화면을 맞춰야 재작업을 줄일 수 있습니다."
                        if primary and primary.template_id == "amount_threshold"
                        else "핵심 조회/한도 정책이 정리된 뒤 화면을 맞춰야 재작업을 줄일 수 있습니다."
                    ),
                    impact_scope="화면 액션 노출, 상태 표시, 사용자 안내 메시지",
                    prerequisite=(
                        "워크플로우 API 계약 고정"
                        if primary and primary.template_id == "workflow"
                        else "정책 API 계약 고정"
                        if primary and primary.template_id == "access_control"
                        else "상태 정책 API 계약 고정"
                        if primary and primary.template_id == "state_transition"
                        else "조회 API 계약 고정"
                        if primary and primary.template_id == "query_filter"
                        else "금액 정책 API 계약 고정"
                        if primary and primary.template_id == "amount_threshold"
                        else "조회/정책 API 계약 고정"
                    ),
                    linked_rules=[rule.title for rule in grounded_rules[:2]],
                    linked_contracts=[item.item for item in retained_contracts[:1]],
                )
            )
            items = sorted({item.priority: item for item in items}.values(), key=lambda item: item.priority)
            return items[:3]
    
    def _build_template_design_options(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
            retained_contracts: list[RetainedContract],
            applied_templates: list[AppliedJudgmentTemplate],
        ) -> list[DesignOption]:
            labels = [item.template_id for item in applied_templates[:2]]
            primary = labels[0] if labels else "validation"
            secondary = labels[1] if len(labels) > 1 else None
            if primary == "validation":
                return [
                    DesignOption(name="옵션 A. 검증 규칙 중심 모듈형 구조", structure_summary="차단 조건, 저장 전 검증, 예외 처리 순서를 검증 계층으로 분리하고 처리 흐름은 검증 결과만 반영하도록 구성합니다.", advantages=["차단 조건과 저장 전 검증 순서를 우선 고정해야 합니다.", "기존 검증 기준 컬럼과 차단 계약을 유지한 상태에서 분리 순서를 통제해야 합니다."], risks=["권한 규칙이나 상태 표시가 보조 축으로 남으면 후속 단계 조정이 필요할 수 있습니다."], difficulty="MEDIUM", duration_weeks=4, recommended=True, selection_reason=""),
                    DesignOption(name="옵션 B. 검증 우선 분리 구조", structure_summary="저장 전 차단 규칙을 먼저 분리하고 API와 서비스는 검증 결과를 소비하는 구조로 정리합니다.", advantages=["단기적으로 저장 오류와 예외 누락을 줄일 수 있습니다."], risks=["정책 규칙이 후속 단계로 밀리면 일부 액션 노출 조정이 남을 수 있습니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                    DesignOption(name="옵션 C. 화면 우선 재구성 구조", structure_summary="화면을 먼저 재구성하고 검증 규칙 분리는 후속 단계로 넘깁니다.", advantages=["화면 개선 효과를 빠르게 보여줄 수 있습니다."], risks=["핵심 차단 조건과 저장 전 검증이 레거시에 남아 재작업 가능성이 큽니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                ]
            if primary == "query_filter":
                return [
                    DesignOption(name="옵션 A. 조회 모델 중심 모듈형 구조", structure_summary="조회 조건, 필터 상태, 정렬, 페이징을 별도 조회 모델로 분리하고 API는 조회 모델만 받아 결과 목록을 반환하도록 구성합니다.", advantages=["조회 조건과 SQL 조건 매핑을 한곳에서 통제해야 합니다.", "정렬과 페이징 기본값을 같은 조회 정책으로 유지해야 합니다."], risks=["조회 규칙 정의가 약하면 필터 조합이 다시 화면과 SQL에 분산될 수 있습니다."], difficulty="MEDIUM", duration_weeks=4, recommended=True, selection_reason=""),
                    DesignOption(name="옵션 B. 필터 상태 분리형 구조", structure_summary="화면 필터 상태를 먼저 분리하고 정렬과 결과 목록 구성은 후속 조회 정책으로 정리합니다.", advantages=["화면 필터 상태를 빠르게 정리할 수 있습니다."], risks=["SQL 조건 매핑 규칙이 뒤로 밀리면 조회 결과 일관성이 흔들릴 수 있습니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                    DesignOption(name="옵션 C. 결과 목록 우선 구조", structure_summary="결과 목록 구성과 정렬 기준을 먼저 정리하고 필터 입력 모델 분리는 후속 단계로 넘깁니다.", advantages=["결과 목록 UX 개선을 빠르게 보여줄 수 있습니다."], risks=["필터 조합 규칙이 레거시에 남아 재작업 가능성이 큽니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                ]
            if primary == "workflow":
                return [
                    DesignOption(name="옵션 A. 승인 흐름 중심 모듈형 구조", structure_summary="승인 트리거, 승인 주체, 단계별 의사결정 게이트를 별도 워크플로우 계층으로 분리하고 API는 승인 결과만 반영하도록 구성합니다.", advantages=["승인 트리거와 승인 주체를 같은 워크플로우 기준으로 유지해야 합니다.", "단계별 승인 순서와 예외 승인 흐름을 함께 고정해야 합니다."], risks=["승인 단계와 예외 승인 경계가 흐리면 승인 누락이 다시 발생할 수 있습니다."], difficulty="MEDIUM", duration_weeks=5, recommended=True, selection_reason=""),
                    DesignOption(name="옵션 B. 단계 분리형 승인 구조", structure_summary="단일 승인과 다단계 승인을 별도 단계 모듈로 나누고 승인 주체 정책은 각 단계에서 공통으로 적용합니다.", advantages=["다단계 승인 구조를 독립적으로 추적하기 쉽습니다."], risks=["단계 간 상태 전달 규칙이 늘어나면 관리 비용이 커질 수 있습니다."], difficulty="MEDIUM", duration_weeks=6, recommended=False, selection_reason=""),
                    DesignOption(name="옵션 C. 예외 승인 분리형 구조", structure_summary="일반 승인 흐름과 대리 승인, 긴급 승인, 자동 승인 경로를 분리하고 승인 주체는 공통 정책으로 적용합니다.", advantages=["예외 흐름을 별도로 통제하기 쉽습니다."], risks=["예외 승인 경로가 늘어나면 일반 승인 흐름과의 정합성 비용이 커질 수 있습니다."], difficulty="HIGH", duration_weeks=6, recommended=False, selection_reason=""),
                ]
            if primary == "amount_threshold":
                return [
                    DesignOption(name="옵션 A. 금액 한도 정책 중심 모듈형 구조", structure_summary="금액 구간, 한도 임계값, 한도 초과 후속 처리 규칙을 별도 정책 계층으로 분리하고 API는 정책 결과만 반영하도록 구성합니다.", advantages=["금액 한도와 임계값을 한 정책 기준으로 유지해야 합니다.", "고액 처리 경계를 같은 규칙 표로 관리해야 합니다."], risks=["승인 또는 보조 처리 규칙과 경계가 흐리면 한도 정책이 다시 분산될 수 있습니다."], difficulty="MEDIUM", duration_weeks=4, recommended=True, selection_reason=""),
                    DesignOption(name="옵션 B. 한도 기준 우선 구조", structure_summary="한도 초과 차단과 임계값 비교를 먼저 분리하고 후속 처리 흐름은 다음 단계에서 정리합니다.", advantages=["한도 초과 기준을 빠르게 고정할 수 있습니다."], risks=["고액 처리 후속 흐름이 뒤로 밀리면 사용자 메시지와 처리 결과가 어긋날 수 있습니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                    DesignOption(name="옵션 C. 처리 결과 우선 구조", structure_summary="한도 초과 결과와 메시지를 먼저 정리하고 한도 정책 분리는 후속 단계로 넘깁니다.", advantages=["사용자 안내를 빠르게 정리할 수 있습니다."], risks=["핵심 한도 규칙이 레거시에 남아 재작업 가능성이 큽니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                ]
            if primary == "access_control":
                return [
                    DesignOption(name="옵션 A. 권한 정책 중심 모듈형 구조", structure_summary="승인 주체, 부서별 처리 권한, 처리 경로를 정책 계층으로 분리하고 API는 승인 결과와 처리 가능 여부만 반영하도록 구성합니다.", advantages=["승인 권한과 부서 책임을 한 정책 기준으로 고정해야 합니다.", "처리 경로와 승인 주체를 함께 분리해야 운영 혼선을 줄일 수 있습니다."], risks=["예외 승인 경로 정의가 약하면 부서 책임이 다시 섞일 수 있습니다."], difficulty="MEDIUM", duration_weeks=4, recommended=True, selection_reason=""),
                    DesignOption(name="옵션 B. 승인 주체 분리형 구조", structure_summary="일반 처리와 승인 주체 결정을 별도 권한 모듈로 나누고, 부서별 정책은 그 위에서 공통으로 적용합니다.", advantages=["승인 주체를 독립적으로 추적하기 쉽습니다."], risks=["부서 정책과 승인 주체 정책이 분리되면 경계 조정 비용이 생길 수 있습니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                    DesignOption(name="옵션 C. 처리 경로 분리형 구조", structure_summary="예외 승인과 일반 처리 경로를 분리하고 권한 정책은 각 경로에서 공통으로 적용합니다.", advantages=["예외 승인 경로를 별도로 통제하기 쉽습니다."], risks=["처리 경로가 늘어나면 정책 적용 지점이 중복될 수 있습니다."], difficulty="HIGH", duration_weeks=6, recommended=False, selection_reason=""),
                ]
            if primary == "state_transition" and secondary == "access_control":
                return [
                    DesignOption(name="옵션 A. 정책·상태 전이 중심 모듈형 구조", structure_summary="상태 전이와 승인 주체 규칙을 같은 정책 계층에서 평가하고 API는 결과 상태만 반영하도록 분리합니다.", advantages=["상태 전이와 권한 규칙을 한 정책 계층에서 관리해야 합니다.", "기존 상태 코드와 승인 조건 계약을 함께 유지해야 합니다."], risks=["정책 계층 경계가 약하면 상태 전이와 권한 판단이 다시 분산될 수 있습니다."], difficulty="MEDIUM", duration_weeks=4, recommended=True, selection_reason=""),
                    DesignOption(name="옵션 B. 승인 경로 분리형 구조", structure_summary="예외 승인 경로를 별도 승인 모듈로 분리하고 기본 처리 흐름은 결과 상태만 반영하도록 구성합니다.", advantages=["승인 경로를 별도로 추적할 수 있습니다."], risks=["상태 전이와 승인 결과 반영이 나뉘어 정합성 비용이 커질 수 있습니다."], difficulty="HIGH", duration_weeks=6, recommended=False, selection_reason=""),
                    DesignOption(name="옵션 C. 화면 우선 재구성 구조", structure_summary="화면을 먼저 재구성하고 정책 분리는 후속 단계로 넘깁니다.", advantages=["화면 개선 효과를 빠르게 보여줄 수 있습니다."], risks=["핵심 상태 전이와 권한 규칙이 레거시에 남아 재작업 가능성이 큽니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                ]
            if primary == "state_transition":
                return [
                    DesignOption(name="옵션 A. 상태 전이 중심 모듈형 구조", structure_summary="핵심 상태 전이와 처리 가능 상태 규칙을 정책 계층으로 분리하고 화면은 정책 결과만 반영하도록 구성합니다.", advantages=["상태 전이와 처리 가능 상태를 우선 고정해야 합니다.", "기존 상태 코드 계약을 유지한 상태에서 분리 순서를 통제해야 합니다."], risks=["권한 규칙이 뒤로 밀리면 예외 승인 경계가 다시 분산될 수 있습니다."], difficulty="MEDIUM", duration_weeks=4, recommended=True, selection_reason=""),
                    DesignOption(name="옵션 B. 상태 검증 우선 구조", structure_summary="상태 기반 차단과 선행 검증을 먼저 정리하고 권한 정책은 후속 단계에서 정리합니다.", advantages=["처리 가능 상태와 차단 조건을 빠르게 고정할 수 있습니다."], risks=["권한 규칙이 후속 단계로 밀리면 승인 경로 정합성이 약해질 수 있습니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                    DesignOption(name="옵션 C. 화면 우선 재구성 구조", structure_summary="화면을 먼저 재구성하고 상태 전이 정책 분리는 후속 단계로 넘깁니다.", advantages=["화면 개선 효과를 빠르게 보여줄 수 있습니다."], risks=["핵심 상태 전이 규칙이 그대로 남아 재작업 가능성이 큽니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                ]
            if primary in {"validation", "access_control"} and secondary in {"validation", "access_control"}:
                return [
                    DesignOption(name="옵션 A. 한도·권한 정책 중심 모듈형 구조", structure_summary="금액 한도, 승인 주체, 예외 승인 규칙을 정책 계층으로 분리하고 저장 전 검증은 별도 검증 흐름으로 정리합니다.", advantages=["금액 한도와 승인 권한을 함께 분리해야 합니다.", "기존 컬럼 계약과 승인 상태 체계를 함께 유지해야 합니다."], risks=["정책 계층과 검증 계층의 경계가 흐리면 규칙이 다시 섞일 수 있습니다."], difficulty="MEDIUM", duration_weeks=4, recommended=True, selection_reason=""),
                    DesignOption(name="옵션 B. 예외 승인 워크플로우 분리형 구조", structure_summary="예외 승인 규칙을 별도 워크플로우로 분리하고 일반 처리 흐름은 기본 검증에 집중시킵니다.", advantages=["예외 승인 경로를 독립적으로 관리하기 쉽습니다."], risks=["기본 검증과 예외 승인 흐름이 이중화될 수 있습니다."], difficulty="HIGH", duration_weeks=6, recommended=False, selection_reason=""),
                    DesignOption(name="옵션 C. 검증 우선 분리 구조", structure_summary="차단 조건과 저장 전 검증을 먼저 분리하고 권한 정책은 후속 단계에서 정교화합니다.", advantages=["단기적으로 저장 오류를 줄일 수 있습니다."], risks=["핵심 승인 정책 분리가 뒤로 밀릴 수 있습니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                ]
            if primary in {"amount_threshold", "access_control"} and secondary in {"amount_threshold", "access_control"}:
                return [
                    DesignOption(name="옵션 A. 한도·권한 정책 중심 모듈형 구조", structure_summary="금액 한도, 부서별 승인 권한, 예외 승인 경계를 같은 정책 계층으로 분리하고 처리 흐름은 정책 결과만 반영하도록 구성합니다.", advantages=["금액 한도와 권한 조건을 같은 정책 기준으로 유지해야 합니다.", "고액 처리와 승인 주체 경계를 함께 고정할 수 있습니다."], risks=["한도 정책과 승인 정책 경계가 흐리면 책임이 다시 섞일 수 있습니다."], difficulty="MEDIUM", duration_weeks=4, recommended=True, selection_reason=""),
                    DesignOption(name="옵션 B. 승인 경로 분리형 구조", structure_summary="고액 승인 경로를 별도 승인 흐름으로 분리하고 금액 한도는 각 경로에서 공통 정책으로 적용합니다.", advantages=["고액 승인 경로를 독립적으로 추적하기 쉽습니다."], risks=["승인 경로가 늘어나면 한도 정책 적용 지점이 중복될 수 있습니다."], difficulty="HIGH", duration_weeks=6, recommended=False, selection_reason=""),
                    DesignOption(name="옵션 C. 한도 검증 우선 구조", structure_summary="금액 한도 비교를 먼저 분리하고 승인 정책은 후속 단계에서 정교화합니다.", advantages=["한도 기준을 빠르게 고정할 수 있습니다."], risks=["승인 주체 분리가 뒤로 밀릴 수 있습니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
                ]
            return [
                DesignOption(name="옵션 A. 정책 중심 모듈형 구조", structure_summary=f"{self._primary_concept(prepared)} 기능 안에서 API, 정책 서비스, 데이터 계약을 모듈형으로 분리합니다.", advantages=["핵심 규칙을 우선 분리해야 합니다.", "기존 계약을 유지한 상태에서 분리 범위를 통제해야 합니다."], risks=["정책 수가 많으면 서비스 경계가 커질 수 있습니다."], difficulty="MEDIUM", duration_weeks=4, recommended=True, selection_reason=""),
                DesignOption(name="옵션 B. 조회/저장 이원화 구조", structure_summary=f"{self._primary_concept(prepared)} 기능을 조회 흐름과 저장 흐름으로 분리하고 정책은 저장 측에 집중합니다.", advantages=["조회 성능과 저장 검증을 분리하기 쉽습니다."], risks=["핵심 정책이 조회에도 필요하면 판단 로직이 중복될 수 있습니다."], difficulty="MEDIUM", duration_weeks=5, recommended=False, selection_reason=""),
            ]
    
    def _build_template_execution_plan(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
            retained_contracts: list[RetainedContract],
            recommended_option: RecommendedOption | None,
            applied_templates: list[AppliedJudgmentTemplate],
        ) -> list[ExecutionPlanWeek]:
            concept = self._primary_concept(prepared)
            option_name = self._option_label(recommended_option.name) if recommended_option else "정책 중심 모듈형 구조"
            templates = self._ordered_templates_for_generation(prepared, applied_templates, grounded_rules)[:2]
            top = templates[0] if templates else None
            second = templates[1] if len(templates) > 1 else None
            if top and top.template_id in {"query_filter", "amount_threshold"}:
                templates = [top]
                second = None
            top_rules = top.matched_rule_titles[:3] if top else [rule.title for rule in grounded_rules[:3]]
            top_contracts = top.matched_contract_items[:2] if top else [item.item for item in retained_contracts[:2]]
            second_rules = second.matched_rule_titles[:3] if second else [rule.title for rule in grounded_rules[1:3]]
            second_contracts = second.matched_contract_items[:2] if second else [item.item for item in retained_contracts[:1]]
            if top and top.template_id == "query_filter":
                return [
                    ExecutionPlanWeek(
                        week_label="1주차",
                        goal="조회 조건, 필터 조합, 정렬 기준을 구조화합니다.",
                        tasks=[
                            "조회 조건과 필터 조합을 조회 모델 기준으로 정리합니다.",
                            "정렬 기준과 기본 페이징 값을 조회 정책 목록으로 고정합니다.",
                            "직접 확인된 조회 계약을 유지 목록으로 확정합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["컨설턴트", "업무 분석가", "백엔드 아키텍트"],
                        duration_weeks=1,
                        deliverables=["조회 조건 목록", "필터 조합 표", "정렬/페이징 기본값 표"],
                    ),
                    ExecutionPlanWeek(
                        week_label="2주차",
                        goal=f"{option_name} 기준으로 조회 모델과 SQL 조건 매핑 구조를 설계합니다.",
                        tasks=[
                            "조회 파라미터와 SQL 조건 매핑 규칙을 조회 계층 책임으로 정의합니다.",
                            "필터 상태와 결과 목록 구성을 같은 조회 모델 기준으로 고정합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["백엔드 아키텍트", "시니어 개발자"],
                        duration_weeks=1,
                        deliverables=["조회 모델 설계안", "SQL 조건 매핑 규칙", "결과 목록 구성 명세"],
                    ),
                    ExecutionPlanWeek(
                        week_label="3주차",
                        goal=f"{concept} API와 조회 모델에 핵심 조회 규칙을 반영합니다.",
                        tasks=[
                            "조회 조건, 정렬, 페이징 규칙을 조회 API와 SQL 매핑에 반영합니다.",
                            f"{self._append_suffix_without_dup(grounded_rules[0].title if grounded_rules else '조회 조건 분리', '규칙')}을 회귀 테스트 케이스로 고정합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["백엔드 개발자", "QA"],
                        duration_weeks=1,
                        deliverables=["API 반영 목록", "조회 모델 테스트 케이스", "조회 규칙 구현 체크리스트"],
                    ),
                    ExecutionPlanWeek(
                        week_label="4주차",
                        goal=f"{concept} 화면과 결과 목록 정합성을 규칙 기준으로 검증합니다.",
                        tasks=[
                            "필터 입력, 정렬, 페이징 UI를 조회 모델과 맞춰 정렬합니다.",
                            "유지 계약이 화면과 API 결과에서 깨지지 않는지 회귀 검증합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["프론트엔드 개발자", "백엔드 개발자", "QA"],
                        duration_weeks=1,
                        deliverables=["화면 정합성 체크리스트", "회귀 검증 결과", "파일럿 적용안"],
                    ),
                ]
            if top and top.template_id == "workflow":
                return [
                    ExecutionPlanWeek(
                        week_label="1주차",
                        goal="승인 트리거와 승인 주체 규칙을 구조화합니다.",
                        tasks=[
                            "승인 시작 조건과 승인 요청 트리거를 워크플로우 규칙 표로 정리합니다.",
                            "승인 주체와 승인 권한 관계를 승인 주체 매트릭스로 고정합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["컨설턴트", "업무 분석가", "백엔드 아키텍트"],
                        duration_weeks=1,
                        deliverables=["승인 트리거 목록", "승인 주체 매트릭스", "승인 권한 계약 목록"],
                    ),
                    ExecutionPlanWeek(
                        week_label="2주차",
                        goal=f"{option_name} 기준으로 승인 단계 구조와 의사결정 게이트를 설계합니다.",
                        tasks=[
                            "단계별 승인 순서와 조건부 승인 분기를 워크플로우 단계 구조로 정의합니다.",
                            "승인, 반려, 보류 게이트를 단계별 워크플로우 결과로 분리합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["백엔드 아키텍트", "시니어 개발자"],
                        duration_weeks=1,
                        deliverables=["승인 단계 흐름도", "의사결정 게이트 명세", "단계별 승인 구조안"],
                    ),
                    ExecutionPlanWeek(
                        week_label="3주차",
                        goal=f"{concept} 승인 API와 워크플로우 서비스에 승인 규칙을 반영합니다.",
                        tasks=[
                            "승인 주체 규칙과 단계별 승인 순서를 워크플로우 서비스 호출로 반영합니다.",
                            "대리 승인, 긴급 승인, 자동 승인 경로를 예외 워크플로우 결과로 분리합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["백엔드 개발자", "QA"],
                        duration_weeks=1,
                        deliverables=["승인 API 반영 목록", "워크플로우 테스트 케이스", "예외 승인 구현 체크리스트"],
                    ),
                    ExecutionPlanWeek(
                        week_label="4주차",
                        goal=f"{concept} 승인 화면과 승인 단계 안내를 워크플로우 기준으로 정렬합니다.",
                        tasks=[
                            "승인 단계 안내와 승인 주체 메시지를 워크플로우 결과와 맞춰 정렬합니다.",
                            "승인 버튼 노출과 예외 승인 안내가 유지 계약과 일치하는지 확인합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["프론트엔드 개발자", "백엔드 개발자", "QA"],
                        duration_weeks=1,
                        deliverables=["승인 화면 체크리스트", "승인 단계 안내 시안", "정합성 확인 결과"],
                    ),
                    ExecutionPlanWeek(
                        week_label="5주차",
                        goal=f"{concept} 상태 전이와 승인 흐름 통합 기준을 확정합니다.",
                        tasks=[
                            "승인 완료, 반려, 보류 결과가 상태 전이와 어떻게 연결되는지 통합 규칙으로 고정합니다.",
                            "워크플로우 결과와 상태 전이 결과가 충돌하지 않는지 통합 시나리오로 확인합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["백엔드 아키텍트", "QA"],
                        duration_weeks=1,
                        deliverables=["승인-상태 통합 규칙서", "통합 시나리오 목록", "파일럿 적용안"],
                    ),
                ]
            if top and top.template_id == "amount_threshold":
                return [
                    ExecutionPlanWeek(
                        week_label="1주차",
                        goal="금액 구간과 한도 계산 기준을 구조화합니다.",
                        tasks=[
                            "금액 구간 기준과 구간별 경계를 정책 규칙 표로 정리합니다.",
                            "한도 계산 기준과 한도 적용 필드를 계약 목록으로 고정합니다.",
                            "직접 확인된 금액 정책 계약을 유지 목록으로 확정합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["컨설턴트", "업무 분석가", "백엔드 아키텍트"],
                        duration_weeks=1,
                        deliverables=["금액 구간 표", "한도 계산 기준표", "금액 정책 계약 목록"],
                    ),
                    ExecutionPlanWeek(
                        week_label="2주차",
                        goal=f"{option_name} 기준으로 금액 정책과 한도 적용 구조를 설계합니다.",
                        tasks=[
                            "금액 구간 정책과 한도 계산 기준을 별도 정책 계층 책임으로 정의합니다.",
                            "승인 필요 구간과 한도 초과 시 처리 경계를 정책 결과로 분리합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["백엔드 아키텍트", "시니어 개발자"],
                        duration_weeks=1,
                        deliverables=["금액 정책 설계안", "한도 계산 명세", "구간별 처리 흐름도"],
                    ),
                    ExecutionPlanWeek(
                        week_label="3주차",
                        goal=f"{concept} API와 정책 서비스에 금액 규칙을 반영합니다.",
                        tasks=[
                            "금액 구간 기준과 한도 계산 규칙을 정책 서비스 호출로 반영합니다.",
                            "승인 필요 경계와 고액 처리 결과를 API 응답 규칙으로 고정합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["백엔드 개발자", "QA"],
                        duration_weeks=1,
                        deliverables=["API 반영 목록", "금액 정책 테스트 케이스", "한도 규칙 구현 체크리스트"],
                    ),
                    ExecutionPlanWeek(
                        week_label="4주차",
                        goal=f"{concept} 화면과 처리 결과 정합성을 금액 정책 기준으로 확인합니다.",
                        tasks=[
                            "금액 구간 안내와 한도 초과 메시지를 정책 결과와 맞춰 정렬합니다.",
                            "유지 계약이 화면과 API 결과에서 유지되는지 확인합니다.",
                        ],
                        related_rules=top_rules,
                        related_contracts=top_contracts,
                        roles=["프론트엔드 개발자", "백엔드 개발자", "QA"],
                        duration_weeks=1,
                        deliverables=["화면 정합성 체크리스트", "정합성 확인 결과", "파일럿 적용안"],
                    ),
                ]
            week1_goal = self._execution_goal_for_template(concept, top, 0)
            week2_goal = f"{option_name} 기준으로 {self._execution_goal_for_template(concept, second or top, 1)}"
            week3_tasks = self._execution_build_tasks(templates, grounded_rules)
            week4_tasks = self._execution_ui_tasks(templates, retained_contracts)
            return [
                ExecutionPlanWeek(
                    week_label="1주차",
                    goal=week1_goal,
                    tasks=self._execution_discovery_tasks(templates, grounded_rules, retained_contracts),
                    related_rules=top_rules,
                    related_contracts=top_contracts,
                    roles=["컨설턴트", "업무 분석가", "백엔드 아키텍트"],
                    duration_weeks=1,
                    deliverables=list(self._execution_deliverables_for_template(top, 0)),
                ),
                ExecutionPlanWeek(
                    week_label="2주차",
                    goal=week2_goal,
                    tasks=self._execution_design_tasks(templates, grounded_rules),
                    related_rules=second_rules or top_rules,
                    related_contracts=second_contracts or top_contracts,
                    roles=["백엔드 아키텍트", "시니어 개발자"],
                    duration_weeks=1,
                    deliverables=list(self._execution_deliverables_for_template(second or top, 1)),
                ),
                ExecutionPlanWeek(
                    week_label="3주차",
                    goal=(
                        f"{concept} API, 서비스, 권한 정책에 핵심 규칙을 반영합니다."
                        if top and top.template_id == "access_control"
                        else f"{concept} API, 서비스, 상태 정책에 핵심 규칙을 반영합니다."
                        if top and top.template_id == "state_transition"
                        else f"{concept} API, 서비스, 조회 모델에 핵심 규칙을 반영합니다."
                        if top and top.template_id == "query_filter"
                        else f"{concept} API, 서비스, 한도 정책에 핵심 규칙을 반영합니다."
                        if top and top.template_id == "amount_threshold"
                        else f"{concept} API, 서비스, 검증 흐름에 핵심 규칙을 반영합니다."
                    ),
                    tasks=week3_tasks,
                    related_rules=[rule.title for rule in grounded_rules[:3]],
                    related_contracts=[item.item for item in retained_contracts[:2]],
                    roles=["백엔드 개발자", "QA"],
                    duration_weeks=1,
                    deliverables=(
                        ["API 반영 목록", "상태 정책 테스트 케이스", "전이 구현 체크리스트"]
                        if top and top.template_id == "state_transition"
                        else ["API 반영 목록", "조회 모델 테스트 케이스", "조회 규칙 구현 체크리스트"]
                        if top and top.template_id == "query_filter"
                        else ["API 반영 목록", "한도 정책 테스트 케이스", "금액 규칙 구현 체크리스트"]
                        if top and top.template_id == "amount_threshold"
                        else ["API 반영 목록", "정책 테스트 케이스", "검증 구현 체크리스트"]
                    ),
                ),
                ExecutionPlanWeek(
                    week_label="4주차",
                    goal=f"{concept} 화면과 전체 흐름의 정합성을 규칙 기준으로 검증합니다.",
                    tasks=week4_tasks,
                    related_rules=[rule.title for rule in grounded_rules[:3]],
                    related_contracts=[item.item for item in retained_contracts[:2]],
                    roles=["프론트엔드 개발자", "백엔드 개발자", "QA"],
                    duration_weeks=1,
                    deliverables=["화면 정합성 체크리스트", "회귀 검증 결과", "파일럿 적용안"],
                ),
            ]
    
    def _build_template_risks(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
            retained_contracts: list[RetainedContract],
            applied_templates: list[AppliedJudgmentTemplate],
        ) -> list[str]:
            risks: list[str] = []
            ordered_templates = self._ordered_templates_for_generation(prepared, applied_templates, grounded_rules)
            for template in ordered_templates[:2]:
                spec = get_judgment_template_spec(template.template_id)
                lead_rule = template.matched_rule_titles[0] if template.matched_rule_titles else ""
                lead_contract = template.matched_contract_items[0] if template.matched_contract_items else ""
                if spec.risk_patterns:
                    risks.append(spec.risk_patterns[0])
                if lead_rule:
                    risks.append(f"{self._append_suffix_without_dup(lead_rule, '규칙')}이 누락되면 {self._primary_concept(prepared)} 핵심 흐름을 잘못 재현할 수 있습니다.")
                if lead_contract:
                    risks.append(f"{lead_contract} 계약이 흔들리면 기존 처리 조건과 화면 표시가 어긋날 수 있습니다.")
            if prepared.missing_context:
                risks.append("입력 자산이 제한적이므로 제안은 설계 초안 수준이며 추가 파일 확인이 필요합니다.")
            deduped = self._dedupe_list(risks)
            primary = self._primary_template(prepared, applied_templates)
            if primary and primary.template_id == "state_transition":
                deduped = sorted(
                    deduped,
                    key=lambda item: (
                        0 if "상태 전이" in item or "처리 가능 상태" in item else 1,
                        1 if "검증" in item or "차단" in item or "한도" in item else 0,
                    ),
                )
            elif primary and primary.template_id == "access_control":
                deduped = sorted(deduped, key=lambda item: 0 if "권한" in item or "승인" in item or "부서" in item else 1)
            return deduped[:4]
    
    def _execution_goal_for_template(self, concept: str, template: AppliedJudgmentTemplate | None, stage: int) -> str:
            if not template:
                return f"{concept} 핵심 규칙과 데이터 계약을 구조화합니다." if stage == 0 else f"{concept} 정책과 검증 구조를 설계합니다."
            if template.template_id == "state_transition" and stage == 1:
                return f"{concept} 상태 전이 정책과 처리 가능 상태 판단 구조를 설계합니다."
            spec = get_judgment_template_spec(template.template_id)
            defaults = spec.execution_plan_defaults[min(stage, len(spec.execution_plan_defaults) - 1)]
            return self._compose_concept_goal(concept, str(defaults["goal"]))
    
    def _compose_concept_goal(self, concept: str, goal: str) -> str:
            normalized_concept = (concept or "").strip()
            normalized_goal = (goal or "").strip()
            if not normalized_concept:
                return normalized_goal
            if not normalized_goal:
                return normalized_concept
            concept_tokens = [token for token in re.split(r"[/\s]+", normalized_concept) if token]
            if normalized_goal.startswith(normalized_concept):
                return normalized_goal
            if any(normalized_goal.startswith(token) for token in concept_tokens):
                return normalized_goal
            return f"{normalized_concept} {normalized_goal}"
    
    def _append_suffix_without_dup(self, text: str, suffix: str) -> str:
            normalized = (text or "").strip()
            normalized_suffix = (suffix or "").strip()
            if not normalized:
                return normalized_suffix
            if not normalized_suffix or normalized.endswith(normalized_suffix):
                return normalized
            return f"{normalized} {normalized_suffix}"
    
    def _with_object_particle(self, text: str) -> str:
            normalized = (text or "").strip()
            if not normalized:
                return normalized
            last = normalized[-1]
            if "가" <= last <= "힣":
                has_batchim = (ord(last) - ord("가")) % 28 != 0
                return f"{normalized}{'을' if has_batchim else '를'}"
            return f"{normalized}를"
    
    def _execution_deliverables_for_template(self, template: AppliedJudgmentTemplate | None, stage: int) -> tuple[str, ...]:
            if not template:
                return ("규칙 목록", "계약 유지 목록")
            spec = get_judgment_template_spec(template.template_id)
            defaults = spec.execution_plan_defaults[min(stage, len(spec.execution_plan_defaults) - 1)]
            return tuple(defaults["deliverables"])
    
    def _execution_discovery_tasks(
            self,
            templates: list[AppliedJudgmentTemplate],
            grounded_rules: list[GroundedBusinessRule],
            retained_contracts: list[RetainedContract],
        ) -> list[str]:
            tasks: list[str] = []
            for template in templates[:2]:
                if template.template_id == "state_transition":
                    tasks.append("직접 확인된 상태 전이 규칙과 처리 가능 상태를 표로 정리합니다.")
                elif template.template_id == "access_control":
                    tasks.append("권한 주체, 부서 책임, 승인 경로를 규칙 표로 정리합니다.")
                elif template.template_id == "validation":
                    tasks.append("금액 한도, 선행 차단, 상태 제한 조건을 검증 규칙으로 분리합니다.")
                elif template.template_id == "query_filter":
                    tasks.append("조회 조건, 필터 조합, 정렬 규칙을 조회 모델 기준으로 정리합니다.")
                elif template.template_id == "amount_threshold":
                    tasks.append("금액 구간과 한도 임계값을 정책 규칙 표로 정리합니다.")
            if retained_contracts:
                tasks.append("직접 확인된 상태값, 컬럼, 플래그 계약을 유지 목록으로 고정합니다.")
            return self._dedupe_list(tasks)[:4]
    
    def _execution_design_tasks(self, templates: list[AppliedJudgmentTemplate], grounded_rules: list[GroundedBusinessRule]) -> list[str]:
            tasks: list[str] = []
            for template in templates[:2]:
                if template.template_id == "state_transition":
                    tasks.append("상태 전이 정책과 처리 가능 상태 판단 기준을 인터페이스로 정의합니다.")
                elif template.template_id == "access_control":
                    tasks.append("권한 정책과 예외 승인 경계를 별도 서비스 책임으로 정의합니다.")
                elif template.template_id == "validation":
                    tasks.append("저장 전 검증과 정책 검증의 경계를 분리하고 순서를 정의합니다.")
                elif template.template_id == "query_filter":
                    tasks.append("조회 모델과 SQL 조건 매핑 규칙을 별도 조회 계층 책임으로 정의합니다.")
                elif template.template_id == "amount_threshold":
                    tasks.append("금액 한도 정책과 한도 초과 후속 처리 경계를 별도 정책 책임으로 정의합니다.")
            if grounded_rules:
                tasks.append("직접 확인된 규칙이 API와 서비스 경계에 어떻게 반영되는지 명세로 고정합니다.")
            return self._dedupe_list(tasks)[:4]
    
    def _execution_build_tasks(self, templates: list[AppliedJudgmentTemplate], grounded_rules: list[GroundedBusinessRule]) -> list[str]:
            tasks: list[str] = []
            if any(item.template_id == "validation" for item in templates):
                tasks.append("직접 확인된 차단 조건과 한도 규칙을 검증 계층에 반영합니다.")
            if any(item.template_id == "amount_threshold" for item in templates):
                tasks.append("금액 구간과 한도 정책을 서비스 계층의 정책 호출로 반영합니다.")
            if any(item.template_id == "access_control" for item in templates):
                tasks.append("승인 주체와 부서별 처리 권한을 서비스 계층의 정책 호출로 연결합니다.")
                tasks.append("예외 승인 경로와 일반 처리 경로를 권한 정책 기준으로 분리합니다.")
            if any(item.template_id == "state_transition" for item in templates):
                tasks.append("상태 전이 규칙과 처리 가능 상태 조건을 API와 서비스 흐름에 반영합니다.")
            if any(item.template_id == "query_filter" for item in templates):
                tasks.append("조회 조건 모델과 정렬/페이징 규칙을 조회 API와 SQL 매핑에 반영합니다.")
            if grounded_rules:
                tasks.append(f"{self._append_suffix_without_dup(grounded_rules[0].title, '규칙')}을 회귀 테스트 케이스로 고정합니다.")
            for rule in grounded_rules[:3]:
                text = f"{rule.title} {rule.description}"
                if "REVIEW_REQUIRED" in text and all("REVIEW_REQUIRED" not in task for task in tasks):
                    tasks.append("REVIEW_REQUIRED 전이 규칙을 상태 전이 테스트 케이스로 고정합니다.")
                if "300만원" in text and all("300만원" not in task for task in tasks):
                    tasks.append("300만원 한도 규칙을 서비스 계층 검증으로 반영합니다.")
                if "CLAIM_AUDIT" in text and all("CLAIM_AUDIT" not in task for task in tasks):
                    tasks.append("CLAIM_AUDIT 전담 규칙을 권한 정책 호출로 반영합니다.")
            return self._dedupe_list(tasks)[:4]
    
    def _execution_ui_tasks(self, templates: list[AppliedJudgmentTemplate], retained_contracts: list[RetainedContract]) -> list[str]:
            tasks: list[str] = []
            if any(item.template_id == "access_control" for item in templates):
                tasks.append("화면 액션 노출과 승인 버튼 표시를 정책 결과와 일치하도록 정렬합니다.")
                tasks.append("부서별 처리 경로 안내와 승인 주체 표시를 정책 결과와 맞춰 정렬합니다.")
            if any(item.template_id == "state_transition" for item in templates):
                tasks.append("상태 표시와 처리 가능 상태 안내를 정책 결과와 맞춰 검증합니다.")
            if any(item.template_id == "validation" for item in templates):
                tasks.append("입력 검증과 저장 전 차단 메시지를 검증 결과와 맞춰 정렬합니다.")
            if any(item.template_id == "query_filter" for item in templates):
                tasks.append("필터 입력, 정렬, 페이징 UI를 조회 모델과 맞춰 정렬합니다.")
            if any(item.template_id == "amount_threshold" for item in templates):
                tasks.append("한도 안내와 고액 처리 메시지를 정책 결과와 맞춰 정렬합니다.")
            if retained_contracts:
                tasks.append("유지 계약이 화면과 API 결과에서 깨지지 않는지 회귀 검증합니다.")
            return self._dedupe_list(tasks)[:4]
    
    def _priority_reason(self, base_reason: str, template: AppliedJudgmentTemplate, grounded_rules: list[GroundedBusinessRule]) -> str:
            lead_rules = ", ".join(template.matched_rule_titles[:3]) or ", ".join(rule.title for rule in grounded_rules[:2])
            return f"{lead_rules} 규칙이 직접 확인되어 {base_reason}"
    
    def _priority_prerequisite(self, base_prerequisite: str, template: AppliedJudgmentTemplate, retained_contracts: list[RetainedContract]) -> str:
            if template.matched_contract_items:
                return f"{', '.join(template.matched_contract_items[:2])} 유지 계약 확정"
            if retained_contracts:
                return f"{retained_contracts[0].item} 확정"
            return base_prerequisite
    
    def _selection_priority_keywords(self, applied_templates: list[AppliedJudgmentTemplate]) -> list[str]:
            keywords: list[str] = []
            for item in applied_templates[:2]:
                if item.template_id == "state_transition":
                    keywords.extend(["REVIEW_REQUIRED", "상태", "READY", "CLOSED", "배송보류"])
                elif item.template_id == "workflow":
                    keywords.extend(["승인", "approver", "approval", "reject", "delegate", "단계"])
                elif item.template_id == "access_control":
                    keywords.extend(["대리점", "CLAIM_AUDIT", "FRAUD", "권한", "지점장"])
                elif item.template_id == "validation":
                    keywords.extend(["300만원", "한도", "B99", "delivery_hold", "차단"])
                elif item.template_id == "query_filter":
                    keywords.extend(["검색", "조회", "필터", "정렬", "페이징"])
                elif item.template_id == "amount_threshold":
                    keywords.extend(["금액", "한도", "고액", "threshold", "limit"])
            return keywords
    
    def _template_retained_contract_specs(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
        ) -> list[dict[str, object]]:
            combined = self._combined_evidence_text(prepared)
            lowered = combined.lower()
            table_name = self._detect_primary_table_name(prepared)
            specs: list[dict[str, object]] = []
            seen: set[str] = set()
            candidate_ids = self._candidate_template_ids(prepared, grounded_rules)
            validation_primary = self._is_validation_primary(prepared)
            access_control_primary = self._should_enrich_access_control(prepared, grounded_rules) or self._has_claim_access_control_focus(prepared, grounded_rules)
            query_filter_primary = prepared.signals.primary_feature_mode == "search_filters"
            amount_threshold_primary = "amount_threshold" in candidate_ids and self._should_force_amount_threshold_narrative(prepared, grounded_rules) and not self._has_claim_access_control_focus(prepared, grounded_rules)
            status_tokens = self._extract_status_tokens(combined)
            status_field = f"{table_name}.status" if table_name else "status"
            if "state_transition" in candidate_ids and status_tokens and not validation_primary and not query_filter_primary and not self._has_workflow_pattern(prepared):
                specs.append(self._contract_spec(
                    item=f"{status_field} 컬럼의 상태값({', '.join(status_tokens[:4])}) 계약은 유지하는 것이 필요합니다.",
                    keywords=tuple(status_tokens[:4] + ["status", "state"]),
                    basis="직접 확인된 상태값 계약이 깨지면 처리 가능 범위와 후속 흐름이 달라집니다.",
                    seen=seen,
                ))
            if "query_filter" in candidate_ids:
                if any(token in lowered for token in ("request.getparameter", "@requestparam", "querystring", "keyword", "statusfilter", "filter")):
                    specs.append(self._contract_spec(
                        item="조회 조건 파라미터 계약은 유지하는 것이 필요합니다.",
                        keywords=("request.getparameter", "@requestparam", "querystring", "keyword", "statusfilter", "filter"),
                        basis="조회 파라미터 계약이 바뀌면 같은 조회 요청에서도 조건 해석이 달라질 수 있습니다.",
                        seen=seen,
                    ))
                if any(token in lowered for token in ("order by", "sort", "paging", "page", "limit", "offset", "정렬", "페이징")):
                    specs.append(self._contract_spec(
                        item="정렬과 페이징 기본값 계약은 유지하는 것이 필요합니다.",
                        keywords=("order by", "sort", "paging", "page", "limit", "offset", "정렬", "페이징"),
                        basis="정렬과 페이징 기본값이 달라지면 같은 조회 조건에서도 결과 순서가 달라질 수 있습니다.",
                        seen=seen,
                    ))
                if any(token in lowered for token in ("where", "criteria", "검색", "조회", "filter", "and", "or")):
                    specs.append(self._contract_spec(
                        item="필터 조합과 결과 일관성 계약은 유지하는 것이 필요합니다.",
                        keywords=("where", "criteria", "검색", "조회", "filter", "and", "or"),
                        basis="필터 조합 규칙이 바뀌면 결과 목록 구성과 조건 해석이 달라질 수 있습니다.",
                        seen=seen,
                    ))
            if "workflow" in candidate_ids and self._has_workflow_pattern(prepared):
                if any(token in lowered for token in ("submitted", "approve", "approved", "reject", "rejected", "hold", "pending", "approval")):
                    specs.append(self._contract_spec(
                        item="승인 경로와 처리 순서 계약은 유지하는 것이 필요합니다.",
                        keywords=("submitted", "approve", "approved", "reject", "rejected", "hold", "pending", "approval"),
                        basis="승인 경로와 처리 순서가 바뀌면 승인 결과와 후속 처리 흐름이 달라질 수 있습니다.",
                        seen=seen,
                    ))
                if any(token in lowered for token in ("approver", "approverrole", "approver_role", "reviewer", "manager", "finance", "admin", "승인자", "결재자")):
                    specs.append(self._contract_spec(
                        item="승인 권한 체계 계약은 유지하는 것이 필요합니다.",
                        keywords=("approver", "approverrole", "approver_role", "reviewer", "manager", "finance", "admin", "승인자", "결재자"),
                        basis="승인 권한 체계가 바뀌면 승인 주체와 승인 경로가 달라질 수 있습니다.",
                        seen=seen,
                    ))
                if any(token in lowered for token in ("approvalstep", "approval_step", "approvallevel", "approval_level", "step", "stage", "1차", "2차", "단계")):
                    specs.append(self._contract_spec(
                        item="단계별 승인 순서 계약은 유지하는 것이 필요합니다.",
                        keywords=("approvalstep", "approval_step", "approvallevel", "approval_level", "step", "stage", "1차", "2차", "단계"),
                        basis="단계별 승인 순서가 달라지면 승인 흐름과 후속 상태 반영이 달라질 수 있습니다.",
                        seen=seen,
                    ))
                if any(token in lowered for token in ("approve", "reject", "hold", "pending", "delegate", "자동 승인", "반려", "보류", "대리 승인", "escalation")):
                    specs.append(self._contract_spec(
                        item="승인 경로와 예외 승인 규칙 계약은 유지하는 것이 필요합니다.",
                        keywords=("approve", "reject", "hold", "pending", "delegate", "자동 승인", "반려", "보류", "대리 승인", "escalation"),
                        basis="승인 경로와 예외 승인 규칙이 바뀌면 승인 결과와 운영 예외 흐름이 달라질 수 있습니다.",
                        seen=seen,
                    ))
            if access_control_primary and self._primary_concept(prepared) == "청구 조정":
                if any(token in lowered for token in ("branch_manager", "3000000", "300만원", "지점장")):
                    specs.append(self._contract_spec(
                        item="claim_amount >= 3000000 지점장 승인 경계 규칙은 유지하는 것이 필요합니다.",
                        keywords=("claim_amount", "3000000", "300만원", "branch_manager", "지점장"),
                        basis="지점장 승인 경계가 바뀌면 승인 주체와 처리 권한 범위가 달라질 수 있습니다.",
                        seen=seen,
                    ))
                if any(token in lowered for token in ("claim_audit", "dept_code", "10000000", "1천만원")):
                    specs.append(self._contract_spec(
                        item="claim_amount >= 10000000 and dept_code = CLAIM_AUDIT 규칙은 유지하는 것이 필요합니다.",
                        keywords=("claim_amount", "10000000", "1천만원", "dept_code", "claim_audit"),
                        basis="고액 처리 전담 부서 규칙은 직접 확인된 권한 계약입니다.",
                        seen=seen,
                    ))
                if any(token in lowered for token in ("fraud", "hq_reviewer")):
                    specs.append(self._contract_spec(
                        item="accident_type = FRAUD HQ_REVIEWER 심사 규칙은 유지하는 것이 필요합니다.",
                        keywords=("fraud", "hq_reviewer", "accident_type"),
                        basis="사고 유형별 본사 심사 규칙이 바뀌면 승인 주체와 심사 경로가 달라질 수 있습니다.",
                        seen=seen,
                    ))
                if any(token in lowered for token in ("b99", "urgent", "긴급", "선승인")):
                    specs.append(self._contract_spec(
                        item="branch_code = B99 긴급건 본사 선승인 규칙은 유지하는 것이 필요합니다.",
                        keywords=("b99", "urgent", "긴급", "선승인", "branch_code"),
                        basis="특수 지점 긴급건의 예외 승인 경로가 바뀌면 승인 흐름과 후속 처리 기준이 달라질 수 있습니다.",
                        seen=seen,
                    ))
            if "validation" in candidate_ids and not access_control_primary and not amount_threshold_primary and any(token in lowered for token in ("delivery_hold_flag", "deliveryhold", "배송보류")):
                specs.append(self._contract_spec(
                    item="delivery_hold_flag 선행 차단 규칙은 유지하는 것이 필요합니다.",
                    keywords=("delivery_hold_flag", "deliveryhold", "배송보류"),
                    basis="선행 차단 규칙은 직접 확인된 검증 계약입니다.",
                    seen=seen,
                ))
            if "validation" in candidate_ids and not access_control_primary and not amount_threshold_primary and any(token in lowered for token in ("duplicate", "중복", "exists", "count(", "count(1)")):
                specs.append(self._contract_spec(
                    item="동일 대상 중복 처리 차단 규칙은 유지하는 것이 필요합니다.",
                    keywords=("duplicate", "중복", "exists", "count", "existsby", "count(1)"),
                    basis="중복 처리 차단은 직접 확인된 검증 계약이므로 유지해야 합니다.",
                    seen=seen,
                ))
            if "validation" in candidate_ids and not access_control_primary and not amount_threshold_primary and any(token in lowered for token in ("blocked", "forbidden", "invalid", "조정 불가", "save(", "repository.save", "throw new")):
                specs.append(self._contract_spec(
                    item="저장 전 차단 조건은 유지하는 것이 필요합니다.",
                    keywords=("blocked", "forbidden", "invalid", "조정 불가", "save", "repository.save", "throw"),
                    basis="저장 전 차단 조건은 직접 확인된 검증 계약이므로 유지해야 합니다.",
                    seen=seen,
                ))
            if "validation" in candidate_ids and not access_control_primary and not amount_threshold_primary and any(token in lowered for token in ("required", "선행", "before", "prior", "flag", "delivery_hold", "pending")):
                specs.append(self._contract_spec(
                    item="선행 조건 확인과 검증 순서는 유지하는 것이 필요합니다.",
                    keywords=("required", "선행", "before", "prior", "flag", "delivery_hold", "pending"),
                    basis="검증 순서와 선행 조건은 직접 확인된 검증 흐름 계약입니다.",
                    seen=seen,
                ))
            if "amount_threshold" in candidate_ids and not access_control_primary:
                for amount_spec in self._extract_amount_threshold_contract_specs(combined):
                    built = self._contract_spec(
                        item=str(amount_spec["item"]),
                        keywords=tuple(amount_spec["keywords"]),
                        basis=str(amount_spec["basis"]),
                        seen=seen,
                    )
                    if built:
                        specs.append(built)
            if "access_control" in candidate_ids and all(token in lowered for token in ("channel_code", "agency", "hq")):
                specs.append(self._contract_spec(
                    item="channel_code = 'AGENCY' 본사 승인 조건은 유지하는 것이 필요합니다.",
                    keywords=("channel_code", "agency", "hq", "고액", "5000000"),
                    basis="채널 기반 승인 조건은 직접 확인된 권한 계약입니다.",
                    seen=seen,
                ))
            if "validation" in candidate_ids and not access_control_primary and any(token in lowered for token in ("3000000", "300만원")):
                amount_field = "claim_amount" if "claim_amount" in lowered else "amount"
                specs.append(self._contract_spec(
                    item=f"{amount_field} >= 3000000 한도 규칙은 유지하는 것이 필요합니다.",
                    keywords=(amount_field, "3000000", "300만원", "branch_manager", "지점장"),
                    basis="직접 확인된 금액 한도 정책이므로 유지해야 합니다.",
                    seen=seen,
                ))
            if "access_control" in candidate_ids and any(token in lowered for token in ("claim_audit", "dept_code")) and self._primary_concept(prepared) != "청구 조정":
                specs.append(self._contract_spec(
                    item="claim_amount >= 10000000 and dept_code = CLAIM_AUDIT 규칙은 유지하는 것이 필요합니다.",
                    keywords=("claim_amount", "10000000", "1천만원", "dept_code", "claim_audit"),
                    basis="고액 처리 전담 부서 규칙은 직접 확인된 권한 계약입니다.",
                    seen=seen,
                ))
            return [item for item in specs if item]

    def _extract_amount_threshold_contract_specs(self, text: str) -> list[dict[str, object]]:
            lowered = (text or "").lower()
            specs: list[dict[str, object]] = []
            amount_field = "order_amount" if "order_amount" in lowered else "claim_amount" if "claim_amount" in lowered else "amount"
            amount_pattern = rf"{re.escape(amount_field)}\s*(?:<=|<|>=|>)\s*(\d{{5,}})"
            amount_boundaries = self._extract_numeric_matches(lowered, amount_pattern)
            if len(amount_boundaries) >= 2:
                specs.append(
                    {
                        "item": f"{amount_field} 금액 구간 경계({', '.join(amount_boundaries[:2])}) 계약은 유지하는 것이 필요합니다.",
                        "keywords": [amount_field, "금액", "구간", *amount_boundaries[:2]],
                        "basis": "금액 구간 경계가 바뀌면 구간별 처리 정책과 결과 등급이 달라질 수 있습니다.",
                    }
                )
            elif amount_boundaries:
                specs.append(
                    {
                        "item": f"{amount_field} 금액 기준({amount_boundaries[0]}) 계약은 유지하는 것이 필요합니다.",
                        "keywords": [amount_field, "금액", amount_boundaries[0]],
                        "basis": "직접 확인된 금액 기준이 바뀌면 기본 처리 구간이 달라질 수 있습니다.",
                    }
                )
            elif amount_field == "amount":
                generic_boundaries = self._extract_numeric_matches(lowered, r"amount\s*(?:<=|<|>=|>)\s*(\d{5,})")
                if len(generic_boundaries) >= 2:
                    specs.append(
                        {
                            "item": f"amount 금액 구간 경계({', '.join(generic_boundaries[:2])}) 계약은 유지하는 것이 필요합니다.",
                            "keywords": ["amount", "금액", "구간", *generic_boundaries[:2]],
                            "basis": "금액 구간 경계가 바뀌면 구간별 처리 정책과 결과 등급이 달라질 수 있습니다.",
                        }
                    )
                elif generic_boundaries:
                    specs.append(
                        {
                            "item": f"amount 금액 기준({generic_boundaries[0]}) 계약은 유지하는 것이 필요합니다.",
                            "keywords": ["amount", "금액", generic_boundaries[0]],
                            "basis": "직접 확인된 금액 기준이 바뀌면 기본 처리 구간이 달라질 수 있습니다.",
                        }
                    )

            limit_field = None
            if "dailylimit" in lowered:
                limit_field = "dailyLimit"
            elif "daily_limit" in lowered:
                limit_field = "daily_limit"
            elif "limit_amount" in lowered:
                limit_field = "limit_amount"
            if limit_field and re.search(rf"(?:{amount_field}|amount)\s*(?:<=|<|>=|>)\s*{re.escape(limit_field.lower())}", lowered):
                specs.append(
                    {
                        "item": f"{limit_field} 한도 기준 계약은 유지하는 것이 필요합니다.",
                        "keywords": [limit_field, "한도", "limit"],
                        "basis": "한도 기준 필드가 바뀌면 구간별 처리 판단과 초과 기준이 달라질 수 있습니다.",
                    }
                )

            approval_values = self._extract_numeric_matches(
                lowered,
                rf"(?:{amount_field}|amount)[^\n]{{0,24}}(?:<=|<|>=|>)\s*(\d{{5,}})[^\n]{{0,80}}(?:requires_|manager|finance|승인 필요|본사 승인|검토)",
            )
            if approval_values:
                approval_field = "amount" if re.search(r"\bamount\b", lowered) else amount_field
                specs.append(
                    {
                        "item": f"{approval_field} 승인 필요 경계({approval_values[0]}) 계약은 유지하는 것이 필요합니다.",
                        "keywords": [approval_field, approval_values[0], "승인", "approval"],
                        "basis": "승인 필요 경계가 바뀌면 고액 처리 기준과 승인 흐름이 달라질 수 있습니다.",
                    }
                )
            return specs[:3]

    def _extract_numeric_matches(self, text: str, pattern: str) -> list[str]:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            ordered: list[str] = []
            for match in matches:
                parts = [item for item in match if item] if isinstance(match, tuple) else [match]
                for part in parts:
                    if part and part not in ordered:
                        ordered.append(part)
            return ordered

    def _candidate_template_ids(
            self,
            prepared: PreparedRebuildInput,
            grounded_rules: list[GroundedBusinessRule],
        ) -> list[JudgmentTemplateId]:
            ordered: list[JudgmentTemplateId] = []
            mode_map: dict[str, tuple[JudgmentTemplateId, ...]] = {
                "status_permissions": ("workflow", "state_transition", "access_control"),
                "search_filters": ("query_filter",),
                "save_validation": ("validation",),
            }
            for mode in (prepared.signals.primary_feature_mode, prepared.signals.secondary_feature_mode):
                for template_id in mode_map.get(mode or "", ()):
                    if template_id not in ordered:
                        ordered.append(template_id)
            for rule in grounded_rules:
                for template_id in self._template_ids_for_rule(rule):
                    if template_id not in ordered:
                        ordered.append(template_id)
            return ordered
    
    def _contract_spec(
            self,
            *,
            item: str,
            keywords: tuple[str, ...],
            basis: str,
            seen: set[str],
        ) -> dict[str, object] | None:
            key = self._normalize_key(item)
            if not key or key in seen:
                return None
            seen.add(key)
            return {"item": item, "keywords": keywords, "basis": basis}
    
    def _combined_evidence_text(self, prepared: PreparedRebuildInput) -> str:
            return " ".join(
                [
                    prepared.assets.source_code,
                    prepared.assets.ui_template,
                    prepared.assets.sql_queries,
                    prepared.assets.database_schema,
                ]
            )
    
    def _detect_primary_table_name(self, prepared: PreparedRebuildInput) -> str:
            text = " ".join([prepared.assets.database_schema, prepared.assets.sql_queries])
            match = re.search(r"\bcreate\s+table\s+([a-zA-Z_][a-zA-Z0-9_]*)", text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1)
                return "" if re.fullmatch(r"TBL_\d+", candidate, flags=re.IGNORECASE) else candidate
            match = re.search(r"\bfrom\s+([a-zA-Z_][a-zA-Z0-9_]*)", text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1)
                return "" if re.fullmatch(r"TBL_\d+", candidate, flags=re.IGNORECASE) else candidate
            return ""
    
    def _extract_status_tokens(self, text: str) -> list[str]:
            text = text or ""
            output: list[str] = []
            blocked = {
                "SELECT",
                "WHERE",
                "FROM",
                "AND",
                "OR",
                "CREATE",
                "TABLE",
                "CLAIM_AUDIT",
                "HQ",
                "HQ_REVIEWER",
                "BRANCH_MANAGER",
            }
            has_explicit_transition = bool(
                re.search(
                    r"\bsetstatus\s*\(|\bset\s+status\s*=|\bupdate\b[\s\S]{0,120}\bset\b",
                    text,
                    flags=re.IGNORECASE,
                )
            )
    
            patterns = [
                r"\bstatus\s+in\s*\(([^)]+)\)",
                r"\bstatus\s*(?:==|=|eq)\s*[\"']([A-Z_]{3,})[\"']",
                r"[\"']([A-Z_]{3,})[\"']\s*\.equals\s*\(\s*[^)]*getstatus\s*\(\s*\)[^)]*\)",
                r"getstatus\s*\(\s*\)\s*\.equals\s*\(\s*[\"']([A-Z_]{3,})[\"']\s*\)",
                r"\bsetstatus\s*\(\s*[\"']([A-Z_]{3,})[\"']\s*\)",
                r"\bset\s+status\s*=\s*[\"']([A-Z_]{3,})[\"']",
                r"\bupdate\b[\s\S]{0,120}\bset\s+status\s*=\s*[\"']([A-Z_]{3,})[\"']",
            ]
    
            for pattern in patterns:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    groups = [item for item in match.groups() if item]
                    if not groups:
                        continue
                    if "," in groups[0] or "'" in groups[0] or '"' in groups[0]:
                        candidates = re.findall(r"[\"']([A-Z_]{3,})[\"']", groups[0])
                    else:
                        candidates = groups
                    for token in candidates:
                        if token in blocked or token in output:
                            continue
                        output.append(token)
            if has_explicit_transition:
                for match in re.finditer(r"\bin\s*\(([^)]+)\)", text, flags=re.IGNORECASE):
                    candidates = re.findall(r"[\"']([A-Z_]{3,})[\"']", match.group(1))
                    for token in candidates:
                        if token in blocked or token in output:
                            continue
                        output.append(token)
            return output[:5]
    
    def _rule_templates_for_concept(self, concept: str) -> list[dict]:
            if concept == "주문 마감":
                return [
                    {"title": "VIP 야간 마감 제한", "statement": "VIP 고객은 야간 시간대에 주문 마감을 수행할 수 없습니다.", "keywords": ("vip", "22", "23", "00", "야간", "마감"), "preferred_types": ("source", "ui"), "design_targets": ("정책 서비스", "상태 전이", "검증 흐름")},
                    {"title": "대리점 고액 주문 본사 전용", "statement": "대리점 채널의 고액 주문은 본사 권한으로만 마감할 수 있습니다.", "keywords": ("agency", "대리점", "hq", "고액", "5000000"), "preferred_types": ("source",), "design_targets": ("정책 서비스", "권한 모델", "API")},
                    {"title": "배송보류 해제 선행", "statement": "배송보류 상태가 해제되기 전에는 주문 마감을 진행할 수 없습니다.", "keywords": ("delivery", "hold", "배송보류"), "preferred_types": ("source",), "design_targets": ("검증 흐름", "API", "상태 전이")},
                    {"title": "수출 주문 고액건 REVIEW_REQUIRED", "statement": "수출 주문의 고액 건은 즉시 마감하지 않고 REVIEW_REQUIRED 상태로 전환해야 합니다.", "keywords": ("export", "수출", "review_required", "7000000"), "preferred_types": ("source", "sql"), "design_targets": ("상태 전이", "정책 서비스", "API")},
                ]
            if concept == "청구 조정":
                return [
                    {"title": "FRAUD 본사 심사 전용", "statement": "FRAUD 사고건은 HQ_REVIEWER 권한으로만 청구 조정을 수행할 수 있습니다.", "keywords": ("fraud", "hq_reviewer"), "preferred_types": ("source",), "design_targets": ("정책 서비스", "권한 모델", "API")},
                    {"title": "지점장 300만원 한도", "statement": "지점장은 300만원 이상 청구건을 조정할 수 없습니다.", "keywords": ("branch_manager", "지점장", "3000000", "300만원"), "preferred_types": ("source",), "design_targets": ("정책 서비스", "검증 흐름")},
                    {"title": "1천만원 이상 전담 부서 처리", "statement": "1천만원 이상 청구건은 CLAIM_AUDIT 부서만 조정할 수 있습니다.", "keywords": ("10000000", "1천만원", "claim_audit"), "preferred_types": ("source",), "design_targets": ("정책 서비스", "권한 모델", "API")},
                    {"title": "B99 긴급건 본사 선승인", "statement": "B99 지점의 긴급 청구건은 본사 선승인 없이 조정할 수 없습니다.", "keywords": ("b99", "urgent", "긴급", "선승인"), "preferred_types": ("source",), "design_targets": ("예외 승인 흐름", "정책 서비스", "API")},
                    {"title": "마감/취소 상태 조정 금지", "statement": "CLOSED 또는 CANCELLED 상태의 청구건은 조정할 수 없습니다.", "keywords": ("closed", "cancelled", "조정", "adjust"), "preferred_types": ("source", "schema", "sql"), "design_targets": ("상태 전이", "검증 흐름", "API")},
                ]
            return []
    
    def _retained_contract_specs(self, concept: str) -> list[dict[str, object]]:
            if concept == "주문 마감":
                return [
                    {
                        "item": "orders.status 값(PAID, READY, REVIEW_REQUIRED) 계약은 유지하는 것이 필요합니다.",
                        "keywords": ("paid", "ready", "review_required", "status"),
                        "basis": "직접 확인된 상태값 계약이 깨지면 주문 마감과 후속 승인 흐름이 달라집니다.",
                    },
                    {
                        "item": "delivery_hold_flag = 'Y' 선행 차단 규칙은 유지하는 것이 필요합니다.",
                        "keywords": ("deliveryholdflag", "delivery_hold", "배송보류"),
                        "basis": "배송보류 해제 여부는 주문 마감 선행 검증 조건으로 직접 확인되었습니다.",
                    },
                    {
                        "item": "channel_code = 'AGENCY' 고액 주문 본사 승인 조건은 유지하는 것이 필요합니다.",
                        "keywords": ("agency", "channelcode", "hq", "5000000", "고액"),
                        "basis": "대리점 고액 주문 본사 승인 조건은 직접 확인된 권한 계약입니다.",
                    },
                ]
            if concept == "청구 조정":
                return [
                    {
                        "item": "claim.status 값(REVIEW, CLOSED, CANCELLED) 계약은 유지하는 것이 필요합니다.",
                        "keywords": ("review", "closed", "cancelled", "status"),
                        "basis": "직접 확인된 상태값 계약이 깨지면 조정 가능 범위와 승인 흐름이 달라집니다.",
                    },
                    {
                        "item": "claim_amount >= 3000000 지점장 한도 규칙은 유지하는 것이 필요합니다.",
                        "keywords": ("3000000", "300만원", "branch_manager", "지점장"),
                        "basis": "지점장 승인 한도는 직접 확인된 금액 기반 정책입니다.",
                    },
                    {
                        "item": "claim_amount >= 10000000 and dept_code = CLAIM_AUDIT 규칙은 유지하는 것이 필요합니다.",
                        "keywords": ("10000000", "1천만원", "claim_audit", "dept_code"),
                        "basis": "고액 청구 전담 부서 규칙은 직접 확인된 권한/조직 계약입니다.",
                    },
                ]
            return []
    
    def _collect_evidence_refs(
            self,
            prepared: PreparedRebuildInput,
            keywords: tuple[str, ...] | list[str],
            preferred_types: tuple[str, ...],
        ) -> list[EvidenceRef]:
            refs: list[EvidenceRef] = []
            for asset_type, asset_names, text in self._evidence_sources(prepared):
                if asset_type not in preferred_types:
                    continue
                excerpt = self._extract_excerpt(text, keywords)
                if not excerpt:
                    continue
                asset_name = asset_names[0] if asset_names else asset_type
                refs.append(
                    EvidenceRef(
                        asset_name=asset_name,
                        asset_type=asset_type,
                        locator="본문 키워드",
                        excerpt=excerpt,
                        evidence_kind=asset_type,
                    )
                )
            return refs[:3]
    
    def _evidence_sources(self, prepared: PreparedRebuildInput) -> list[tuple[str, list[str], str]]:
            return [
                ("source", prepared.asset_presence.source_asset_names, prepared.assets.source_code),
                ("ui", prepared.asset_presence.ui_asset_names, prepared.assets.ui_template),
                ("schema", prepared.asset_presence.schema_asset_names, prepared.assets.database_schema),
                ("sql", prepared.asset_presence.sql_asset_names, prepared.assets.sql_queries),
            ]
    
    def _extract_excerpt(self, text: str, keywords: tuple[str, ...] | list[str]) -> str:
            if not text:
                return ""
            lowered = text.lower()
            for keyword in keywords:
                needle = (keyword or "").lower()
                if not needle:
                    continue
                idx = lowered.find(needle)
                if idx < 0:
                    continue
                start = max(0, idx - 36)
                end = min(len(text), idx + max(len(keyword), 12) + 36)
                excerpt = " ".join(text[start:end].strip().split())
                return excerpt[:140]
            return ""
    
    def _resolve_confidence(self, evidence: list[EvidenceRef]) -> tuple[str, str]:
            kinds = {item.evidence_kind for item in evidence}
            if kinds & {"source", "ui", "sql", "schema"}:
                return "확정", "현재 자산의 코드, 화면, SQL 또는 스키마에서 직접 확인되었습니다."
            return "가정", "직접 근거가 부족해 가정 수준으로 분류했습니다."
    
    def _dedupe_by_normalized_text(self, items: list, *, attr: str) -> list:
            seen: set[str] = set()
            output = []
            for item in items:
                value = getattr(item, attr, "")
                key = self._normalize_key(value)
                if not key or key in seen:
                    continue
                seen.add(key)
                output.append(item)
            return output
    
    def _normalize_key(self, value: str) -> str:
            return re.sub(r"\s+", " ", (value or "").strip().lower())
    
    def _dedupe_list(self, items: list[str]) -> list[str]:
            seen: set[str] = set()
            output: list[str] = []
            for item in items:
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                output.append(item)
            return output
