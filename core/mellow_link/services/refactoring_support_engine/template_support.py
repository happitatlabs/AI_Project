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
    DOCUMENT_DOMAIN_GROUPS = (
        ("원가", ("원가", "원가체계", "원가분석", "원가계산", "재료비", "노무비", "제조경비", "배부", "배부기준", "손익", "손익분석", "기준정보")),
        ("업무프로세스", ("업무프로세스", "프로세스", "통합재무", "인적자원", "기금", "이행계획", "변화관리", "요구사항", "bpr", "ismp")),
        ("수용가", ("수용가", "민원", "요금", "자재", "자산", "예산", "회계")),
        ("선박", ("선박", "영업", "운항", "장비", "재무", "총무", "협력업체", "해운")),
    )
    DOCUMENT_GENERIC_TERMS = ("현행", "개선", "구조", "계획", "방향", "요구사항", "비교", "기준")

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

    def _is_document_only_input(self, prepared: PreparedRebuildInput) -> bool:
            asset_presence = getattr(prepared, "asset_presence", None)
            has_docs = bool(
                getattr(asset_presence, "has_docs", False)
                or (getattr(prepared, "supporting_docs", "") or "").strip()
            )
            has_operational_assets = any(
                (
                    getattr(asset_presence, "has_source_code", False),
                    getattr(asset_presence, "has_ui_asset", False),
                    getattr(asset_presence, "has_schema_asset", False),
                    getattr(asset_presence, "has_sql_asset", False),
                    bool((prepared.assets.source_code or "").strip()),
                    bool((prepared.assets.database_schema or "").strip()),
                    bool((prepared.assets.sql_queries or "").strip()),
                )
            )
            return has_docs and not has_operational_assets

    def _document_source_text(self, prepared: PreparedRebuildInput) -> str:
            return " ".join(
                [
                    " ".join(prepared.asset_presence.doc_asset_names),
                    prepared.supporting_docs,
                ]
            ).lower()

    def _document_domain_terms(self, prepared: PreparedRebuildInput) -> list[str]:
            text = self._document_source_text(prepared)
            if not text.strip():
                return []
            group_matches: list[tuple[int, str, list[str]]] = []
            for anchor, keywords in self.DOCUMENT_DOMAIN_GROUPS:
                group_hits = [keyword for keyword in keywords if keyword.lower() in text]
                if group_hits:
                    group_matches.append((len(group_hits), anchor, group_hits))
            matched: list[str] = []
            if group_matches:
                _, anchor, group_hits = max(group_matches, key=lambda item: (item[0], len(item[1])))
                matched.append(anchor)
                for keyword in group_hits:
                    if keyword not in matched:
                        matched.append(keyword)
                for keyword in self.DOCUMENT_GENERIC_TERMS:
                    if keyword.lower() in text and keyword not in matched:
                        matched.append(keyword)
                return matched[:8]
            for keyword in self.DOCUMENT_GENERIC_TERMS:
                if keyword.lower() in text and keyword not in matched:
                    matched.append(keyword)
            return matched[:6]

    def _document_focus_terms(self, prepared: PreparedRebuildInput) -> list[str]:
            terms = [term for term in self._document_domain_terms(prepared) if str(term or "").strip()]
            if terms:
                return terms[:4]
            return ["현행 구조", "판단 기준", "개선 방향"]

    def _uses_document_neutral_template_fallback(
        self,
        prepared: PreparedRebuildInput,
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> bool:
            family = str(getattr(getattr(prepared, "family_classification", None), "family", "") or "").strip()
            return not applied_templates and (
                self._is_document_only_input(prepared)
                or family in {"document_consulting", "option_comparison"}
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
            if self._has_fx_fifo_domain(prepared):
                return LayeredListResult(
                    database=[
                        f"예시: {concept} 입금 lot 원장과 출금 lot 소진 이력을 분리해 FIFO 계산 경계를 명확히 합니다.",
                        "예시: lot 잔량(RMN_FAMT/RMN_AMT), 취득 환율, 출금 환율, GAP_AMT를 같은 계산 키로 연결합니다.",
                        "예시: 전표 기준번호와 GL_INTERFACE 적재 컬럼을 lot 계산 결과와 같은 거래 키로 연결합니다.",
                    ],
                    backend=[
                        f"예시: {concept} lot 소진 계산 API와 환차손익 계산 API를 분리해 계산 단계를 명확히 합니다.",
                        "예시: FIFO lot 선택, GAP_AMT 계산, 전표 생성, GL 적재를 순차 서비스로 분리합니다.",
                        "예시: 출금 처리 서비스는 계산 결과를 받아 TN_FOROUD, TN_BKCHIT, GL_INTERFACE 반영만 담당합니다.",
                    ],
                    frontend=[
                        f"예시: {concept} 화면은 입금/출금 내역, 소진 lot, 환차손익, 전표 반영 결과를 분리해 표시합니다.",
                        "예시: lot 소진 상세와 환차손익 계산 근거를 같은 거래 기준번호로 조회합니다.",
                    ],
                )
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

    def _fx_fifo_signal_text(self, prepared: PreparedRebuildInput) -> str:
            return " ".join(
                [
                    prepared.goal,
                    " ".join(prepared.constraints),
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

    def _fx_fifo_signal_buckets(self, prepared: PreparedRebuildInput) -> set[str]:
            text = self._fx_fifo_signal_text(prepared)
            bucket_keywords = {
                "currency": ("외화", "currency", "currency_code", "mney_unit", "환율", "exch_rate"),
                "fifo_lot": ("fifo", "선입선출", "lot", "tn_forins", "tn_forout", "tn_foroud", "rmn_famt", "outf_amt"),
                "gain_loss": ("환차손익", "환차", "exchange p/l", "gap_amt", "gain_loss", "out_amt0"),
                "voucher": ("전표", "voucher", "journal", "gl_interface", "glintf", "user_je_source_name", "user_je_category_name", "reference4", "reference6"),
                "gl": ("gl", "ledger", "set_of_books_id", "code_combination", "segment1", "segment2", "segment3", "entered_dr", "entered_cr"),
                "flow": ("입금", "출금", "deposit", "payment", "forins", "forout"),
            }
            return {
                bucket
                for bucket, keywords in bucket_keywords.items()
                if any(keyword in text for keyword in keywords)
            }

    def _has_fx_fifo_domain(self, prepared: PreparedRebuildInput) -> bool:
            buckets = self._fx_fifo_signal_buckets(prepared)
            return (
                len(buckets) >= 3
                and "fifo_lot" in buckets
                and ("gain_loss" in buckets or "currency" in buckets)
                and ("voucher" in buckets or "gl" in buckets)
            )

    def _has_explicit_redesign_request(self, prepared: PreparedRebuildInput) -> bool:
            text = " ".join([prepared.goal, " ".join(prepared.constraints)]).lower()
            keywords = (
                "redesign",
                "re-architect",
                "rewrite",
                "migration",
                "migrate",
                "replatform",
                "service split",
                "service separation",
                "service decomposition",
                "layer separation",
                "재설계",
                "마이그레이션",
                "전환",
                "재플랫폼",
                "서비스 분리",
                "서비스 분해",
                "계층 분리",
                "재구성 로드맵",
            )
            for keyword in keywords:
                if keyword not in text:
                    continue
                escaped = re.escape(keyword)
                negative_patterns = (
                    rf"(?:not|without|exclude|excluding|defer|later|instead of)[^.\n]{{0,24}}{escaped}",
                    rf"{escaped}[^.\n]{{0,24}}(?:하지\s*마|말라|아니|제외|배제|후속|보조|나중|보다|밀지\s*마|쓰지\s*마|피하)",
                    rf"(?:현행|운영|분석|복원)[^.\n]{{0,24}}우선[^.\n]{{0,24}}{escaped}",
                )
                if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in negative_patterns):
                    continue
                return True
            return False

    def _operational_sql_object_count(self, prepared: PreparedRebuildInput) -> int:
            text = self._fx_fifo_signal_text(prepared)
            patterns = (
                r"\bcreate\s+(?:or\s+replace\s+)?table\b",
                r"\bcreate\s+(?:or\s+replace\s+)?procedure\b",
                r"\bcreate\s+(?:or\s+replace\s+)?trigger\b",
                r"\binsert\s+into\b",
                r"\bupdate\s+[a-z_][a-z0-9_]*\s+set\b",
                r"\bdelete\s+from\b",
            )
            return sum(1 for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE))

    def _operational_domain_keyword_count(self, prepared: PreparedRebuildInput) -> int:
            text = self._fx_fifo_signal_text(prepared)
            keyword_groups = (
                ("fifo", "lot", "선입선출"),
                ("환차", "gain_loss", "gap_amt", "exchange p/l"),
                ("전표", "voucher", "journal"),
                ("gl", "gl_interface", "ledger", "interface"),
                ("history", "posting", "reverse", "cancel", "delete"),
                ("입금", "출금", "deposit", "withdraw", "forins", "forout"),
            )
            return sum(1 for group in keyword_groups if any(keyword in text for keyword in group))

    def _interface_linkage_signal_buckets(self, prepared: PreparedRebuildInput) -> set[str]:
            text = self._fx_fifo_signal_text(prepared)
            bucket_keywords = {
                "staging": (
                    "ib_bulk_tran_add",
                    "staging",
                    "bulk_tran",
                    "file_date",
                    "file_num",
                    "file_seq",
                    "wif_file_key",
                ),
                "daily_add": (
                    "ib_acctall_tr_dd_add",
                    "acctall_tr_dd_add",
                    "acct_seq",
                    "tr_date_seq",
                    "last_upd_date",
                    "last_upd_time",
                ),
                "ack_status": (
                    "tran_status",
                    "tran_result_cd",
                    "erp_rcv_flag",
                    "cnf_yn",
                    "ack",
                    "confirm",
                    "status",
                ),
                "retry_fail": (
                    "retry",
                    "react_cd",
                    "errlog",
                    "fail",
                    "error",
                    "back_yn",
                    "reprocess",
                    "tn_if_retry_his",
                ),
                "snapshot": (
                    "ib_acctall_tr_dd_lst",
                    "latest",
                    "snapshot",
                    "last table",
                    "lst",
                ),
                "pay_order": (
                    "tn_pay_order_dtl",
                    "pay_order",
                    "pay_date",
                    "pay_no",
                    "pay_stat",
                    "pay_hang",
                    "out_acnt_nox",
                ),
                "interface_proc": (
                    "p_fundih",
                    "t_fndi",
                    "interface",
                    "send",
                    "receive",
                    "rcv",
                    "batch",
                ),
            }
            return {
                bucket
                for bucket, keywords in bucket_keywords.items()
                if any(keyword in text for keyword in keywords)
            }

    def _interface_linkage_signal_score(self, prepared: PreparedRebuildInput) -> int:
            buckets = self._interface_linkage_signal_buckets(prepared)
            required = {"staging", "daily_add", "ack_status"}
            return len(buckets) + (1 if required.issubset(buckets) else 0)

    def _has_interface_linkage_domain(self, prepared: PreparedRebuildInput) -> bool:
            buckets = self._interface_linkage_signal_buckets(prepared)
            return (
                {"staging", "daily_add", "ack_status"}.issubset(buckets)
                and len(buckets) >= 4
            )

    def _settlement_journal_signal_buckets(self, prepared: PreparedRebuildInput) -> set[str]:
            text = self._fx_fifo_signal_text(prepared)
            bucket_keywords = {
                "settlement": (
                    "settle",
                    "settlement",
                    "stl_",
                    "stlno",
                    "stl_no",
                    "stl_date",
                    "pay_order",
                    "tn_pay_order_dtl",
                ),
                "voucher_header": (
                    "tn_bkchno",
                    "ac_chitno",
                    "ac_date",
                    "invoice_no",
                    "chk",
                    "header",
                ),
                "voucher_line": (
                    "tn_bkchit",
                    "dc_flag",
                    "acnt_cd",
                    "chit_amt",
                    "journal",
                    "voucher",
                    "line_amt",
                ),
                "gl": (
                    "gl_interface",
                    "glintf",
                    "user_je",
                    "entered_dr",
                    "entered_cr",
                    "reference4",
                    "reference6",
                    "ledger",
                ),
                "reverse_cancel": (
                    "cancel",
                    "reverse",
                    "delete",
                    "back_yn",
                    "can_yn",
                    "reverse_yn",
                    "oac_chitno",
                ),
                "posting_proc": (
                    "posting",
                    "post",
                    "p_stlpost",
                    "t_settle_hdr",
                    "t_settle_hd",
                    "settle_hdr",
                    "settle_dtl",
                ),
            }
            return {
                bucket
                for bucket, keywords in bucket_keywords.items()
                if any(keyword in text for keyword in keywords)
            }

    def _settlement_journal_signal_score(self, prepared: PreparedRebuildInput) -> int:
            buckets = self._settlement_journal_signal_buckets(prepared)
            required = {"voucher_header", "voucher_line"}
            return len(buckets) + (1 if required.issubset(buckets) else 0)

    def _has_settlement_journal_domain(self, prepared: PreparedRebuildInput) -> bool:
            buckets = self._settlement_journal_signal_buckets(prepared)
            return (
                {"voucher_header", "voucher_line"}.issubset(buckets)
                and (
                    "settlement" in buckets
                    or "gl" in buckets
                    or "reverse_cancel" in buckets
                )
                and len(buckets) >= 4
            )

    def _has_operational_source_dominance(self, prepared: PreparedRebuildInput) -> bool:
            asset_presence = prepared.asset_presence
            assets = prepared.assets
            operational_count = sum(
                1
                for present in (
                    bool(asset_presence.has_source_code or (assets.source_code or "").strip()),
                    bool(asset_presence.has_schema_asset or (assets.database_schema or "").strip()),
                    bool(asset_presence.has_sql_asset or (assets.sql_queries or "").strip()),
                )
                if present
            )
            descriptive_count = sum(
                1
                for present in (
                    bool(asset_presence.has_ui_asset or (assets.ui_template or "").strip()),
                    bool(asset_presence.has_framework_hint or (assets.framework_info or "").strip()),
                    bool(asset_presence.has_docs),
                )
                if present
            )
            procedural_assets = sum(
                1
                for name in (
                    list(asset_presence.source_asset_names)
                    + list(asset_presence.schema_asset_names)
                    + list(asset_presence.sql_asset_names)
                )
                if re.search(r"\.(?:sql|ddl|dml|prc|proc|trg|trigger|pkb|pks|fnc)$", str(name or ""), flags=re.IGNORECASE)
            )
            return operational_count + min(procedural_assets, 2) >= max(2, descriptive_count + 1)

    def resolve_question_axis(
            self,
            prepared: PreparedRebuildInput | None,
            *,
            family: str = "",
            narrative_axis: str = "",
        ) -> str:
            if prepared is None:
                return ""
            explicit = str(getattr(prepared, "question_axis", "") or "").strip()
            if explicit:
                return explicit
            resolved_family = str(
                family
                or getattr(getattr(prepared, "family_classification", None), "family", "")
                or ""
            ).strip()
            if resolved_family and resolved_family != "operational_source":
                return ""
            domain = str(narrative_axis or "").strip()
            if not domain:
                if self._has_fx_fifo_domain(prepared):
                    domain = "fx_fifo"
                elif self._has_interface_linkage_domain(prepared) and self._interface_linkage_signal_score(prepared) >= self._settlement_journal_signal_score(prepared):
                    domain = "interface_linkage"
                elif self._has_settlement_journal_domain(prepared):
                    domain = "settlement_journal"
                else:
                    domain = "operational_source"
            text = self._operational_question_axis_text(prepared)
            axis = self._classify_operational_question_axis(text=text, domain=domain)
            prepared.question_axis = axis
            return axis

    def _operational_question_axis_text(self, prepared: PreparedRebuildInput) -> str:
            parts = [
                str(getattr(prepared, "goal", "") or ""),
                str(getattr(getattr(prepared, "intent", None), "scenario", "") or ""),
            ]
            return re.sub(r"\s+", " ", " ".join(part for part in parts if str(part or "").strip())).strip().lower()

    def _classify_operational_question_axis(self, *, text: str, domain: str) -> str:
            normalized = str(text or "").strip().lower()
            if not normalized:
                return "journal_linkage" if domain == "settlement_journal" else "processing_flow"
            journal_terms = (
                "전표",
                "분개",
                "journal",
                "gl",
                "회계 연계",
                "회계 흐름",
                "회계 반영",
                "posting",
                "기준번호",
                "reference",
                "거래 키",
                "연계 키",
                "voucher",
            )
            calculation_terms = (
                "계산 규칙",
                "계산",
                "산출",
                "환율",
                "환차손익",
                "금액 기준",
                "소진 기준",
                "평가 기준",
                "원가",
                "차이",
                "rate",
                "amount",
            )
            flow_terms = (
                "흐름",
                "처리 흐름",
                "처리 순서",
                "순서",
                "어떻게 동작",
                "어떻게 이어",
                "복원",
                "연계 흐름",
                "flow",
                "chain",
                "process",
            )
            journal_score = sum(1 for term in journal_terms if term in normalized)
            calculation_score = sum(1 for term in calculation_terms if term in normalized)
            flow_score = sum(1 for term in flow_terms if term in normalized)
            if "전표 연계" in normalized or "gl 연결" in normalized or "거래 키" in normalized:
                journal_score += 2
            if "계산 규칙" in normalized or "환차손익" in normalized:
                calculation_score += 2
            if "처리 흐름" in normalized or "동작하는지" in normalized:
                flow_score += 2
            if journal_score and journal_score >= max(calculation_score, flow_score):
                return "journal_linkage"
            if flow_score and calculation_score:
                if journal_score == 0 and calculation_score >= flow_score + 3:
                    return "calculation_rule"
                return "processing_flow"
            if calculation_score > flow_score:
                return "calculation_rule"
            if flow_score:
                return "processing_flow"
            return "journal_linkage" if domain == "settlement_journal" else "processing_flow"

    def operational_analysis_profile(self, prepared: PreparedRebuildInput) -> dict[str, object]:
            explicit_redesign = self._has_explicit_redesign_request(prepared)
            dominant_operational_assets = self._has_operational_source_dominance(prepared)
            fx_fifo = self._has_fx_fifo_domain(prepared)
            interface_linkage = self._has_interface_linkage_domain(prepared)
            settlement_journal = self._has_settlement_journal_domain(prepared)
            sql_object_count = self._operational_sql_object_count(prepared)
            domain_keyword_count = self._operational_domain_keyword_count(prepared)
            interface_score = self._interface_linkage_signal_score(prepared)
            settlement_score = self._settlement_journal_signal_score(prepared)
            if fx_fifo:
                domain = "fx_fifo"
            elif interface_linkage and interface_score >= settlement_score:
                domain = "interface_linkage"
            elif settlement_journal:
                domain = "settlement_journal"
            else:
                domain = "operational_source"
            active = (
                not explicit_redesign
                and dominant_operational_assets
                and (
                    fx_fifo
                    or interface_linkage
                    or settlement_journal
                    or (sql_object_count >= 2 and domain_keyword_count >= 4)
                )
            )
            question_axis = self.resolve_question_axis(prepared, family="operational_source", narrative_axis=domain)
            metadata = self._operational_domain_metadata(domain, question_axis=question_axis)
            object_inventory = self._operational_object_inventory(prepared, domain=domain, question_axis=question_axis, limit=8)
            return {
                "active": active,
                "domain": domain,
                "question_axis": question_axis,
                "explicit_redesign": explicit_redesign,
                "dominant_operational_assets": dominant_operational_assets,
                "sql_object_count": sql_object_count,
                "domain_keyword_count": domain_keyword_count,
                "interface_score": interface_score,
                "settlement_score": settlement_score,
                "object_names": [str(item.get("name") or "").strip() for item in object_inventory if str(item.get("name") or "").strip()],
                "object_inventory": object_inventory,
                "object_section_intro": self._operational_object_section_intro(domain, object_inventory, question_axis=question_axis),
                "object_section_lines": self._operational_object_section_lines(object_inventory[:5]),
                **metadata,
            }

    def _has_operational_source_analysis_priority(self, prepared: PreparedRebuildInput) -> bool:
            return bool(self.operational_analysis_profile(prepared).get("active"))

    def _operational_domain_metadata(self, domain: str, *, question_axis: str = "") -> dict[str, object]:
            mapping: dict[str, dict[str, object]] = {
                "fx_fifo": {
                    "report_purpose": "외화 입금, 출금, FIFO lot 소진, 환차손익 계산, 전표 및 GL 흐름을 분석하기 위한 보고서입니다.",
                    "report_scope": ["입금 lot 원장", "출금 lot 소진", "환차손익 계산", "전표 및 GL 흐름"],
                    "report_questions": [
                        "어떤 lot 순서로 출금이 소진되는가?",
                        "환차손익은 어떤 환율과 금액 기준으로 계산되는가?",
                        "계산 결과는 전표와 GL 인터페이스에 어떻게 반영되는가?",
                    ],
                    "identity_sentence": "본 자산은 외화 입금, 외화 출금, 선입선출 lot 소진, 환차손익 계산, 전표 반영까지 이어지는 회계 처리 소스 묶음입니다.",
                    "flow_sentence": "외화 입금이 원장에 적재되고, 출금 시 선입선출 기준으로 lot이 소진되며, 환차손익 계산과 전표 반영이 이어집니다.",
                    "rule_sentence": "입금 잔량 유지, 선입선출 소진 순서, 환율 비교 기준, 회계 반영 키 일치가 핵심입니다.",
                    "risk_sentence": "lot 소진 순서 변경, 환율 기준 불일치, 취소 시 역처리 누락, 회계 연계 누락 가능성을 점검해야 합니다.",
                    "primary_reason": "입력 자산이 외화 입출금 FIFO 운영 소스이므로 현재 단계에서는 현행 업무 규칙과 회계 처리 흐름 복원이 우선입니다.",
                    "follow_up_lines": [
                        "취소와 역처리 시 lot 잔량과 환차손익이 같은 거래 기준으로 유지되는지 추가 확인합니다.",
                        "전표 반영과 회계 연계가 같은 기준번호를 유지하는지 점검합니다.",
                        "현행 계산 기준을 운영 점검표로 정리합니다.",
                    ],
                    "flow_terms": ["외화 입금", "외화 출금", "FIFO lot", "환차손익", "전표", "GL interface"],
                    "risk_terms": ["FIFO 소진 순서", "환차손익 기준", "전표-GL 연계", "취소 역분개", "정합성"],
                    "identity_anchor": "회계 처리 소스 묶음",
                },
                "interface_linkage": {
                    "report_purpose": "외부 거래 파일 수신, 인터페이스 적재, 상태 확정, 재처리 흐름을 분석하기 위한 보고서입니다.",
                    "report_scope": ["수신 적재", "상태 확정", "재처리 이력", "후속 업무 연계"],
                    "report_questions": [
                        "어떤 상태값과 파일 키로 수신 적재가 후속 업무 흐름으로 이어지는가?",
                        "확정 응답과 최신 상태본은 어떤 순서로 갱신되는가?",
                        "재처리 실패 흐름과 후속 지급 연계는 어디서 보장되는가?",
                    ],
                    "identity_sentence": "본 자산은 외부 거래 파일 수신, 인터페이스 적재, 상태 확정, 재처리, 업무 연계까지 이어지는 인터페이스 운영 소스 묶음입니다.",
                    "flow_sentence": "파일 수신 이후 임시 적재가 이뤄지고, 상태 확정과 응답 반영을 거쳐 최신 상태 갱신과 후속 업무 연계가 이어집니다.",
                    "rule_sentence": "파일 키 기준 중복 방지, 상태 전이 순서, 최신 상태 갱신, 후속 업무 연결 키 유지가 핵심입니다.",
                    "risk_sentence": "중복 적재, 응답 상태 불일치, 재처리 누락, 최신 상태 갱신 누락, 후속 업무 연계 누락 가능성을 점검해야 합니다.",
                    "primary_reason": "입력 자산이 파일 수신, staging 적재, ACK 상태 전이, retry/실패 처리, downstream 연계를 포함한 인터페이스 운영 소스이므로 현행 연계 흐름 복원이 우선입니다.",
                    "follow_up_lines": [
                        "중복 수신과 재처리 시 최신 상태가 어떻게 보정되는지 추가 확인합니다.",
                        "응답 확정과 후속 지급 연계가 같은 거래 키를 유지하는지 점검합니다.",
                        "상태 갱신 순서를 운영 점검표로 정리합니다.",
                    ],
                    "flow_terms": ["수신 적재", "상태 확정", "ACK", "재처리", "최신 상태본", "후속 지급 연계"],
                    "risk_terms": ["중복 적재", "ACK/status 불일치", "재처리 누락", "최신 상태본 누락", "후속 지급 연계 누락"],
                    "identity_anchor": "인터페이스 운영 소스 묶음",
                },
                "settlement_journal": {
                    "report_purpose": "정산 확정, 전표 헤더/라인 생성, GL 인터페이스 적재, 취소 역처리 흐름을 분석하기 위한 보고서입니다.",
                    "report_scope": ["정산 헤더/상세", "전표 헤더/라인", "GL 인터페이스", "취소·역처리"],
                    "report_questions": [
                        "정산 확정은 어떤 기준으로 전표 헤더와 라인 생성으로 이어지는가?",
                        "전표 라인과 회계 연계 reference는 어떤 거래 키로 묶이는가?",
                        "취소·역처리 시 reverse posting과 지급 상태는 어떻게 맞춰지는가?",
                    ],
                    "identity_sentence": "본 자산은 정산 확정, 전표 헤더·라인 생성, 회계 연계 적재, 취소 역처리까지 이어지는 회계 운영 소스 묶음입니다.",
                    "flow_sentence": "정산이 확정되면 전표 헤더와 라인이 생성되고, 회계 연계 적재와 취소 역처리가 같은 체인으로 이어집니다.",
                    "rule_sentence": "정산번호와 회계 기준번호 매핑, 차변·대변 균형, 회계 연계 키 일치, 취소 시 역처리 키 유지가 핵심입니다.",
                    "risk_sentence": "정산-전표 불일치, 헤더·라인 누락, 회계 연계 누락, 취소 역처리 누락, 지급 상태 미동기화 가능성을 점검해야 합니다.",
                    "primary_reason": "입력 자산이 정산 확정부터 전표/GL 반영과 취소 역처리까지 이어지는 운영 소스이므로 현행 회계 처리 체인과 정합성 점검이 우선입니다.",
                    "follow_up_lines": [
                        "취소와 역분개가 같은 정산 기준번호를 유지하는지 추가 확인합니다.",
                        "정산 확정과 전표·회계 반영이 같은 회계 기준을 따르는지 점검합니다.",
                        "현행 정산 기준을 운영 점검표로 정리합니다.",
                    ],
                    "flow_terms": ["정산 확정", "전표 헤더", "전표 라인", "회계 인터페이스", "취소 역처리"],
                    "risk_terms": ["정산-전표 불일치", "차변/대변 불균형", "GL 적재 누락", "취소 역분개", "지급 상태 미동기화"],
                    "identity_anchor": "회계 운영 소스 묶음",
                },
                "operational_source": {
                    "report_purpose": "현행 운영 로직, 데이터 흐름, 처리 순서를 분석하기 위한 보고서입니다.",
                    "report_scope": ["핵심 데이터 흐름", "후속 반영 흐름", "처리 순서", "운영 리스크"],
                    "report_questions": [
                        "어떤 저장 흐름과 후속 반영 흐름이 한 처리 체인으로 연결되는가?",
                        "데이터 반영 순서와 인터페이스 연결은 어떤 계약으로 유지되는가?",
                        "재처리·취소·정합성 위험은 어느 구간에서 발생하는가?",
                    ],
                    "identity_sentence": "본 자산은 데이터 저장, 후속 반영, 자동 처리 구간이 연결된 현행 운영 소스 묶음입니다.",
                    "flow_sentence": "데이터 반영 순서와 자동 처리 구간, 외부 연계 관계를 먼저 복원해야 합니다.",
                    "rule_sentence": "핵심 처리 순서, 상태 갱신 조건, 유지 계약을 실제 소스 기준으로 정리해야 합니다.",
                    "risk_sentence": "재처리 누락, 연계 정합성 불일치, 취소/삭제 시 역처리 누락 가능성을 점검해야 합니다.",
                    "primary_reason": "입력 자산이 실제 운영 처리와 후속 반영을 담당하는 현행 자산이므로 현재 단계에서는 현행 업무 규칙과 처리 흐름 복원이 우선입니다.",
                    "follow_up_lines": [
                        "취소, 삭제, 재처리 시 데이터 반영 순서가 유지되는지 추가 확인합니다.",
                        "후속 연계가 같은 거래 기준을 유지하는지 점검합니다.",
                        "현행 처리 기준을 운영 점검표로 정리합니다.",
                    ],
                    "flow_terms": ["데이터 흐름", "처리 순서", "트리거/프로시저 연계"],
                    "risk_terms": ["재처리 누락", "연계 정합성", "취소/삭제 역처리"],
                    "identity_anchor": "운영 소스 묶음",
                },
            }
            base = dict(mapping.get(domain, mapping["operational_source"]))
            return self._operational_question_axis_metadata(domain=domain, question_axis=question_axis, base=base)

    def _operational_question_axis_metadata(
            self,
            *,
            domain: str,
            question_axis: str,
            base: dict[str, object],
        ) -> dict[str, object]:
            axis = str(question_axis or "").strip() or "processing_flow"
            if axis == "journal_linkage":
                overrides: dict[str, dict[str, object]] = {
                    "fx_fifo": {
                        "report_purpose": "외화 입출금 결과와 전표/GL 연결 사이의 기준 불일치 가능성과 회계 영향을 진단하기 위한 보고서입니다.",
                        "report_scope": ["전표 생성 기준 불일치 가능성", "GL 연결 누락 가능성", "거래 기준번호 정합성", "취소·역처리 영향"],
                        "report_questions": [
                            "어디서 전표 생성 기준과 GL 연결 기준이 어긋날 수 있는가?",
                            "거래 기준번호가 유지되지 않으면 어떤 회계 영향이 발생하는가?",
                            "취소·역처리 시 어떤 불일치 가능성을 확인해야 하는가?",
                        ],
                        "identity_sentence": "진단 대상은 외화 입출금 결과와 전표/GL 연결 사이의 기준 일치 여부입니다.",
                        "flow_sentence": "전표 생성 기준, GL 전달 기준, 거래 기준번호 유지 여부를 진단 관점으로 확인해야 합니다.",
                        "rule_sentence": "전표 생성 기준과 회계 전달 기준이 같은 거래 기준을 유지하는지가 핵심입니다.",
                        "primary_reason": "질문 축이 전표 연계 중심이므로 현재 단계에서는 기준 불일치 가능성과 회계 영향을 먼저 진단합니다.",
                        "follow_up_lines": [
                            "전표 생성과 GL 연결이 같은 거래 기준번호를 유지하는지 추가 확인합니다.",
                            "lot 소진 결과와 환차손익이 어떤 전표 기준으로 이어지는지 점검합니다.",
                            "취소·역처리 시 같은 회계 키가 유지되는지 운영 점검표로 정리합니다.",
                        ],
                    },
                    "settlement_journal": {
                        "report_purpose": "정산 결과가 어떤 전표 기준, 회계 reference, 거래 키로 연결되는지 분석하기 위한 보고서입니다.",
                        "report_scope": ["정산 기준", "전표 생성 기준", "회계 reference", "취소·역처리 키"],
                        "report_questions": [
                            "정산 결과는 어떤 기준으로 전표 헤더·라인으로 이어지는가?",
                            "전표와 회계 reference는 어떤 거래 키로 묶이는가?",
                            "취소·역처리 시 같은 회계 기준이 어떻게 유지되는가?",
                        ],
                        "identity_sentence": "본 자산은 정산 결과가 전표 기준, 회계 reference, 거래 키로 이어지는 회계 운영 소스 묶음입니다.",
                        "flow_sentence": "정산 결과가 전표 헤더·라인 생성으로 이어지고, 같은 거래 키로 회계 reference와 취소 역처리까지 연결되는 흐름을 먼저 복원해야 합니다.",
                        "rule_sentence": "전표 생성 기준, 회계 reference 일치, 차변·대변 균형, 취소 시 같은 회계 키 유지가 핵심입니다.",
                    },
                    "operational_source": {
                        "report_purpose": "처리 결과가 어떤 전표 기준, 회계 연결, 거래 키로 이어지는지 분석하기 위한 보고서입니다.",
                        "report_scope": ["처리 결과", "전표 생성 기준", "회계 연결", "거래 기준"],
                        "report_questions": [
                            "처리 결과는 어떤 전표 기준으로 이어지는가?",
                            "전표와 회계 연결은 어떤 거래 키로 묶이는가?",
                            "취소·역처리 시 같은 기준이 어떻게 유지되는가?",
                        ],
                        "identity_sentence": "본 자산은 처리 결과가 전표 기준과 회계 연결, 거래 키로 이어지는 현행 운영 소스 묶음입니다.",
                        "flow_sentence": "처리 결과가 전표 생성 기준으로 정리되고, 같은 거래 기준으로 회계 연결까지 이어지는 흐름을 먼저 복원해야 합니다.",
                        "rule_sentence": "전표 생성 기준, 회계 전달 기준, 거래 키 일치, 취소 시 같은 기준 유지가 핵심입니다.",
                    },
                }
                updated = dict(base)
                updated.update(overrides.get(domain, overrides["operational_source"]))
                return updated
            if axis == "calculation_rule":
                overrides = {
                    "fx_fifo": {
                        "report_purpose": "외화 입출금 계산 기준 선택지를 비교해 우선 적용할 계산 규칙을 정리하기 위한 보고서입니다.",
                        "report_scope": ["계산 기준 선택지", "비교 기준", "추천안", "적용 검증 항목"],
                        "report_questions": [
                            "어떤 계산 기준을 우선 선택해야 하는가?",
                            "선택지는 어떤 기준으로 비교해야 하는가?",
                            "추천안을 적용할 때 어떤 검증 항목을 둬야 하는가?",
                        ],
                        "identity_sentence": "본 문서는 외화 입출금 계산 기준을 선택하기 위한 판단 결과입니다.",
                        "flow_sentence": "현행 FIFO 유지, 평균 기준 단순화, 거래별 지정 기준을 같은 비교 축에 놓고 판단해야 합니다.",
                        "rule_sentence": "계산 재현성, 환율 기준 일관성, 회계 연결 가능성이 핵심 비교 기준입니다.",
                        "primary_reason": "질문 축이 계산 규칙 중심이므로 현재 단계에서는 선택지, 비교 기준, 추천안을 우선 정리합니다.",
                        "follow_up_lines": [
                            "추천안은 현행 FIFO 기준 유지와 예외 검증 보강입니다.",
                            "적용 기준은 계산 재현성, 환율 기준 일관성, 회계 연결 가능성입니다.",
                            "흐름 상세와 리스크 상세는 각각 Structure, Diagnosis 문서를 참조합니다.",
                        ],
                    },
                    "operational_source": {
                        "report_purpose": "현행 처리에서 어떤 계산 기준과 상태 규칙으로 결과가 산출되는지 분석하기 위한 보고서입니다.",
                        "report_scope": ["계산 기준", "상태 조건", "산출 순서", "운영 리스크"],
                        "report_questions": [
                            "어떤 계산 기준과 상태 규칙으로 결과가 산출되는가?",
                            "계산 결과는 어떤 순서로 후속 반영과 연결되는가?",
                            "예외 처리 시 기준이 흔들릴 위험은 어디서 발생하는가?",
                        ],
                        "identity_sentence": "본 자산은 계산 기준과 상태 규칙, 후속 반영이 연결된 현행 운영 소스 묶음입니다.",
                        "flow_sentence": "핵심 기준값 계산, 상태 반영, 후속 전달 순서를 먼저 복원해야 합니다.",
                        "rule_sentence": "계산 기준, 상태 조건, 산출 순서, 예외 처리 시 같은 기준 유지가 핵심입니다.",
                    },
                }
                updated = dict(base)
                updated.update(overrides.get(domain, overrides["operational_source"]))
                return updated
            return base

    def _operational_object_inventory(
            self,
            prepared: PreparedRebuildInput,
            *,
            domain: str = "",
            question_axis: str = "",
            limit: int = 8,
        ) -> list[dict[str, str]]:
            text_parts = [
                " ".join(prepared.asset_presence.source_asset_names),
                " ".join(prepared.asset_presence.schema_asset_names),
                " ".join(prepared.asset_presence.sql_asset_names),
                prepared.assets.source_code,
                prepared.assets.database_schema,
                prepared.assets.sql_queries,
            ]
            text = "\n".join(part for part in text_parts if part)
            candidates: dict[str, dict[str, object]] = {}
            pattern_specs = (
                (r"\bcreate\s+(?:or\s+replace\s+)?table\s+((?:[A-Z_][A-Z0-9_$#]*\.)?[A-Z_][A-Z0-9_$#]*)", "table"),
                (r"\bcreate\s+(?:or\s+replace\s+)?(?:procedure|function)\s+((?:[A-Z_][A-Z0-9_$#]*\.)?[A-Z_][A-Z0-9_$#]*)", "procedure"),
                (r"\bcreate\s+(?:or\s+replace\s+)?trigger\s+((?:[A-Z_][A-Z0-9_$#]*\.)?[A-Z_][A-Z0-9_$#]*)", "trigger"),
                (r"\b(?:from|into|update|join|merge\s+into|delete\s+from)\s+((?:[A-Z_][A-Z0-9_$#]*\.)?[A-Z_][A-Z0-9_$#]*)", "table"),
                (r"\b((?:[A-Z_][A-Z0-9_$#]*\.)?[A-Z_][A-Z0-9_$#]*)\.(trg|trigger|prc|proc|pkb|pks|fnc|sql)\b", "file_hint"),
            )
            for pattern, default_kind in pattern_specs:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    raw_name = str(match.group(1) or "").strip()
                    kind = default_kind
                    if default_kind == "file_hint":
                        ext = str(match.group(2) or "").strip().lower()
                        kind = "trigger" if ext in {"trg", "trigger"} else "procedure" if ext in {"prc", "proc", "pkb", "pks", "fnc"} else "table"
                    name = self._normalize_operational_object_name(raw_name)
                    if not name or self._is_ignored_operational_object_name(name):
                        continue
                    current = candidates.get(name)
                    kind_priority = self._operational_object_kind_priority(kind)
                    if current is None or kind_priority > int(current.get("kind_priority") or 0):
                        candidates[name] = {
                            "name": name,
                            "kind": kind,
                            "kind_priority": kind_priority,
                            "score": self._operational_object_rank(domain, name, kind, question_axis=question_axis),
                        }
            ordered = sorted(
                candidates.values(),
                key=lambda item: (
                    -int(item.get("score") or 0),
                    -int(item.get("kind_priority") or 0),
                    str(item.get("name") or ""),
                ),
            )
            inventory: list[dict[str, str]] = []
            for item in ordered[:limit]:
                name = str(item.get("name") or "").strip()
                kind = str(item.get("kind") or "").strip() or "table"
                if not name:
                    continue
                inventory.append(
                    {
                        "name": name,
                        "display_name": self._operational_object_display_name(domain=domain, name=name, kind=kind),
                        "kind": kind,
                        "description": self._operational_object_description(domain=domain, name=name, kind=kind, question_axis=question_axis),
                    }
                )
            return inventory

    def _operational_object_section_intro(
            self,
            domain: str,
            inventory: list[dict[str, str]],
            *,
            question_axis: str = "",
        ) -> str:
            count = len(inventory[:5])
            axis = str(question_axis or "").strip()
            if axis == "journal_linkage":
                if domain == "fx_fifo":
                    return f"핵심 데이터 흐름은 lot 계산 결과, 전표 생성 기준, GL 연결, 거래 기준번호 유지로 이어지며 관련 핵심 대상은 {count}개입니다."
                if domain == "settlement_journal":
                    return f"핵심 데이터 흐름은 정산 결과, 전표 기준, 회계 reference, 취소 역처리 키 유지로 이어지며 관련 핵심 대상은 {count}개입니다."
                return f"핵심 데이터 흐름은 처리 결과, 전표 생성 기준, 회계 연결, 거래 기준 유지로 이어지며 관련 핵심 대상은 {count}개입니다."
            if axis == "calculation_rule":
                if domain == "fx_fifo":
                    return f"핵심 데이터 흐름은 입금 잔량 유지, 선입선출 lot 소진, 환율 비교, 손익 산출로 이어지며 관련 핵심 대상은 {count}개입니다."
                return f"핵심 데이터 흐름은 기준값 계산, 상태 반영, 산출 순서로 이어지며 관련 핵심 대상은 {count}개입니다."
            if domain == "fx_fifo":
                return f"핵심 데이터 흐름은 외화 입금, 선입선출 lot 소진, 환차손익 계산, 회계 반영으로 이어지며 관련 핵심 대상은 {count}개입니다."
            if domain == "interface_linkage":
                return f"핵심 데이터 흐름은 파일 수신, 상태 확정, 재처리, 후속 업무 연계로 이어지며 관련 핵심 대상은 {count}개입니다."
            if domain == "settlement_journal":
                return f"핵심 데이터 흐름은 정산 확정, 전표 반영, 회계 연계, 취소 역처리로 이어지며 관련 핵심 대상은 {count}개입니다."
            return f"핵심 데이터 흐름은 저장, 자동 반영, 후속 연계 순서로 이어지며 관련 핵심 대상은 {count}개입니다."

    def _operational_object_section_lines(self, inventory: list[dict[str, str]]) -> list[str]:
            lines: list[str] = []
            for item in inventory[:5]:
                name = str(item.get("display_name") or item.get("name") or "").strip()
                description = str(item.get("description") or "").strip()
                if not name or not description:
                    continue
                lines.append(f"{name}: {description}")
            return lines

    def _operational_object_display_name(self, *, domain: str, name: str, kind: str) -> str:
            upper_name = str(name or "").upper()
            domain_specific: dict[str, dict[str, str]] = {
                "fx_fifo": {
                    "TN_FORINS": "외화 입금 lot 원장",
                    "TN_FOROUT": "외화 출금 요청",
                    "TN_FOROUD": "lot 소진 결과 이력",
                    "TN_BKCHIT": "전표 라인 반영 이력",
                    "GL_INTERFACE": "회계 인터페이스 적재 대상",
                    "P_FOROUT": "출금 lot 소진 절차",
                    "P_BKCHNO": "전표 기준번호 생성 절차",
                },
                "interface_linkage": {
                    "IB_BULK_TRAN_ADD": "거래 파일 수신 적재",
                    "P_FUNDIH": "수신 데이터 반영 절차",
                    "IB_ACCTALL_TR_DD_ADD": "상태 응답 적재 이력",
                    "IB_ACCTALL_TR_DD_LST": "최신 상태 스냅샷",
                    "TN_PAY_ORDER_DTL": "후속 지급 연계 상태",
                },
                "settlement_journal": {
                    "TN_SETTLE_HDR": "정산 헤더",
                    "TN_SETTLE_DTL": "정산 상세",
                    "TN_BKCHNO": "전표 헤더",
                    "TN_BKCHIT": "전표 라인",
                    "GL_INTERFACE": "회계 인터페이스 적재 대상",
                    "TN_PAY_ORDER_DTL": "지급 상태 연계",
                },
            }
            display = domain_specific.get(domain, {}).get(upper_name)
            if display:
                return display
            if "GL_INTERFACE" in upper_name:
                return "회계 인터페이스 적재 대상"
            if "FORINS" in upper_name:
                return "외화 입금 lot 원장"
            if "FOROUT" in upper_name and kind == "procedure":
                return "외화 출금 반영 절차"
            if "FOROUT" in upper_name:
                return "외화 출금 요청"
            if "FOROUD" in upper_name:
                return "lot 소진 결과 이력"
            if "BKCHNO" in upper_name:
                return "전표 헤더"
            if "BKCHIT" in upper_name:
                return "전표 라인"
            if "SETTLE_HDR" in upper_name:
                return "정산 헤더"
            if "SETTLE_DTL" in upper_name:
                return "정산 상세"
            if "PAY_ORDER" in upper_name:
                return "후속 지급 연계 상태"
            if "IB_BULK" in upper_name:
                return "거래 파일 수신 적재"
            if "IB_" in upper_name and "LST" in upper_name:
                return "최신 상태 스냅샷"
            if "IB_" in upper_name:
                return "인터페이스 수신 적재"
            if kind == "procedure":
                return "핵심 처리 절차"
            if kind == "trigger":
                return "후속 반영 트리거"
            return "핵심 데이터 저장 객체"

    def _operational_token_display_map(
            self,
            *,
            domain: str,
            inventory: list[dict[str, str]] | None = None,
        ) -> dict[str, str]:
            mapping: dict[str, str] = {}
            for item in list(inventory or []):
                raw_name = self._normalize_operational_object_name(str(item.get("name") or ""))
                display_name = str(item.get("display_name") or item.get("name") or "").strip()
                if raw_name and display_name:
                    mapping[raw_name] = display_name
            domain_specific = {
                "fx_fifo": {
                    "TN_FORINS": "외화 입금 lot 원장",
                    "TN_FOROUT": "외화 출금 요청",
                    "TN_FOROUD": "lot 소진 결과 이력",
                    "TN_BKCHIT": "전표 라인 반영 이력",
                    "P_FOROUT": "외화 출금 반영 절차",
                    "P_BKCHNO": "전표 기준번호 생성 절차",
                    "RMN_FAMT": "입금 lot 외화 잔량",
                    "RMN_AMT": "입금 lot 원화 잔량",
                    "GAP_AMT": "환차손익",
                    "OUT_AMT0": "출금 기준 금액",
                    "OUTF_AMT": "출금 외화 금액",
                    "EXCH_RATE": "환율",
                    "TR_DATE": "거래일자",
                    "TR_DT": "거래일자",
                    "TR_DATE_SEQ": "거래 순번",
                    "ACCT_SEQ": "계좌 식별값",
                    "MNEY_UNIT": "통화 코드",
                    "REFERENCE4": "전표 기준번호",
                    "REFERENCE6": "전표 상세 순번",
                    "USER_JE_CATEGORY_NAME": "전표 분류",
                    "CURRENCY_CODE": "통화 코드",
                    "ENTERED_DR": "차변 금액",
                    "ENTERED_CR": "대변 금액",
                },
                "interface_linkage": {
                    "IB_BULK_TRAN_ADD": "거래 파일 수신 적재",
                    "P_FUNDIH": "수신 데이터 반영 절차",
                    "IB_ACCTALL_TR_DD_ADD": "상태 응답 적재 이력",
                    "IB_ACCTALL_TR_DD_LST": "최신 상태 스냅샷",
                    "TN_PAY_ORDER_DTL": "후속 지급 연계 상태",
                    "TN_IF_RETRY_HIS": "재처리 이력",
                    "ACK": "응답 확정",
                    "ERP_RCV_FLAG": "응답 수신 상태",
                    "PAY_ORDER": "후속 지급 연계",
                    "STATUS_CD": "상태 코드",
                    "STATUS_DT": "상태 일자",
                    "TRX_NO": "거래 번호",
                    "TRX_DT": "거래 일자",
                },
                "settlement_journal": {
                    "TN_SETTLE_HDR": "정산 헤더",
                    "TN_SETTLE_DTL": "정산 상세",
                    "TN_BKCHNO": "전표 헤더",
                    "TN_BKCHIT": "전표 라인",
                    "TN_PAY_ORDER_DTL": "지급 상태 연계",
                    "SETTLE_NO": "정산 번호",
                    "BKCHNO": "전표 번호",
                    "BKCHIT": "전표 라인",
                    "REFERENCE4": "회계 기준번호",
                    "REFERENCE6": "회계 상세 순번",
                    "ENTERED_DR": "차변 금액",
                    "ENTERED_CR": "대변 금액",
                },
            }
            for raw_name, display_name in domain_specific.get(domain, {}).items():
                mapping.setdefault(raw_name, display_name)
            mapping.setdefault("GL_INTERFACE", "회계 인터페이스")
            return mapping

    def _operational_humanize_line(
            self,
            text: str,
            *,
            domain: str,
            inventory: list[dict[str, str]] | None = None,
        ) -> str:
            normalized = str(text or "").strip()
            if not normalized:
                return ""
            normalized = re.sub(r"\b[A-Z][A-Z0-9$#]*\.", "", normalized)
            replacements = self._operational_token_display_map(domain=domain, inventory=inventory)
            for raw_name, display_name in sorted(replacements.items(), key=lambda item: (-len(item[0]), item[0])):
                normalized = re.sub(rf"\b{re.escape(raw_name)}\b", display_name, normalized, flags=re.IGNORECASE)
            phrase_replacements = (
                (r"\bRMN_FAMT\s*/\s*RMN_AMT\b", "입금 lot 잔량"),
                (r"\bTR_DATE\s*,\s*TR_DATE_SEQ\b", "거래일자와 순번"),
                (r"\bTR_DT\s*,\s*TRX_NO\b", "거래 일자와 거래 번호"),
                (r"\bTRIGGER\b", "후속 반영"),
                (r"\bPROCEDURE\b", "처리 절차"),
            )
            for pattern, replacement in phrase_replacements:
                normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
            generic_token_patterns = (
                (r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*AMT[A-Z0-9$#]*\b", "금액"),
                (r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*(?:DT|DATE)[A-Z0-9$#]*\b", "일자"),
                (r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*(?:NO|NUM|SEQ)[A-Z0-9$#]*\b", "번호"),
                (r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*(?:CD|CODE)[A-Z0-9$#]*\b", "코드"),
                (r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*(?:YN|FLAG)[A-Z0-9$#]*\b", "여부/표시값"),
                (r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*STATUS[A-Z0-9$#]*\b", "상태"),
                (r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*RATE[A-Z0-9$#]*\b", "비율"),
                (r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*(?:KEY|REF|ID)[A-Z0-9$#]*\b", "식별 기준"),
            )
            for pattern, replacement in generic_token_patterns:
                normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
            structural_replacements = (
                (r"SQL\s*또는\s*데이터\s*접근\s*로직이\s*UI[^\.\n]*", "데이터 반영 흐름과 계산 기준이 한 단계에 모여 있어 처리 순서를 먼저 복원해야 합니다"),
                (r"데이터\s*접근\s*로직이\s*UI[^\.\n]*", "데이터 반영 흐름과 계산 기준이 한 단계에 모여 있어 처리 순서를 먼저 복원해야 합니다"),
                (r"\bSQL\b", "현행 처리"),
                (r"\bTABLE\b", "데이터 흐름"),
                (r"\bPROCEDURE\b", "처리 단계"),
                (r"\bTRIGGER\b", "후속 반영 단계"),
                (r"\bCOLUMN\b", "입력 기준"),
                (r"데이터\s*접근", "데이터 반영"),
                (r"\bUI\b", "화면"),
                (r"UI/템플릿", "화면"),
                (r"재설계", "후속 검토"),
                (r"계층\s*분리", "처리 단계 정리"),
                (r"서비스\s*분리", "처리 단계 정리"),
                (r"분리\s*구조", "흐름 정리"),
                (r"레이어", "단계"),
            )
            for pattern, replacement in structural_replacements:
                normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
            normalized = re.sub(r"\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bMERGE\b|\bJOIN\b|\bFROM\b|\bWHERE\b", "", normalized, flags=re.IGNORECASE)
            normalized = re.sub(r"\s+/\s+", "/", normalized)
            normalized = re.sub(r"\s+,", ",", normalized)
            normalized = re.sub(r"\(\s*", "(", normalized)
            normalized = re.sub(r"\s*\)", ")", normalized)
            normalized = re.sub(r"\s{2,}", " ", normalized)
            return normalized.strip(" ,;")

    # 객체명은 테이블/프로시저/트리거뿐 아니라 컬럼명과 SQL 구문처럼 보이는 기술 토큰까지 포함해 다룹니다.
    def operational_text_exposes_technical_token(
            self,
            text: str,
            *,
            extra_tokens: list[str] | tuple[str, ...] | None = None,
        ) -> bool:
            normalized = str(text or "")
            if not normalized.strip():
                return False
            upper_text = normalized.upper()
            normalized_tokens = [
                self._normalize_operational_object_name(item)
                for item in list(extra_tokens or [])
                if self._normalize_operational_object_name(item)
            ]
            if normalized_tokens and any(token in upper_text for token in normalized_tokens):
                return True
            token_patterns = (
                r"\b[A-Z][A-Z0-9$#]*\.[A-Z_][A-Z0-9_$#]+\b",
                r"\.[A-Z_][A-Z0-9_$#]+\b",
                r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9_$#]+\b",
                r"\b(?:TN|TB|TR|IB|GL|P|PKG|PK|PROC|PRC|FN|FNC|SP|VW|IDX|SEQ)_[A-Z0-9_$#]+\b",
                r"\b[A-Z][A-Z0-9$#]*_[A-Z0-9$#]*(?:AMT|SEQ|ID|CD|CODE|YN|FLAG|STATUS|RATE|DATE|DT|NO|NUM|QTY|CNT|KEY|REF)[A-Z0-9$#]*\b",
                r"\b(?:SELECT|INSERT|UPDATE|DELETE|MERGE|JOIN|FROM|WHERE|GROUP\s+BY|ORDER\s+BY)\b",
                r"\b(?:SQL|TABLE|PROCEDURE|TRIGGER|COLUMN)\b",
                r"\bUI\b",
                r"데이터\s*접근",
                r"(?:테이블|프로시저|트리거|컬럼)",
            )
            return any(re.search(pattern, upper_text) for pattern in token_patterns)

    def _operational_default_section_lines(
            self,
            *,
            section_key: str,
            profile: dict[str, object],
        ) -> list[str]:
            identity_sentence = str(profile.get("identity_sentence") or "").strip()
            flow_sentence = str(profile.get("flow_sentence") or "").strip()
            rule_sentence = str(profile.get("rule_sentence") or "").strip()
            risk_sentence = str(profile.get("risk_sentence") or "").strip()
            primary_reason = str(profile.get("primary_reason") or "").strip()
            follow_up_lines = [str(item).strip() for item in list(profile.get("follow_up_lines") or []) if str(item).strip()]
            if section_key == "report_purpose":
                report_purpose = str(profile.get("report_purpose") or "").strip()
                return [report_purpose] if report_purpose else []
            if section_key == "one_line_conclusion":
                if identity_sentence:
                    return [f"{identity_sentence.rstrip('.')} 1차 목적은 현행 데이터 흐름과 계산 기준, 처리 순서를 복원하는 것입니다."]
                return []
            if section_key == "executive_summary_v2":
                return [
                    line
                    for line in (
                        f"현행 분석: {identity_sentence}" if identity_sentence else "",
                        f"핵심 흐름: {flow_sentence}" if flow_sentence else "",
                        f"주요 업무 규칙: {rule_sentence}" if rule_sentence else "",
                        f"운영 리스크: {risk_sentence}" if risk_sentence else "",
                    )
                    if line
                ]
            if section_key in {"primary_judgment_reason", "rationale"}:
                return [primary_reason] if primary_reason else []
            if section_key in {"recommended_option", "recommended_directions", "next_step"}:
                return follow_up_lines[:3]
            if section_key in {"risks", "risk"}:
                return [risk_sentence] if risk_sentence else []
            return []

    def operational_lines_expose_technical_tokens(
            self,
            lines: list[str] | tuple[str, ...],
            *,
            extra_tokens: list[str] | tuple[str, ...] | None = None,
        ) -> bool:
            return any(
                self.operational_text_exposes_technical_token(str(line or ""), extra_tokens=extra_tokens)
                for line in list(lines or [])
            )

    def operational_text_exposes_forbidden_surface_phrase(self, text: str) -> bool:
            normalized = str(text or "").strip().lower()
            if not normalized:
                return False
            patterns = (
                "분리 구조",
                "분리",
                "계층 분리",
                "계층으로 분리",
                "재설계",
                "재구성 로드맵",
                "서비스 분리",
                "서비스로 분리",
                "정책 계층",
                "모듈형",
                "옵션",
                "구조 개선",
            )
            return any(pattern in normalized for pattern in patterns)

    def operational_section_level(self, section_key: str) -> str:
            normalized = str(section_key or "").strip()
            if normalized in {"analysis_summary", "evidence"}:
                return "l2"
            if normalized in {
                "report_purpose",
                "one_line_conclusion",
                "one_line_summary",
                "executive_summary",
                "executive_summary_v2",
                "primary_judgment_reason",
                "rationale",
                "recommended_option",
                "recommended_directions",
                "execution_plan",
                "related_contracts",
                "next_step",
                "risks",
                "risk",
            }:
                return "l1"
            return "l3"

    def render_operational_section_lines(
            self,
            *,
            section_key: str,
            lines: list[str] | tuple[str, ...] | None = None,
            prepared: PreparedRebuildInput | None = None,
            domain_override: str = "",
            fallback_lines: list[str] | tuple[str, ...] | None = None,
        ) -> list[str]:
            level = self.operational_section_level(section_key)
            normalized_lines = [str(line or "").strip() for line in list(lines or []) if str(line or "").strip()]
            normalized_fallback = [str(line or "").strip() for line in list(fallback_lines or []) if str(line or "").strip()]
            profile = self.operational_analysis_profile(prepared) if prepared is not None else {}
            domain = str(profile.get("domain") or domain_override or "").strip()
            inventory = list(profile.get("object_inventory") or [])
            raw_object_tokens = [
                str(item.get("name") or "").strip()
                for item in inventory
                if str(item.get("name") or "").strip()
            ]
            if level == "l2" and prepared is not None:
                intro = str(profile.get("object_section_intro") or "").strip()
                object_lines = [str(item).strip() for item in list(profile.get("object_section_lines") or []) if str(item).strip()]
                return [item for item in [intro, *object_lines] if item]
            candidate_lines = normalized_lines or normalized_fallback
            fallback_candidate_lines = normalized_fallback if normalized_fallback and normalized_fallback != candidate_lines else []
            default_lines = self._operational_default_section_lines(section_key=section_key, profile=profile)
            if level == "l1":
                candidate_lines = [
                    self._operational_humanize_line(line, domain=domain, inventory=inventory)
                    for line in candidate_lines
                ]
                candidate_lines = [line for line in candidate_lines if line]
                fallback_candidate_lines = [
                    self._operational_humanize_line(line, domain=domain, inventory=inventory)
                    for line in fallback_candidate_lines
                ]
                fallback_candidate_lines = [line for line in fallback_candidate_lines if line]
                filtered = [
                    line
                    for line in candidate_lines
                    if not self.operational_text_exposes_technical_token(line, extra_tokens=raw_object_tokens)
                    and not self.operational_text_exposes_forbidden_surface_phrase(line)
                ]
                if filtered:
                    return filtered
                if fallback_candidate_lines:
                    fallback_filtered = [
                        line
                        for line in fallback_candidate_lines
                        if not self.operational_text_exposes_technical_token(line, extra_tokens=raw_object_tokens)
                        and not self.operational_text_exposes_forbidden_surface_phrase(line)
                    ]
                    if fallback_filtered:
                        return fallback_filtered
                if default_lines:
                    default_filtered = [
                        line
                        for line in default_lines
                        if not self.operational_text_exposes_technical_token(line, extra_tokens=raw_object_tokens)
                        and not self.operational_text_exposes_forbidden_surface_phrase(line)
                    ]
                    if default_filtered:
                        return default_filtered
                return filtered
            if level == "l2":
                filtered = [
                    line
                    for line in candidate_lines
                    if not self.operational_text_exposes_technical_token(line, extra_tokens=raw_object_tokens)
                ]
                if filtered:
                    return filtered
                if fallback_candidate_lines:
                    fallback_filtered = [
                        line
                        for line in fallback_candidate_lines
                        if not self.operational_text_exposes_technical_token(line, extra_tokens=raw_object_tokens)
                    ]
                    if fallback_filtered:
                        return fallback_filtered
                return candidate_lines
            return candidate_lines

    def _operational_object_names(self, prepared: PreparedRebuildInput, limit: int = 6) -> list[str]:
            domain = "operational_source"
            if self._has_fx_fifo_domain(prepared):
                domain = "fx_fifo"
            elif self._has_interface_linkage_domain(prepared) and self._interface_linkage_signal_score(prepared) >= self._settlement_journal_signal_score(prepared):
                domain = "interface_linkage"
            elif self._has_settlement_journal_domain(prepared):
                domain = "settlement_journal"
            return [
                str(item.get("name") or "").strip()
                for item in self._operational_object_inventory(prepared, domain=domain, limit=limit)
                if str(item.get("name") or "").strip()
            ]

    def _normalize_operational_object_name(self, value: str) -> str:
            normalized = str(value or "").strip().upper()
            if not normalized:
                return ""
            if "." in normalized:
                normalized = normalized.split(".")[-1]
            normalized = re.sub(r"[^A-Z0-9_$#]", "", normalized)
            return normalized

    def _is_ignored_operational_object_name(self, name: str) -> bool:
            ignored = {
                "CREATE",
                "TABLE",
                "PROCEDURE",
                "FUNCTION",
                "TRIGGER",
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "FROM",
                "INTO",
                "JOIN",
                "WHERE",
                "MERGE",
                "VALUES",
                "SET",
                "WHEN",
                "THEN",
                "BEGIN",
                "END",
                "DUAL",
            }
            return not name or len(name) < 3 or name in ignored

    def _operational_object_kind_priority(self, kind: str) -> int:
            return {"table": 3, "procedure": 2, "trigger": 1}.get(str(kind or "").strip(), 0)

    def _operational_object_rank(self, domain: str, name: str, kind: str, *, question_axis: str = "") -> int:
            score = self._operational_object_kind_priority(kind) * 10
            domain_priority: dict[str, tuple[tuple[str, ...], ...]] = {
                "fx_fifo": (
                    ("FORINS",),
                    ("FOROUT",),
                    ("FOROUD",),
                    ("BKCHIT",),
                    ("GL_INTERFACE",),
                    ("BKCHNO",),
                ),
                "interface_linkage": (
                    ("IB_BULK_TRAN_ADD",),
                    ("P_FUNDIH",),
                    ("IB_ACCTALL_TR_DD_LST",),
                    ("TN_PAY_ORDER_DTL",),
                    ("IB_",),
                    ("PAY_ORDER",),
                ),
                "settlement_journal": (
                    ("TN_SETTLE_HDR",),
                    ("TN_SETTLE_DTL",),
                    ("TN_BKCHNO",),
                    ("TN_BKCHIT",),
                    ("GL_INTERFACE",),
                    ("TN_PAY_ORDER_DTL",),
                ),
            }
            priorities = domain_priority.get(domain, ())
            for index, tokens in enumerate(priorities):
                if any(token in name for token in tokens):
                    score += 100 - (index * 8)
                    break
            if "GL_INTERFACE" in name:
                score += 20
            if "PAY_ORDER" in name:
                score += 12
            if kind == "table":
                score += 4
            axis = str(question_axis or "").strip()
            axis_priority: dict[str, tuple[tuple[str, ...], ...]] = {
                "journal_linkage": (
                    ("BKCHNO", "JE", "JOURNAL"),
                    ("BKCHIT", "ENTRY", "LINE"),
                    ("GL_INTERFACE", "GL", "LEDGER"),
                    ("FOROUD", "SETTLE_DTL"),
                ),
                "calculation_rule": (
                    ("FORINS", "RMN", "BAL"),
                    ("FOROUT", "OUT", "REQ"),
                    ("FOROUD", "GAP", "LOSS", "RATE"),
                    ("SETTLE_DTL", "AMT", "CALC"),
                ),
                "processing_flow": (
                    ("FORINS", "SETTLE_HDR", "IB_"),
                    ("FOROUT", "SETTLE_DTL", "P_"),
                    ("FOROUD", "BKCHIT", "GL_INTERFACE"),
                ),
            }
            for index, tokens in enumerate(axis_priority.get(axis, ())):
                if any(token in name for token in tokens):
                    score += 70 - (index * 9)
                    break
            return score

    def _operational_object_description(self, *, domain: str, name: str, kind: str, question_axis: str = "") -> str:
            upper_name = str(name or "").upper()
            axis = str(question_axis or "").strip()
            if axis == "journal_linkage":
                journal_specific: dict[str, dict[str, str]] = {
                    "fx_fifo": {
                        "TN_FOROUD": "lot 소진 결과와 환차손익이 어떤 전표 기준으로 넘어가는지 남깁니다.",
                        "TN_BKCHIT": "lot 계산 결과가 어떤 전표 라인으로 이어지는지 보여 줍니다.",
                        "GL_INTERFACE": "전표 결과가 어떤 거래 기준번호로 회계 연계에 전달되는지 보여 줍니다.",
                        "P_BKCHNO": "전표 기준번호를 만들고 계산 결과를 회계 연계 기준과 묶습니다.",
                    },
                    "settlement_journal": {
                        "TN_SETTLE_HDR": "정산 결과가 어떤 전표 기준으로 이어지는지 출발 기준을 잡습니다.",
                        "TN_BKCHNO": "정산 결과를 어떤 전표 헤더 기준으로 묶는지 보여 줍니다.",
                        "TN_BKCHIT": "전표 라인과 회계 reference가 어떤 거래 키로 연결되는지 남깁니다.",
                        "GL_INTERFACE": "전표 결과가 어떤 회계 기준으로 외부 연계에 전달되는지 보여 줍니다.",
                    },
                }
                description = journal_specific.get(domain, {}).get(upper_name)
                if description:
                    return description
            if axis == "calculation_rule":
                calculation_specific: dict[str, dict[str, str]] = {
                    "fx_fifo": {
                        "TN_FORINS": "입금 lot의 잔량과 취득 기준을 유지해 계산의 시작점을 잡습니다.",
                        "TN_FOROUT": "출금 금액이 어떤 lot 소진 기준으로 계산되는지 출발 기준을 잡습니다.",
                        "TN_FOROUD": "lot 소진량과 손익 산출 결과를 계산 기준대로 남깁니다.",
                        "P_FOROUT": "lot 선택 순서와 환율 비교, 손익 산출 단계를 이어 줍니다.",
                    },
                }
                description = calculation_specific.get(domain, {}).get(upper_name)
                if description:
                    return description
            domain_specific: dict[str, dict[str, str]] = {
                "fx_fifo": {
                    "TN_FORINS": "입금 금액과 남은 잔량의 출발 기준을 관리합니다.",
                    "TN_FOROUT": "출금 요청 금액과 소진 대상 선택의 출발 기준을 잡습니다.",
                    "TN_FOROUD": "어떤 lot이 얼마만큼 소진됐는지와 계산 결과를 남깁니다.",
                    "TN_BKCHIT": "계산 결과가 전표 반영으로 이어진 흔적을 남깁니다.",
                    "GL_INTERFACE": "계산 결과가 회계 반영으로 넘어가기 전 최종 전달 기준을 모읍니다.",
                    "P_FOROUT": "출금 요청에서 lot 소진 순서와 금액 계산을 이어 줍니다.",
                    "P_BKCHNO": "전표 기준번호를 만들고 회계 반영 순서를 이어 줍니다.",
                },
                "interface_linkage": {
                    "IB_BULK_TRAN_ADD": "수신된 거래가 첫 적재 단계에서 어떤 상태로 들어오는지 잡습니다.",
                    "P_FUNDIH": "수신 데이터가 상태 갱신과 후속 반영으로 이어지게 합니다.",
                    "IB_ACCTALL_TR_DD_LST": "최신 상태가 무엇인지와 마지막 확정 결과를 유지합니다.",
                    "TN_PAY_ORDER_DTL": "후속 지급 단계와 연결되는 처리 상태를 관리합니다.",
                },
                "settlement_journal": {
                    "TN_SETTLE_HDR": "정산 확정의 출발 기준과 전체 상태를 관리합니다.",
                    "TN_SETTLE_DTL": "거래별 정산 기준과 세부 반영 대상을 남깁니다.",
                    "TN_BKCHNO": "정산 결과가 어떤 전표 단위로 이어지는지 잡습니다.",
                    "TN_BKCHIT": "전표별 반영 금액과 처리 결과를 남깁니다.",
                    "GL_INTERFACE": "전표 결과가 회계 반영 단계로 넘어가기 전 전달 기준을 모읍니다.",
                    "TN_PAY_ORDER_DTL": "지급 상태와 정산 반영 결과의 연결 상태를 관리합니다.",
                },
            }
            description = domain_specific.get(domain, {}).get(upper_name)
            if description:
                return description
            if "GL_INTERFACE" in upper_name:
                return "외부 회계 반영으로 넘어가기 전 전달 기준을 모읍니다."
            if any(token in upper_name for token in ("BKCHNO", "HDR", "HEAD")):
                return "상위 단위 상태와 기준번호 흐름을 관리합니다."
            if any(token in upper_name for token in ("BKCHIT", "DTL", "LINE", "IT")):
                return "세부 반영 결과와 금액 흐름을 남깁니다."
            if any(token in upper_name for token in ("HIST", "LST", "LOG")):
                return "이력과 최신 상태 변화를 이어서 보여 줍니다."
            if "PAY_ORDER" in upper_name:
                return "후속 지급 또는 주문 연계 상태를 이어 줍니다."
            if kind == "trigger":
                return "상태 변화 뒤 이어지는 후속 반영을 자동으로 이어 줍니다."
            if kind == "procedure":
                return "처리 순서와 계산·연계 단계를 이어 줍니다."
            return "핵심 데이터와 처리 상태를 같은 거래 흐름 기준으로 관리합니다."
    
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
            if self._has_fx_fifo_domain(prepared):
                return 0
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
                for token in ("manager", "director", "team_lead", "auditor")
                if re.search(rf"""["']{re.escape(token)}["']""", text)
            }
            if role_literals:
                count += 1
            if len(role_literals) >= 2:
                count += 1
            return count
    
    def _workflow_stage_signal_count(self, prepared: PreparedRebuildInput) -> int:
            if self._has_fx_fifo_domain(prepared):
                return 0
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
            if self._has_fx_fifo_domain(prepared):
                return 0
            text = self._workflow_signal_text(prepared)
            groups = [
                ("approve(", ".approve(", "approved", "\"approved\"", "'approved'", "승인", "auto_approved", "자동 승인"),
                ("reject", "rejected", "반려"),
                ("delegate", "delegated", "대리 승인", "위임"),
                ("escalation", "escalate"),
            ]
            return sum(1 for tokens in groups if any(token in text for token in tokens))

    def _workflow_progression_signal_count(self, prepared: PreparedRebuildInput) -> int:
            if self._has_fx_fifo_domain(prepared):
                return 0
            text = self._workflow_signal_text(prepared)
            groups = [
                ("requested", "submitted", "request_status"),
                ("approvalstep", "approval_step", "approvallevel", "approval_level", "getnextstep", "nextstep"),
                ("delegate", "delegated", "pending_delegate_assignment"),
                ("reject", "rejected"),
            ]
            return sum(1 for tokens in groups if any(token in text for token in tokens))

    def _has_workflow_pattern(self, prepared: PreparedRebuildInput) -> bool:
            if self._has_fx_fifo_domain(prepared):
                return False
            actor_count = self._workflow_actor_signal_count(prepared)
            stage_count = self._workflow_stage_signal_count(prepared)
            gate_count = self._workflow_gate_signal_count(prepared)
            progression_count = self._workflow_progression_signal_count(prepared)
            total_strength = actor_count + stage_count + gate_count + progression_count
            return (
                actor_count >= 1
                and progression_count >= 1
                and total_strength >= 3
                and (stage_count >= 1 or gate_count >= 1)
            )
    
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
            profile = self.operational_analysis_profile(prepared)
            if bool(profile.get("active")):
                fallback_lines = [str(item).strip() for item in list(profile.get("follow_up_lines") or []) if str(item).strip()]
                if not fallback_lines:
                    fallback_lines = [
                        "취소와 재처리 시 현행 처리 순서가 유지되는지 추가 확인합니다.",
                        "후속 연계가 같은 거래 기준을 유지하는지 점검합니다.",
                        "현행 처리 기준을 운영 점검표로 정리합니다.",
                    ]
                rendered = self.render_operational_section_lines(
                    section_key="recommended_directions",
                    prepared=prepared,
                    lines=fallback_lines,
                    fallback_lines=fallback_lines,
                )
                return rendered or fallback_lines
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
                    getattr(prepared, "selected_narrative_judgment", "") or getattr(prepared, "selected_primary_judgment", "")
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
            if self._has_fx_fifo_domain(prepared):
                return "외화 입출금 FIFO"
            text = " ".join(
                [
                    " ".join(prepared.asset_presence.source_asset_names),
                    " ".join(prepared.asset_presence.ui_asset_names),
                    " ".join(prepared.asset_presence.schema_asset_names),
                    " ".join(prepared.asset_presence.sql_asset_names),
                    " ".join(prepared.asset_presence.doc_asset_names),
                    prepared.assets.source_code,
                    prepared.assets.ui_template,
                    prepared.assets.sql_queries,
                    prepared.assets.database_schema,
                    prepared.supporting_docs,
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
            document_terms = self._document_domain_terms(prepared)
            if document_terms:
                return document_terms[0]
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
            if self._has_fx_fifo_domain(prepared):
                return False
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
            if self._has_fx_fifo_domain(prepared):
                return False
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
            if self._has_fx_fifo_domain(prepared):
                return "validation"
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
            if self._has_fx_fifo_domain(prepared):
                return (
                    f"{self._attach_object_particle(self._option_label(recommended.name))} 우선안으로 두고 "
                    "현행 lot, 환차손익, 전표/GL 연계 기준을 복원한 뒤 후속 구조 개선 후보로 비교하는 편이 적절합니다."
                )
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
            if "lot" in label.lower() or "fifo" in label.lower() or "gl" in label.lower():
                return f"{label}는 일부 구조 분리에는 유효하지만 FIFO 계산과 회계 연계를 함께 묶는 현재 우선순위보다 뒤에 두어야 합니다."
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
            if self._has_fx_fifo_domain(prepared):
                evidence_pool = [evidence for rule in grounded_rules[:3] for evidence in rule.evidence][:3]
                objects = self._operational_object_names(prepared)
                lot_anchor = ", ".join(objects[:3]) if objects else "TN_FORINS, TN_FOROUT, TN_FOROUD"
                return [
                    DecisionItem(
                        statement=f"{concept} 자산에서 {lot_anchor} 기준의 입금 lot 적재와 FIFO 소진 순서를 먼저 복원해야 합니다.",
                        rationale="입금 lot 잔량과 출금 lot 소진 순서를 먼저 확인해야 동일 거래의 원가 계산과 lot 추적 근거를 설명할 수 있습니다.",
                        linked_evidence=evidence_pool,
                    ),
                    DecisionItem(
                        statement=f"{concept} 자산에서 EXCH_RATE, OUT_AMT0, GAP_AMT 기준의 환차손익 계산 경로를 확인해야 합니다.",
                        rationale="lot별 취득 환율과 출금 환율 비교 기준을 복원해야 환차손익과 출금 금액 연결 관계를 검증할 수 있습니다.",
                        linked_evidence=evidence_pool,
                    ),
                    DecisionItem(
                        statement=f"{concept} 자산에서 TN_BKCHIT, GL_INTERFACE 적재와 거래 기준번호 연계를 확인해야 합니다.",
                        rationale="전표와 GL 반영 기준번호가 어떤 계산 결과를 따라가는지 확인해야 회계 반영 누락과 재처리 오류 위험을 점검할 수 있습니다.",
                        linked_evidence=evidence_pool,
                    ),
                ]
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
            if self._has_fx_fifo_domain(prepared):
                linked_rules = [rule.title for rule in grounded_rules[:3]]
                linked_contracts = [item.item for item in retained_contracts[:2]]
                return [
                    PrioritySplitItem(
                        priority=1,
                        item=f"{concept} 기능에서 입금 lot 원장과 출금 lot 소진 순서를 먼저 복원하는 것이 필요합니다.",
                        title=f"{concept} 현행 lot 흐름 복원",
                        reason="FIFO lot 잔량과 소진 순서를 먼저 복원해야 출금 원가와 lot 추적 결과의 현재 기준을 설명할 수 있습니다.",
                        impact_scope="입금 lot 원장, 출금 소진 이력, FIFO 소진 기준",
                        prerequisite="핵심 lot 객체 식별",
                        linked_rules=linked_rules,
                        linked_contracts=linked_contracts,
                    ),
                    PrioritySplitItem(
                        priority=2,
                        item=f"{concept} 기능에서 환차손익 계산 기준과 GAP_AMT 반영 흐름을 다음 단계로 점검하는 것이 필요합니다.",
                        title=f"{concept} 환차손익 경로 점검",
                        reason="lot별 취득 환율과 출금 환율 비교 기준을 확인해야 환차손익 결과와 출금 금액 연결을 설명할 수 있습니다.",
                        impact_scope="환차손익 계산, 출금 금액, 계산 예외 처리",
                        prerequisite="FIFO lot 소진 기준 복원",
                        linked_rules=linked_rules,
                        linked_contracts=linked_contracts,
                    ),
                    PrioritySplitItem(
                        priority=3,
                        item=f"{concept} 기능의 전표 생성, GL 반영, 취소·재처리 정합성을 마지막에 점검하는 것이 필요합니다.",
                        title=f"{concept} 전표·GL 정합성 점검",
                        reason="lot 계산과 환차손익 흐름이 확인된 뒤 전표와 GL 인터페이스 연계를 점검해야 운영 누락 위험을 줄일 수 있습니다.",
                        impact_scope="전표 생성, GL_INTERFACE 적재, 역분개·정합성 검토",
                        prerequisite="환차손익 계산 기준 확인",
                        linked_rules=linked_rules,
                        linked_contracts=linked_contracts,
                    ),
                ]
            if self._uses_document_neutral_template_fallback(prepared, applied_templates):
                focus_terms = self._document_focus_terms(prepared)
                primary_focus = focus_terms[0]
                comparison_focus = focus_terms[1] if len(focus_terms) > 1 else "판단 기준"
                return [
                    PrioritySplitItem(
                        priority=1,
                        item=f"{primary_focus} 관련 현행 구조와 핵심 용어를 먼저 정리하는 것이 필요합니다.",
                        title=f"{primary_focus} 현행 구조 정리",
                        reason="문서형 입력에서는 현행 구조와 핵심 용어를 먼저 고정해야 후속 비교와 계획이 흔들리지 않습니다.",
                        impact_scope="현행 구조, 핵심 용어, source 근거 정리",
                        prerequisite="핵심 source block 확인",
                        linked_rules=[rule.title for rule in grounded_rules[:2]],
                        linked_contracts=[item.item for item in retained_contracts[:1]],
                    ),
                    PrioritySplitItem(
                        priority=2,
                        item=f"{comparison_focus} 관련 비교 기준과 판단 축을 다음 단계로 정리하는 것이 필요합니다.",
                        title=f"{comparison_focus} 비교 기준 정리",
                        reason="비교 기준과 판단 축을 분리해야 결론을 먼저 강제하지 않고 선택지를 정리할 수 있습니다.",
                        impact_scope="선택지 비교, 판단 기준, 누락 정보 정리",
                        prerequisite="현행 구조 정리",
                        linked_rules=[rule.title for rule in grounded_rules[:2]],
                        linked_contracts=[item.item for item in retained_contracts[:1]],
                    ),
                    PrioritySplitItem(
                        priority=3,
                        item="누락 정보와 단계별 실행 후보를 마지막에 정리하는 것이 필요합니다.",
                        title="누락 정보 및 로드맵 정리",
                        reason="구조와 기준을 먼저 정리한 뒤 실행 후보를 정리해야 후속 계획이 source와 어긋나지 않습니다.",
                        impact_scope="누락 정보, 후속 확인 항목, 단계별 계획",
                        prerequisite="비교 기준 정리",
                        linked_rules=[rule.title for rule in grounded_rules[:2]],
                        linked_contracts=[item.item for item in retained_contracts[:1]],
                    ),
                ]
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
            if self._has_fx_fifo_domain(prepared):
                return [
                    DesignOption(
                        name="옵션 A. FIFO 계산·회계 연계 분리 구조",
                        structure_summary="입금 lot 원장, 출금 lot 소진 계산, 환차손익 계산, 전표/GL 반영을 순차 서비스로 분리합니다.",
                        advantages=["FIFO lot 계산과 환차손익 기준을 같은 계산 흐름으로 고정할 수 있습니다.", "전표 생성과 GL 연계를 계산 결과와 같은 거래 키로 연결하기 쉽습니다."],
                        risks=["lot 식별 키가 약하면 계산 계층과 회계 계층 사이에서 재정렬 비용이 생길 수 있습니다."],
                        difficulty="MEDIUM",
                        duration_weeks=4,
                        recommended=True,
                        selection_reason="",
                    ),
                    DesignOption(
                        name="옵션 B. lot 원장 우선 분리 구조",
                        structure_summary="입금 lot 잔량과 출금 lot 소진 이력을 먼저 분리하고 환차손익/전표는 후속 단계에서 연결합니다.",
                        advantages=["FIFO 원장 경계를 빠르게 고정할 수 있습니다."],
                        risks=["환차손익과 전표 반영 기준이 뒤로 밀리면 회계 정합성 확인이 늦어질 수 있습니다."],
                        difficulty="MEDIUM",
                        duration_weeks=5,
                        recommended=False,
                        selection_reason="",
                    ),
                    DesignOption(
                        name="옵션 C. GL 연계 우선 구조",
                        structure_summary="전표 생성과 GL 인터페이스를 먼저 정리하고 FIFO lot 계산과 환차손익 정교화는 후속 단계로 넘깁니다.",
                        advantages=["회계 인터페이스 정합성을 빠르게 정리할 수 있습니다."],
                        risks=["핵심 FIFO lot 계산이 레거시에 남아 재작업 가능성이 큽니다."],
                        difficulty="MEDIUM",
                        duration_weeks=5,
                        recommended=False,
                        selection_reason="",
                    ),
                ]
            if self._uses_document_neutral_template_fallback(prepared, applied_templates):
                focus_terms = self._document_focus_terms(prepared)
                primary_focus = focus_terms[0]
                secondary_focus = focus_terms[1] if len(focus_terms) > 1 else "판단 기준"
                return [
                    DesignOption(
                        name="옵션 A. 현행 구조 정리 중심 구조",
                        structure_summary=f"{primary_focus}와 {secondary_focus}를 기준으로 현행 구조, 핵심 용어, 비교 축을 먼저 정리하는 구조입니다.",
                        advantages=["source에서 직접 확인된 용어와 구조를 먼저 고정할 수 있습니다.", "도메인 불확실성을 남긴 채 비교 기준을 정리하기 쉽습니다."],
                        risks=["세부 구현 방식은 후속 근거 없이 확정하지 못합니다."],
                        difficulty="MEDIUM",
                        duration_weeks=4,
                        recommended=True,
                        selection_reason="",
                    ),
                    DesignOption(
                        name="옵션 B. 비교 기준 분리 구조",
                        structure_summary=f"{primary_focus} 관련 선택지와 판단 기준을 먼저 분리하고 상세 설계는 후속 단계에서 정리하는 구조입니다.",
                        advantages=["선택지 비교와 기준 정리를 빠르게 진행할 수 있습니다."],
                        risks=["현행 상세 구조를 충분히 보지 못하면 후속 설계 재조정이 필요할 수 있습니다."],
                        difficulty="MEDIUM",
                        duration_weeks=5,
                        recommended=False,
                        selection_reason="",
                    ),
                    DesignOption(
                        name="옵션 C. 추가 근거 확인 후 상세 설계 구조",
                        structure_summary="핵심 구조와 누락 정보를 먼저 수집한 뒤 상세 설계를 단계적으로 정리하는 구조입니다.",
                        advantages=["source 근거가 약한 영역을 별도 확인 항목으로 남기기 쉽습니다."],
                        risks=["초기 설계 속도는 상대적으로 느릴 수 있습니다."],
                        difficulty="MEDIUM",
                        duration_weeks=5,
                        recommended=False,
                        selection_reason="",
                    ),
                ]
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
            if self._has_fx_fifo_domain(prepared):
                related_rules = [rule.title for rule in grounded_rules[:3]]
                related_contracts = self.render_operational_section_lines(
                    section_key="related_contracts",
                    prepared=prepared,
                    lines=[item.item for item in retained_contracts[:3]],
                    fallback_lines=[
                        "입금 lot 잔량 계산 계약은 유지하는 것이 필요합니다.",
                        "출금 lot 소진 순서 계약은 유지하는 것이 필요합니다.",
                        "환차손익과 회계 인터페이스 반영 계약은 유지하는 것이 필요합니다.",
                    ],
                )
                stage_lines = [
                    (
                        "1주차",
                        "현행 입금 lot 원장과 출금 lot 소진 흐름을 복원합니다.",
                        [
                            "TN_FORINS, TN_FOROUT, TN_FOROUD 기준으로 입금 lot 잔량과 출금 소진 흐름을 표로 정리합니다.",
                            "lot 잔량(RMN_FAMT/RMN_AMT)과 FIFO 소진 순서(TR_DATE, TR_DATE_SEQ)의 현행 기준을 정리합니다.",
                        ],
                        [
                            "현행 입금 lot 원장과 출금 lot 소진 흐름을 복원합니다.",
                            "외화 입금 lot 원장, 외화 출금 요청, lot 소진 결과 이력 기준으로 입금 lot 잔량과 출금 소진 흐름을 표로 정리합니다.",
                            "입금 lot 잔량과 FIFO 소진 순서의 현행 기준을 정리합니다.",
                        ],
                        ["lot 원장 구조도", "FIFO 소진 규칙 표", "핵심 객체 목록"],
                        ["컨설턴트", "업무 분석가", "백엔드 아키텍트"],
                    ),
                    (
                        "2주차",
                        "환차손익 계산과 전표·GL 연계 규칙을 분석합니다.",
                        [
                            "lot별 취득 환율, 출금 환율, GAP_AMT 계산 기준을 현행 로직 기준으로 정리합니다.",
                            "전표 생성과 GL_INTERFACE 적재 기준번호가 어떤 거래 키를 따르는지 연결 관계를 확인합니다.",
                        ],
                        [
                            "환차손익 계산과 전표·회계 인터페이스 연계 규칙을 분석합니다.",
                            "lot별 취득 환율, 출금 환율, 환차손익 계산 기준을 현행 로직 기준으로 정리합니다.",
                            "전표 생성과 회계 인터페이스 적재 기준번호가 어떤 거래 키를 따르는지 연결 관계를 확인합니다.",
                        ],
                        ["환차손익 계산 명세", "전표/GL 연계 명세", "거래 키 매핑 규칙"],
                        ["백엔드 아키텍트", "시니어 개발자"],
                    ),
                    (
                        "3주차",
                        f"{concept} 취소·재처리·정합성 점검 포인트를 정리합니다.",
                        [
                            "FIFO lot 선택, lot 잔량 차감, GAP_AMT 계산에서 재처리 시점과 누락 가능 지점을 확인합니다.",
                            "TN_BKCHIT/GL_INTERFACE 반영, 취소, 삭제, 역분개 연계 여부를 점검 항목으로 정리합니다.",
                        ],
                        [
                            f"{concept} 취소·재처리·정합성 점검 포인트를 정리합니다.",
                            "FIFO lot 선택, lot 잔량 차감, 환차손익 계산에서 재처리 시점과 누락 가능 지점을 확인합니다.",
                            "전표 라인 반영 이력과 회계 인터페이스 반영, 취소, 삭제, 역분개 연계 여부를 점검 항목으로 정리합니다.",
                        ],
                        ["정합성 점검표", "회계 연계 테스트 케이스", "운영 리스크 목록"],
                        ["백엔드 개발자", "QA"],
                    ),
                    (
                        "4주차",
                        f"현행 분석 이후 {option_name} 등 개선 후보를 후속 검토안으로 정리합니다.",
                        [
                            "lot 소진 상세, 환차손익 결과, 전표 반영 결과가 같은 거래 기준번호로 연결되는지 검증합니다.",
                            "트리거 책임 축소, 계산 로직 분리, 회귀 테스트 고정 방안을 개선 후보로 정리합니다.",
                        ],
                        [
                            f"현행 분석 이후 {option_name} 등 개선 후보를 후속 검토안으로 정리합니다.",
                            "lot 소진 상세, 환차손익 결과, 전표 반영 결과가 같은 거래 기준번호로 연결되는지 검증합니다.",
                            "후속 반영 책임 축소, 계산 로직 분리, 회귀 테스트 고정 방안을 개선 후보로 정리합니다.",
                        ],
                        ["정합성 체크리스트", "회귀 검증 결과", "개선 후보 목록"],
                        ["백엔드 개발자", "QA", "회계 담당자"],
                    ),
                ]
                rendered_plan: list[ExecutionPlanWeek] = []
                for week_label, goal, tasks, fallback_lines, deliverables, roles in stage_lines:
                    rendered_lines = self.render_operational_section_lines(
                        section_key="execution_plan",
                        prepared=prepared,
                        lines=[goal, *tasks],
                        fallback_lines=fallback_lines,
                    )
                    rendered_goal = str(rendered_lines[0] if rendered_lines else fallback_lines[0]).strip()
                    rendered_tasks = [str(item).strip() for item in rendered_lines[1:] if str(item).strip()] or list(fallback_lines[1:])
                    rendered_plan.append(
                        ExecutionPlanWeek(
                            week_label=week_label,
                            goal=rendered_goal,
                            tasks=rendered_tasks,
                            related_rules=related_rules,
                            related_contracts=related_contracts,
                            roles=roles,
                            duration_weeks=1,
                            deliverables=deliverables,
                        )
                    )
                return rendered_plan
            if self._uses_document_neutral_template_fallback(prepared, applied_templates):
                focus_terms = self._document_focus_terms(prepared)
                primary_focus = focus_terms[0]
                secondary_focus = focus_terms[1] if len(focus_terms) > 1 else "판단 기준"
                linked_rules = [rule.title for rule in grounded_rules[:3]]
                linked_contracts = [item.item for item in retained_contracts[:2]]
                return [
                    ExecutionPlanWeek(
                        week_label="1주차",
                        goal=f"{primary_focus} 관련 현행 구조와 핵심 용어를 정리합니다.",
                        tasks=[
                            "safe source 기준으로 핵심 용어와 구조 단위를 목록화합니다.",
                            "슬라이드/문서별 핵심 근거와 반복 표현을 정리합니다.",
                            "직접 확인된 구조와 확인이 필요한 구조를 구분합니다.",
                        ],
                        related_rules=linked_rules,
                        related_contracts=linked_contracts,
                        roles=["컨설턴트", "업무 분석가"],
                        duration_weeks=1,
                        deliverables=["현행 구조 목록", "핵심 용어 표", "source 근거 목록"],
                    ),
                    ExecutionPlanWeek(
                        week_label="2주차",
                        goal=f"{secondary_focus} 관련 비교 기준과 판단 축을 정리합니다.",
                        tasks=[
                            "선택지 비교에 필요한 판단 기준과 제약을 정리합니다.",
                            "문서에서 직접 확인된 개선 방향과 누락 정보를 분리합니다.",
                        ],
                        related_rules=linked_rules,
                        related_contracts=linked_contracts,
                        roles=["컨설턴트", "아키텍트"],
                        duration_weeks=1,
                        deliverables=["판단 기준 표", "선택지 비교 초안", "누락 정보 목록"],
                    ),
                    ExecutionPlanWeek(
                        week_label="3주차",
                        goal="선택지와 후속 확인 항목을 구조 기준으로 정리합니다.",
                        tasks=[
                            "현행 구조와 개선 방향 사이의 차이를 선택지 단위로 정리합니다.",
                            "추가 확인이 필요한 항목을 missing information으로 분리합니다.",
                        ],
                        related_rules=linked_rules,
                        related_contracts=linked_contracts,
                        roles=["업무 분석가", "백엔드 아키텍트"],
                        duration_weeks=1,
                        deliverables=["선택지 정리표", "후속 확인 항목", "리스크 메모"],
                    ),
                    ExecutionPlanWeek(
                        week_label="4주차",
                        goal=f"{option_name} 기준의 단계별 실행 로드맵을 정리합니다.",
                        tasks=[
                            "단기 실행 항목과 후속 설계 항목을 분리합니다.",
                            "source 근거가 약한 영역은 보류 또는 추가 확인 대상으로 남깁니다.",
                        ],
                        related_rules=linked_rules,
                        related_contracts=linked_contracts,
                        roles=["컨설턴트", "프로젝트 리드"],
                        duration_weeks=1,
                        deliverables=["단계별 로드맵", "우선순위 목록", "보류 항목 정리"],
                    ),
                ]
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
            if self._has_fx_fifo_domain(prepared):
                risks = [
                    "FIFO lot 소진 순서가 바뀌면 동일 출금 건의 원가와 lot 추적 결과가 달라질 수 있습니다.",
                    "GAP_AMT 계산 기준이 흔들리면 환차손익과 전표 금액이 서로 어긋날 수 있습니다.",
                    "전표 생성과 GL_INTERFACE 반영 기준번호가 분리되면 회계 연계 누락이 발생할 수 있습니다.",
                ]
                if prepared.missing_context:
                    risks.append("입력 자산이 제한적이므로 제안은 설계 초안 수준이며 추가 파일 확인이 필요합니다.")
                return self._dedupe_list(risks)[:4]
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
            if self._has_fx_fifo_domain(prepared):
                for item, keywords, basis in (
                    (
                        "입금 lot 잔량(RMN_FAMT/RMN_AMT) 계산 계약은 유지하는 것이 필요합니다.",
                        ("tn_forins", "rmn_famt", "rmn_amt", "acnt_seq"),
                        "입금 lot 잔량이 바뀌면 FIFO 출금 순서와 잔량 계산 결과가 달라질 수 있습니다.",
                    ),
                    (
                        "출금 lot 소진 순서(TR_DATE, TR_DATE_SEQ 기준 FIFO) 계약은 유지하는 것이 필요합니다.",
                        ("tn_forout", "tn_foroud", "tr_date", "tr_date_seq", "tr_date_seq0", "order by"),
                        "lot 소진 순서가 달라지면 동일 출금 건의 원가와 환차손익 결과가 달라질 수 있습니다.",
                    ),
                    (
                        "환차손익(GAP_AMT) 계산 및 전표/GL_INTERFACE 반영 계약은 유지하는 것이 필요합니다.",
                        ("gap_amt", "gl_interface", "reference4", "reference6", "user_je_category_name"),
                        "환차손익 계산과 전표 반영 기준이 바뀌면 회계 결과와 GL 연계 흐름이 달라질 수 있습니다.",
                    ),
                ):
                    built = self._contract_spec(item=item, keywords=keywords, basis=basis, seen=seen)
                    if built:
                        specs.append(built)
                return [item for item in specs if item]
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
            if self._has_fx_fifo_domain(prepared):
                return ["validation", "amount_threshold"]
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
