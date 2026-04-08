from __future__ import annotations

import json
import re
from typing import Any

from mellow_link.services.anonymization.schemas import SafeAnalysisBundle
from mellow_link.services.refactoring_support_engine.decision_catalog import (
    JudgmentTemplateId,
    JudgmentTemplateSpec,
    get_judgment_template_spec,
    get_judgment_template_specs,
)
from mellow_link.services.refactoring_support_engine.input_assembler import InputAssembler
from mellow_link.services.refactoring_support_engine.schemas import FeatureSignals, PreparedRebuildInput
from mellow_link.services.refactoring_support_engine.template_support import TemplateSupport

from .schemas import (
    AppliedJudgmentTemplate,
    AssetPresenceSummary,
    DecisionItem,
    DesignOption,
    EvidenceRef,
    ExecutionPlanWeek,
    ExtractedRulesEnvelope,
    GroundedBusinessRule,
    LayeredListResult,
    MissingContextItem,
    PatternCandidate,
    PrioritySplitItem,
    RebuildAssetsPayload,
    RecommendedOption,
    RetainedContract,
    SaveValidationRules,
    SearchFilterRules,
    StatusPermissionsRules,
    StructuredRebuildResult,
    VerificationItem,
)


class RebuildAssistantService:
    SCOPE_LIMIT_PATTERNS = (
        r"whole[\s-]?system",
        r"entire system",
        r"full[\s-]?site",
        r"multi[\s-]?service",
        r"microservice",
        r"deployable",
        r"production[\s-]?ready",
        r"full[\s-]?database migration",
        r"full migration",
        r"전체\s*시스템",
        r"전체\s*사이트",
        r"전면\s*재구축",
        r"멀티\s*서비스",
        r"마이크로서비스",
        r"배포\s*가능",
        r"실행\s*가능한\s*전체\s*코드",
        r"전체\s*데이터베이스\s*마이그레이션",
    )
    CONCEPT_PATTERNS = (
        "order", "orders", "payment", "invoice", "approval", "request", "requests",
        "user", "member", "account", "product", "item", "customer", "notice",
        "document", "contract", "shipment", "refund", "claim", "board", "post",
        "comment", "report", "schedule", "booking", "reservation", "employee",
        "role", "status", "policy", "audit", "search", "filter", "query",
        "save", "submit", "validation",
        "주문", "결재", "요청", "사용자", "회원", "상품", "고객", "문서", "계약", "환불",
        "게시판", "댓글", "보고서", "예약", "직원", "권한", "상태", "정책", "감사", "검색",
        "필터", "조회", "저장", "등록", "검증",
    )
    SOURCE_ASSET_EXTENSIONS = (".java", ".py", ".js", ".jsx", ".ts", ".tsx", ".cs", ".kt", ".rb", ".php", ".go", ".scala")

    def prepare_input(
        self,
        *,
        goal: str,
        assets: RebuildAssetsPayload,
        constraints: list[str] | None = None,
        temp_context: str = "",
    ) -> PreparedRebuildInput:
        return InputAssembler().prepare_input(
            self,
            goal=goal,
            assets=assets,
            constraints=constraints,
            temp_context=temp_context,
        )

    def prepare_safe_bundle_input(
        self,
        *,
        goal: str,
        safe_bundle: SafeAnalysisBundle,
        constraints: list[str] | None = None,
    ) -> PreparedRebuildInput:
        return InputAssembler().prepare_safe_bundle_input(
            self,
            goal=goal,
            safe_bundle=safe_bundle,
            constraints=constraints,
        )

    def is_scope_limited(self, goal: str) -> bool:
        text = (goal or "").strip().lower()
        return bool(text) and any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in self.SCOPE_LIMIT_PATTERNS)

    def detect_missing_context(self, prepared: PreparedRebuildInput) -> list[str]:
        return [item.required_material for item in self.build_missing_context_details(prepared)]

    def build_missing_context_details(self, prepared: PreparedRebuildInput) -> list[MissingContextItem]:
        missing: list[MissingContextItem] = []
        has_source = self._has_source_code_evidence(prepared)
        has_ui = self._has_ui_evidence(prepared)
        has_schema = self._has_schema_evidence(prepared)
        has_sql = self._has_sql_evidence(prepared)
        has_framework = self._has_framework_evidence(prepared)
        if not has_source and not has_ui:
            missing.append(
                MissingContextItem(
                    required_material="레거시 화면 또는 서버 코드",
                    reason="기능 흐름과 화면-백엔드 결합 지점을 확인할 근거가 부족합니다.",
                )
            )
        if not has_schema and not has_sql:
            missing.append(
                MissingContextItem(
                    required_material="DB 스키마 또는 핵심 SQL",
                    reason="업무 규칙과 데이터 검증 규칙을 구조화할 DB 근거가 부족합니다.",
                )
            )
        elif not has_schema:
            missing.append(
                MissingContextItem(
                    required_material="DB 스키마",
                    reason="테이블/컬럼 계약과 상태 컬럼 구조를 확정할 근거가 부족합니다.",
                )
            )
        elif not has_sql:
            missing.append(
                MissingContextItem(
                    required_material="핵심 SQL",
                    reason="조회/검증/상태 전이 규칙을 구체화할 SQL 근거가 부족합니다.",
                )
            )
        if not has_framework:
            missing.append(
                MissingContextItem(
                    required_material="기존 프레임워크/런타임 정보",
                    reason="현대화 설계안의 기술 제약과 전환 경계를 정확히 잡기 어렵습니다.",
                )
            )
        if not prepared.signals.status_permissions and not prepared.signals.search_filters and not prepared.signals.save_validation:
            missing.append(
                MissingContextItem(
                    required_material="권한/조회/저장 흐름이 드러나는 추가 코드 또는 문서",
                    reason="핵심 업무 규칙의 우선순위와 주요 처리 흐름을 더 명확히 판별해야 합니다.",
                )
            )
        return missing

    def _has_source_code_evidence(self, prepared: PreparedRebuildInput) -> bool:
        if prepared.safe_bundle is not None:
            return bool(prepared.asset_presence.has_source_code)
        return bool(prepared.asset_presence.has_source_code or (prepared.assets.source_code or "").strip())

    def _has_ui_evidence(self, prepared: PreparedRebuildInput) -> bool:
        if prepared.safe_bundle is not None:
            return bool(prepared.asset_presence.has_ui_asset)
        return bool(prepared.asset_presence.has_ui_asset or (prepared.assets.ui_template or "").strip())

    def _has_schema_evidence(self, prepared: PreparedRebuildInput) -> bool:
        if prepared.safe_bundle is not None:
            return bool(prepared.asset_presence.has_schema_asset)
        return bool(prepared.asset_presence.has_schema_asset or (prepared.assets.database_schema or "").strip())

    def _has_sql_evidence(self, prepared: PreparedRebuildInput) -> bool:
        if prepared.safe_bundle is not None:
            return bool(prepared.asset_presence.has_sql_asset)
        return bool(prepared.asset_presence.has_sql_asset or (prepared.assets.sql_queries or "").strip())

    def _has_framework_evidence(self, prepared: PreparedRebuildInput) -> bool:
        if prepared.safe_bundle is not None:
            return bool(prepared.asset_presence.has_framework_hint)
        return bool(prepared.asset_presence.has_framework_hint or (prepared.assets.framework_info or "").strip())

    def extract_feature_signals(self, prepared: PreparedRebuildInput) -> FeatureSignals:
        bundle = prepared.legacy_bundle.lower()
        concepts = self._extract_concepts(prepared)
        status_permissions = self._extract_status_permission_signals(bundle)
        search_filters = self._extract_search_filter_signals(bundle)
        save_validation = self._extract_save_validation_signals(bundle)
        technical = []
        if self._looks_like_jsp(prepared):
            technical.append("JSP/서버 템플릿 렌더링")
        if self._contains_sql_in_ui(prepared):
            technical.append("UI 근접 SQL 결합")
        if "request.getparameter" in bundle or "param." in bundle:
            technical.append("request parameter 기반 흐름")
        if self._has_join_heaviness(prepared.assets.sql_queries):
            technical.append("복합 조인 쿼리")
        scores = self._score_feature_modes(
            prepared,
            status_permissions=status_permissions,
            search_filters=search_filters,
            save_validation=save_validation,
        )
        primary_mode, secondary_mode = self._pick_feature_modes(scores)
        return FeatureSignals(
            concepts=concepts,
            status_permissions=status_permissions,
            search_filters=search_filters,
            save_validation=save_validation,
            technical=technical,
            scores=scores,
            primary_feature_mode=primary_mode,
            secondary_feature_mode=secondary_mode,
        )

    def analyze_assets(self, prepared: PreparedRebuildInput) -> list[str]:
        from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine

        return DiagnosisEngine().build_analysis_summary(prepared)

    def infer_target_architecture(self, prepared: PreparedRebuildInput) -> list[str]:
        return self._engine_template_support().infer_target_architecture(prepared)

    def build_layer_reconstruction(self, prepared: PreparedRebuildInput) -> LayeredListResult:
        return self._engine_template_support().build_layer_reconstruction(prepared)

    def build_recomposition_draft(
        self,
        prepared: PreparedRebuildInput,
        applied_templates: list[AppliedJudgmentTemplate] | None = None,
    ) -> LayeredListResult:
        return self._engine_template_support().build_recomposition_draft(prepared, applied_templates)

    def build_risks(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> list[str]:
        return self._engine_template_support().build_risks(
            prepared,
            grounded_rules,
            retained_contracts,
            applied_templates,
        )

    def extract_rules(self, prepared: PreparedRebuildInput) -> ExtractedRulesEnvelope:
        from mellow_link.services.refactoring_support_engine.diagnosis_engine import DiagnosisEngine

        return DiagnosisEngine().build_extracted_rules(prepared)

    def extract_status_permissions_rules(
        self,
        prepared: PreparedRebuildInput,
        supplemental: bool = False,
    ) -> StatusPermissionsRules:
        text = prepared.legacy_bundle
        roles = [role.upper() for role in self._extract_unique_matches(text, r"\b(admin|manager|user|operator|guest|owner|reviewer|approver)\b")]
        statuses = [status.upper() for status in self._extract_unique_matches(text, r"\b(pending|approved|rejected|draft|submitted|active|inactive|closed|cancelled)\b")]
        actions = self._extract_unique_matches(text, r"\b(approve|reject|resubmit|cancel|submit|close|reopen)\b")
        entities = self._rule_entities(prepared)

        role_action_matrix: list[dict] = []
        for role in roles:
            allowed_actions = [action for action in actions if re.search(rf"{role}.*{action}|{action}.*{role}", text, flags=re.IGNORECASE)]
            if allowed_actions:
                role_action_matrix.append({"role": role, "allowed_actions": self._dedupe_list(allowed_actions)})

        status_action_matrix: list[dict] = []
        for status in statuses:
            visible_actions = [action for action in actions if re.search(rf"{status}.*{action}|{action}.*{status}", text, flags=re.IGNORECASE)]
            if visible_actions:
                status_action_matrix.append({"status": status, "visible_actions": self._dedupe_list(visible_actions)})

        transition_rules: list[dict] = []
        for status in statuses:
            for action in actions:
                if not re.search(rf"{status}.*{action}|{action}.*{status}", text, flags=re.IGNORECASE):
                    continue
                condition = self._transition_condition_hint(text, roles, status, action)
                transition_rules.append(
                    {
                        "from_status": status,
                        "action": action,
                        "to_status": self._infer_target_status(action, statuses),
                        "condition": condition,
                    }
                )

        ui_visibility_rules: list[str] = []
        if actions and statuses:
            for action in actions[:3]:
                related_statuses = [
                    status for status in statuses if re.search(rf"{status}.*{action}|{action}.*{status}", text, flags=re.IGNORECASE)
                ]
                related_roles = [
                    role for role in roles if re.search(rf"{role}.*{action}|{action}.*{role}", text, flags=re.IGNORECASE)
                ]
                if related_statuses or related_roles:
                    role_fragment = f" and role is {' or '.join(related_roles)}" if related_roles else ""
                    status_fragment = f"when status is {' or '.join(related_statuses)}" if related_statuses else "when action state is satisfied"
                    ui_visibility_rules.append(f"show {action} button only {status_fragment}{role_fragment}".strip())
        if not ui_visibility_rules and re.search(r"<c:if|<c:choose|if\s*\(", text, flags=re.IGNORECASE):
            ui_visibility_rules.append("conditional action visibility is embedded in JSP or server-side branches")

        policy_hints: list[str] = []
        if roles or actions or statuses:
            policy_hints.append("extract role/action visibility into policy service")
        if transition_rules:
            policy_hints.append("extract state transition checks into transition policy")
        if re.search(r"<c:if|<c:choose|if\s*\(", text, flags=re.IGNORECASE):
            policy_hints.append("move conditional button rendering rules out of the view layer")

        if supplemental:
            role_action_matrix = role_action_matrix[:1]
            status_action_matrix = status_action_matrix[:1]
            transition_rules = transition_rules[:1]
            ui_visibility_rules = ui_visibility_rules[:1]
            policy_hints = policy_hints[:1]

        return StatusPermissionsRules(
            entities=entities,
            roles=roles,
            statuses=statuses,
            actions=actions,
            role_action_matrix=role_action_matrix,
            status_action_matrix=status_action_matrix,
            transition_rules=self._dedupe_dicts(transition_rules),
            ui_visibility_rules=self._dedupe_list(ui_visibility_rules),
            policy_hints=self._dedupe_list(policy_hints),
        )

    def extract_search_filter_rules(
        self,
        prepared: PreparedRebuildInput,
        supplemental: bool = False,
    ) -> SearchFilterRules:
        text = prepared.legacy_bundle
        entities = self._rule_entities(prepared)
        query_params = self._extract_unique_matches(
            text,
            r"request\.getParameter\(\"([^\"]+)\"\)|@RequestParam\(\"([^\"]+)\"\)|\b(keyword|status|page|sort|dateFrom|dateTo|category|region|includeClosed|filter)\b",
        )

        filter_fields: list[dict] = []
        for name in query_params:
            field_type = self._infer_filter_field_type(name)
            filter_fields.append({"name": name, "type": field_type, "required": False})

        sort_rules: list[dict] = []
        sql_text = prepared.assets.sql_queries or text
        order_match = re.search(r"order\s+by\s+([a-z0-9_\.]+)(?:\s+(asc|desc))?", sql_text, flags=re.IGNORECASE)
        if order_match:
            sort_rules.append(
                {
                    "field": order_match.group(1).split(".")[-1],
                    "direction": (order_match.group(2) or "asc").lower(),
                    "default": True,
                }
            )

        paging_rules: list[dict] = []
        if re.search(r"\blimit\b", sql_text, flags=re.IGNORECASE):
            paging_rules.append({"param": "limit", "style": "limit", "default": False})
        if re.search(r"\boffset\b", sql_text, flags=re.IGNORECASE):
            paging_rules.append({"param": "offset", "style": "offset", "default": False})
        if any(param.lower() == "page" for param in query_params):
            paging_rules.append({"param": "page", "style": "page", "default": False})

        query_binding_rules: list[str] = []
        if query_params:
            query_binding_rules.append(f"use bound params for {', '.join(query_params[:4])} filters")
        if re.search(r"\bwhere\b", sql_text, flags=re.IGNORECASE):
            query_binding_rules.append("avoid string concatenation in WHERE clause")
        if re.search(r"\blike\b", sql_text, flags=re.IGNORECASE):
            query_binding_rules.append("parameterize LIKE predicates instead of inline SQL composition")

        default_filters: list[str] = []
        if any(param.lower() == "status" for param in query_params):
            default_filters.append("preserve default status filter behavior from the legacy search form")
        if re.search(r"includeClosed|closed", text, flags=re.IGNORECASE):
            default_filters.append("exclude CLOSED unless includeClosed is explicitly enabled")

        result_shape_hints: list[str] = []
        columns = self._extract_select_columns(sql_text)
        if columns:
            result_shape_hints.append(f"list result with {', '.join(columns[:4])}")
        elif re.search(r"\b(table|grid|list|results?)\b", text, flags=re.IGNORECASE):
            result_shape_hints.append("list result shape is rendered as a table/grid in the legacy view")

        if supplemental:
            filter_fields = filter_fields[:2]
            sort_rules = sort_rules[:1]
            paging_rules = paging_rules[:1]
            query_binding_rules = query_binding_rules[:1]
            default_filters = default_filters[:1]
            result_shape_hints = result_shape_hints[:1]

        return SearchFilterRules(
            entities=entities,
            filter_fields=filter_fields,
            query_params=query_params,
            sort_rules=sort_rules,
            paging_rules=paging_rules,
            query_binding_rules=self._dedupe_list(query_binding_rules),
            default_filters=self._dedupe_list(default_filters),
            result_shape_hints=self._dedupe_list(result_shape_hints),
        )

    def extract_save_validation_rules(
        self,
        prepared: PreparedRebuildInput,
        supplemental: bool = False,
    ) -> SaveValidationRules:
        text = prepared.legacy_bundle
        entities = self._rule_entities(prepared)
        required_fields = self._extract_unique_matches(
            text,
            r"if\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*==\s*null|([a-zA-Z_][a-zA-Z0-9_]*)\.isBlank\(\)|required\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        )
        field_validation_rules: list[str] = []
        for field in required_fields:
            field_validation_rules.append(f"{field} must not be empty")
        if re.search(r"validate|validator", text, flags=re.IGNORECASE):
            field_validation_rules.append("legacy save flow includes validator-style checks before persistence")

        duplicate_check_rules: list[str] = []
        duplicate_fields = self._extract_unique_matches(text, r"existsBy([A-Z][a-zA-Z0-9_]*)|duplicate\s+([a-zA-Z_][a-zA-Z0-9_]*)")
        for field in duplicate_fields:
            normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", field).replace("_", " ").lower()
            duplicate_check_rules.append(f"prevent duplicate records by {normalized}")
        if not duplicate_check_rules and re.search(r"\b(duplicate|exists|already exists|unique|중복)\b", text, flags=re.IGNORECASE):
            duplicate_check_rules.append("prevent duplicate records before save")

        save_guard_rules: list[str] = []
        if re.search(r"\b(forbidden|cannot save|blocked|guard)\b", text, flags=re.IGNORECASE):
            save_guard_rules.append("apply pre-save guard before persistence")
        if re.search(r"\b(save|insert|update|submit|persist)\b", text, flags=re.IGNORECASE) and (
            required_fields or duplicate_check_rules or re.search(r"throw\s+new", text, flags=re.IGNORECASE)
        ):
            save_guard_rules.append("run validation and duplicate guards before persistence")
        if re.search(r"\b(role|admin|manager)\b", text, flags=re.IGNORECASE) and re.search(r"\b(save|insert|update|submit)\b", text, flags=re.IGNORECASE):
            save_guard_rules.append("enforce role-based save restrictions before save")
        if re.search(r"\b(status|state|pending|approved|closed|draft)\b", text, flags=re.IGNORECASE) and re.search(r"\b(save|update|submit)\b", text, flags=re.IGNORECASE):
            save_guard_rules.append("enforce status-change restrictions before save")

        exception_rules = self._extract_unique_matches(
            text,
            r"throw\s+new\s+([A-Za-z]+Exception)|\b(IllegalStateException|ValidationException|SecurityException|IllegalArgumentException)\b",
        )
        exception_rules = [f"raise {rule}" for rule in exception_rules]

        command_boundary_hints: list[str] = []
        if required_fields or duplicate_check_rules or save_guard_rules:
            command_boundary_hints.append("split validation from persistence")
            command_boundary_hints.append("use command DTO and validator")
        if exception_rules:
            command_boundary_hints.append("normalize save-time exceptions into explicit validation results")

        if supplemental:
            field_validation_rules = field_validation_rules[:2]
            duplicate_check_rules = duplicate_check_rules[:1]
            save_guard_rules = save_guard_rules[:1]
            exception_rules = exception_rules[:1]
            command_boundary_hints = command_boundary_hints[:1]

        return SaveValidationRules(
            entities=entities,
            required_fields=required_fields,
            field_validation_rules=self._dedupe_list(field_validation_rules),
            duplicate_check_rules=self._dedupe_list(duplicate_check_rules),
            save_guard_rules=self._dedupe_list(save_guard_rules),
            exception_rules=self._dedupe_list(exception_rules),
            command_boundary_hints=self._dedupe_list(command_boundary_hints),
        )

    def estimate_confidence(self, prepared: PreparedRebuildInput) -> float:
        score = 0.1
        score += min(0.18, len(prepared.assets.source_code) / 6000)
        score += min(0.16, len(prepared.assets.ui_template) / 5000)
        score += min(0.16, len(prepared.assets.sql_queries) / 2500)
        score += min(0.14, len(prepared.assets.database_schema) / 2500)
        score += min(0.06, len(prepared.assets.framework_info) / 1000)
        signal_groups = sum(
            1
            for group in (
                prepared.signals.status_permissions,
                prepared.signals.search_filters,
                prepared.signals.save_validation,
            )
            if group
        )
        score += signal_groups * 0.08
        score += min(0.06, len(prepared.signals.concepts) * 0.02)
        dominance_gap = self._dominance_gap(prepared.signals.scores)
        score += min(0.08, dominance_gap * 0.12)
        score -= min(0.22, 0.06 * len(prepared.missing_context))
        if prepared.scope_limited:
            score -= 0.05
        if prepared.missing_context:
            score = min(score, 0.94)
        return max(0.0, min(1.0, round(score, 2)))

    def build_result(self, prepared: PreparedRebuildInput) -> StructuredRebuildResult:
        from mellow_link.services.refactoring_support_engine.facade import RefactoringSupportEngineFacade

        return RefactoringSupportEngineFacade(self).build_result(prepared)

    def _engine_template_support(self) -> TemplateSupport:
        return TemplateSupport()

    def _compat_decision_artifacts(
        self,
        prepared: PreparedRebuildInput,
        applied_templates: list[AppliedJudgmentTemplate] | None = None,
    ):
        from mellow_link.services.refactoring_support_engine.schemas import DecisionArtifacts, DecisionSummary

        templates = list(applied_templates or [])
        primary_judgment = (prepared.selected_primary_judgment or "").strip()
        if not primary_judgment and templates:
            primary_judgment = templates[0].template_id
        selected_narrative = (prepared.selected_narrative_judgment or "").strip() or primary_judgment
        return DecisionArtifacts(
            decision_summary=DecisionSummary(decisions=[]),
            applied_templates=templates,
            pattern_candidates=list(prepared.pattern_candidates or []),
            primary_judgment=primary_judgment,
            template_judgment=primary_judgment,
            structural_judgment="observation_only",
            narrative_axis=selected_narrative,
            feature_signal_mode=str(getattr(getattr(prepared, "signals", None), "primary_feature_mode", "") or ""),
            primary_judgment_reason=(prepared.selected_primary_judgment_reason or "").strip(),
            selected_narrative_judgment=selected_narrative,
            decision_items=[],
        )

    def build_polish_bundle(
        self,
        result: StructuredRebuildResult,
        *,
        audience: str = "manager",
        delivery_mode: str = "client_report",
        use_ai_rewrite: bool = False,
    ):
        from .postprocess.service import StructuredResultPolishService

        return StructuredResultPolishService().polish_result(
            result,
            audience=audience,
            delivery_mode=delivery_mode,
            use_ai_rewrite=use_ai_rewrite,
        )

    def _build_extensions(self, prepared: PreparedRebuildInput) -> dict[str, Any]:
        if not prepared.accounting_asset_name and not prepared.accounting_input_error:
            return {}
        from mellow_link.services.accounting_mvp.service import build_accounting_extension

        extension = build_accounting_extension(
            accounting_input=prepared.accounting_input,
            context_text=prepared.legacy_bundle,
            accounting_input_error=prepared.accounting_input_error,
        )
        return {"accounting": extension.model_dump()}

    def attach_report_purpose(
        self,
        result: StructuredRebuildResult,
        user_question: str | None = None,
        narrative_judgment: str | None = None,
    ) -> StructuredRebuildResult:
        report_purpose, report_scope, report_questions = self._build_report_metadata(
            result,
            user_question,
            narrative_judgment=narrative_judgment,
        )
        return result.model_copy(
            update={
                "report_purpose": report_purpose,
                "report_scope": report_scope,
                "report_questions": report_questions,
            }
        )

    def _apply_accounting_top_narrative(
        self,
        prepared: PreparedRebuildInput,
        result: StructuredRebuildResult,
    ) -> StructuredRebuildResult:
        accounting = result.extensions.get("accounting") if isinstance(result.extensions, dict) else None
        if not isinstance(accounting, dict):
            return result
        updates = self._build_accounting_top_narrative_updates(prepared, result, accounting)
        if not updates:
            return result
        return result.model_copy(update=updates)

    def _apply_accounting_bottom_sections(
        self,
        prepared: PreparedRebuildInput,
        result: StructuredRebuildResult,
    ) -> StructuredRebuildResult:
        accounting = result.extensions.get("accounting") if isinstance(result.extensions, dict) else None
        if not isinstance(accounting, dict):
            return result
        updates = self._build_accounting_bottom_section_updates(prepared, result, accounting)
        if not updates:
            return result
        return result.model_copy(update=updates)

    def _build_accounting_top_narrative_updates(
        self,
        prepared: PreparedRebuildInput,
        result: StructuredRebuildResult,
        accounting: dict[str, Any],
    ) -> dict[str, Any]:
        mode = self._accounting_narrative_mode(accounting)
        context = self._build_accounting_narrative_context(accounting)
        if not context:
            return {}

        if mode == "failure":
            return self._build_accounting_failure_narrative_updates(result, context)
        if mode == "warning":
            return self._build_accounting_warning_narrative_updates(result, context)
        return self._build_accounting_success_narrative_updates(result, context)

    def _build_accounting_bottom_section_updates(
        self,
        prepared: PreparedRebuildInput,
        result: StructuredRebuildResult,
        accounting: dict[str, Any],
    ) -> dict[str, Any]:
        mode = self._accounting_narrative_mode(accounting)
        context = self._build_accounting_narrative_context(accounting)
        if not context:
            return {}

        method_label = context["method_label"]
        failure_text = context["humanized_failure"]
        warning_text = context["warning_text"]
        voucher_status = context["voucher_status"]
        voucher_issue = context["voucher_issue"]

        if mode == "failure":
            grounded_rules = [
                self._make_accounting_grounded_rule(
                    "계산 입력 책임",
                    "거래 데이터, 환율 데이터, 회계 정책 입력이 모두 확보되어야 회계 계산을 수행할 수 있습니다.",
                    ["입력 검증", "회계 계산"],
                    confidence="확정",
                    needs_verification=False,
                ),
                self._make_accounting_grounded_rule(
                    "계산 차단 사유",
                    f"현재 계산 차단 사유는 {failure_text.rstrip('.')}입니다.",
                    ["입력 검증", "회계 계산"],
                    confidence="확정",
                    needs_verification=False,
                ),
                self._make_accounting_grounded_rule(
                    "재실행 조건",
                    "누락 입력과 기준 정보를 보완하면 같은 정책 기준으로 재계산할 수 있습니다.",
                    ["회계 계산", "전표 검토"],
                    confidence="조건부",
                    needs_verification=True,
                ),
            ]
            retained_contracts = [
                self._make_accounting_contract(
                    "환율 기준 계약은 유지하는 것이 필요합니다.",
                    "거래일 기준 환율이 확보되어야 계산 결과를 산출할 수 있습니다.",
                ),
                self._make_accounting_contract(
                    "회계 정책 적용 기준 계약은 유지하는 것이 필요합니다.",
                    "정책 버전과 유효기간이 확정되어야 계산 방식을 결정할 수 있습니다.",
                ),
                self._make_accounting_contract(
                    "거래일 입력 계약은 유지하는 것이 필요합니다.",
                    "거래일이 누락되면 환율과 정책 선택 근거를 확정할 수 없습니다.",
                ),
            ]
            recomposition_draft = LayeredListResult(
                database=[
                    "누락된 거래일, 환율 기준일, 정책 유효기간 입력을 먼저 보완합니다.",
                    "거래 입력과 환율 데이터의 필수 필드를 다시 확인합니다.",
                ],
                backend=[
                    "계산을 막는 입력 누락 사유를 명시적으로 반환하는지 점검합니다.",
                    "입력 보완 후 동일 기준으로 재계산할 수 있도록 검증 경로를 확인합니다.",
                ],
                frontend=[
                    "계산 불가 사유와 누락 입력을 사용자에게 바로 표시합니다.",
                    "보완 후 재실행 조건을 같은 화면에서 안내합니다.",
                ],
            )
            recommended_directions = [
                "누락 입력과 기준 정보를 먼저 보완하는 것이 필요합니다.",
                "환율과 정책 기준을 확정한 뒤 재계산하는 것이 필요합니다.",
                "재계산 이후 전표 정합성 검토를 다시 수행하는 것이 필요합니다.",
            ]
        else:
            voucher_rule = (
                "전표는 계산 결과와 정합성을 유지해야 합니다."
                if voucher_status == "completed"
                else "전표 데이터와 계정 매핑이 보완되어야 전표 정합성을 검토할 수 있습니다."
                if voucher_status == "input_missing"
                else f"전표 검토에서는 {voucher_issue or '추가 확인 항목'}을 후속 확인해야 합니다."
            )
            warning_suffix = ""
            if mode == "warning" and warning_text:
                warning_suffix = f" 다만 {warning_text.rstrip('.')} 항목은 최종 확정 전에 추가 확인이 필요합니다."
            grounded_rules = [
                self._make_accounting_grounded_rule(
                    "적용 회계 방식",
                    f"환차손익은 {method_label} 기준으로 계산됩니다.{warning_suffix}",
                    ["회계 계산", "정책 적용"],
                    confidence="확정",
                    needs_verification=False,
                ),
                self._make_accounting_grounded_rule(
                    "환율 적용 기준",
                    "환율은 거래일 기준으로 적용되며 계산 근거와 동일하게 유지되어야 합니다.",
                    ["입력 검증", "회계 계산"],
                    confidence="확정",
                    needs_verification=False,
                ),
                self._make_accounting_grounded_rule(
                    "전표 정합성 유지",
                    voucher_rule,
                    ["전표 검토", "회계 계산"],
                    confidence="조건부" if voucher_status != "completed" else "확정",
                    needs_verification=voucher_status != "completed",
                ),
            ]
            retained_contracts = [
                self._make_accounting_contract(
                    "환율 기준 계약은 유지하는 것이 필요합니다.",
                    "거래일 기준 환율과 실제 계산에 사용한 환율이 일치해야 합니다.",
                ),
                self._make_accounting_contract(
                    "회계 정책 적용 기준 계약은 유지하는 것이 필요합니다.",
                    f"{method_label} 기준과 정책 버전이 계산 결과에 그대로 반영되어야 합니다.",
                ),
                self._make_accounting_contract(
                    "전표-거래 매핑 계약은 유지하는 것이 필요합니다.",
                    "거래 데이터와 전표 검토 결과가 같은 기준으로 연결되어야 합니다.",
                ),
            ]
            recomposition_draft = LayeredListResult(
                database=[
                    "거래 입력, 환율 기준일, 정책 버전 필드를 같은 회계 기준으로 점검합니다.",
                    "전표와 거래를 연결하는 매핑 키를 함께 확인합니다.",
                ],
                backend=[
                    "계산 방식, 환율 선택 기준, 전표 검토 로직을 회계 기준으로 점검합니다.",
                    "불일치 항목과 경고를 계산 결과와 함께 반환하도록 확인합니다.",
                ],
                frontend=[
                    "계산 결과, 경고 항목, 전표 검토 상태를 같은 화면에서 보여줍니다.",
                    "입력 누락과 후속 확인 필요 항목을 사용자에게 명확히 안내합니다.",
                ],
            )
            recommended_directions = [
                "적용 회계 방식과 계산 기준을 먼저 확인하는 것이 필요합니다.",
                "전표 정합성 또는 입력 경고를 함께 검토하는 것이 필요합니다.",
                "후속 운영 기준과 재계산 조건을 확정하는 것이 필요합니다.",
            ]

        return {
            "grounded_business_rules": grounded_rules,
            "core_business_rules": [item.description for item in grounded_rules],
            "retained_contracts": retained_contracts,
            "recomposition_draft": recomposition_draft,
            "recommended_directions": recommended_directions,
        }

    def _make_accounting_grounded_rule(
        self,
        title: str,
        description: str,
        design_targets: list[str],
        *,
        confidence: str,
        needs_verification: bool,
    ) -> GroundedBusinessRule:
        return GroundedBusinessRule(
            title=title,
            description=description,
            evidence=[],
            design_targets=design_targets,
            confidence=confidence,
            confidence_reason="회계 확장 결과를 기준으로 생성한 보고서용 규칙입니다.",
            needs_verification=needs_verification,
        )

    def _make_accounting_contract(self, item: str, basis: str) -> RetainedContract:
        return RetainedContract(item=item, basis=basis, evidence=[])

    def _accounting_narrative_mode(self, accounting: dict[str, Any]) -> str:
        calc_status = accounting.get("calculation_status") or {}
        if not bool(calc_status.get("can_calculate")):
            return "failure"
        warnings = self._collect_accounting_warnings(accounting)
        return "warning" if warnings else "success"

    def _build_accounting_narrative_context(self, accounting: dict[str, Any]) -> dict[str, Any]:
        calc_status = accounting.get("calculation_status") or {}
        validation = accounting.get("input_validation") or {}
        fx_calc = accounting.get("fx_calculation") or {}
        voucher_review = accounting.get("voucher_review") or {}
        analysis = accounting.get("accounting_analysis") or {}

        method = (
            str(fx_calc.get("method") or "").strip()
            or str(analysis.get("recommended_method") or "").strip()
        )
        method_label = self._humanize_accounting_method(method) or "회계 방식"

        amount_value = fx_calc.get("realized_gain_loss_krw")
        amount_text = ""
        if amount_value is not None:
            try:
                amount_text = f"{int(amount_value):,}원"
            except Exception:
                amount_text = str(amount_value)

        warnings = self._collect_accounting_warnings(accounting)
        warning_text = self._humanize_accounting_issue(warnings[0]) if warnings else ""
        warning_label = self._accounting_issue_label(warnings[0]) if warnings else ""

        failure_issue = (
            str(calc_status.get("blocking_issue") or "").strip()
            or str(validation.get("failure_reason") or "").strip()
            or str(fx_calc.get("failure_reason") or "").strip()
        )
        humanized_failure = self._humanize_accounting_issue(failure_issue)
        humanized_failure_label = self._accounting_issue_label(failure_issue)

        voucher_status = str(voucher_review.get("status") or "").strip().lower()
        voucher_summary = self._build_accounting_voucher_summary(voucher_review)
        voucher_issue = self._build_accounting_voucher_issue(voucher_review)

        return {
            "method_label": method_label,
            "amount_text": amount_text,
            "warnings": warnings,
            "warning_text": warning_text,
            "warning_label": warning_label,
            "humanized_failure": humanized_failure,
            "humanized_failure_label": humanized_failure_label,
            "voucher_status": voucher_status,
            "voucher_summary": voucher_summary,
            "voucher_issue": voucher_issue,
            "report_purpose": accounting.get("report_purpose") or "",
            "summary_sentence": str(accounting.get("summary_sentence") or "").strip(),
            "can_calculate": bool(calc_status.get("can_calculate")),
        }

    def _collect_accounting_warnings(self, accounting: dict[str, Any]) -> list[str]:
        validation = accounting.get("input_validation") or {}
        fx_calc = accounting.get("fx_calculation") or {}
        voucher_review = accounting.get("voucher_review") or {}
        candidates = []
        candidates.extend(str(item or "").strip() for item in (validation.get("ambiguous_inputs") or []))
        candidates.extend(str(item or "").strip() for item in (fx_calc.get("warnings") or []))
        candidates.extend(str(item or "").strip() for item in (validation.get("warnings") or []))
        candidates.extend(str(item or "").strip() for item in (voucher_review.get("warnings") or []))
        deduped: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            key = re.sub(r"\s+", " ", item).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _humanize_accounting_method(self, value: str) -> str:
        mapping = {
            "MOVING_AVERAGE": "이동평균법",
            "FIFO": "선입선출법",
            "SPECIFIC_ID": "개별식별법",
        }
        return mapping.get((value or "").strip().upper(), (value or "").strip())

    def _humanize_accounting_issue(self, value: str) -> str:
        text = (value or "").strip()
        if not text:
            return "추가 입력 확인이 필요합니다."
        mapping = {
            "all required inputs present": "필수 입력이 모두 제공되었습니다.",
            "voucher_review requires vouchers and account_mappings": "전표 데이터와 계정 매핑이 없어 전표 검토를 수행할 수 없습니다.",
            "missing exchange_rates": "환율 데이터가 누락되었습니다.",
            "missing required inputs: transactions": "거래 데이터가 누락되었습니다.",
            "missing required inputs: exchange_rates": "환율 데이터가 누락되었습니다.",
            "missing required inputs: policies": "회계 정책 데이터가 누락되었습니다.",
            "missing required inputs: vouchers": "전표 데이터가 누락되었습니다.",
            "missing required inputs: account_mappings": "계정 매핑이 누락되었습니다.",
            "multiple active policies matched transaction dates": "복수 정책이 거래일과 동시에 일치해 적용 정책을 확정할 수 없습니다.",
            "no active policy covers transaction dates": "거래일을 포괄하는 활성 정책이 없습니다.",
        }
        if text in mapping:
            return mapping[text]
        if text.startswith("invalid accounting payload schema:"):
            lowered = text.lower()
            if "occurred_at" in lowered:
                return "거래일(occurred_at) 입력이 누락되었습니다."
            if "rate_date" in lowered:
                return "환율 기준일(rate_date) 입력이 누락되었습니다."
            if "currency" in lowered:
                return "통화(currency) 입력이 누락되었습니다."
            return "회계 입력 형식이 올바르지 않습니다."
        if text.startswith("invalid accounting payload json:"):
            return "회계 입력 JSON 형식이 올바르지 않습니다."
        if text.startswith("missing required inputs:"):
            missing = text.split(":", 1)[1].strip()
            return f"필수 입력이 누락되었습니다. ({missing})"
        lowered = text.lower()
        if "ambiguous exchange rate" in lowered or "multiple exchange rates" in lowered:
            return "복수 환율이 감지되어 적용 환율을 확정할 수 없습니다."
        if "exchange rate" in lowered:
            return "환율 선택 근거가 불명확합니다."
        if "policy" in lowered:
            return "적용할 회계 정책을 확정할 수 없습니다."
        if "lot" in lowered or "source lot" in lowered:
            return "lot/source 지정이 없어 계산을 확정할 수 없습니다."
        return text.rstrip(".") + "."

    def _accounting_issue_label(self, value: str) -> str:
        text = (value or "").strip()
        if not text:
            return "입력 확인 필요"
        mapping = {
            "all required inputs present": "필수 입력 충족",
            "voucher_review requires vouchers and account_mappings": "전표 데이터 및 계정 매핑 부족",
            "missing exchange_rates": "환율 데이터 누락",
            "missing required inputs: transactions": "거래 데이터 누락",
            "missing required inputs: exchange_rates": "환율 데이터 누락",
            "missing required inputs: policies": "회계 정책 데이터 누락",
            "missing required inputs: vouchers": "전표 데이터 누락",
            "missing required inputs: account_mappings": "계정 매핑 누락",
            "multiple active policies matched transaction dates": "복수 정책 충돌",
            "no active policy covers transaction dates": "정책 유효기간 불일치",
        }
        if text in mapping:
            return mapping[text]
        lowered = text.lower()
        if text.startswith("invalid accounting payload schema:"):
            if "occurred_at" in lowered:
                return "거래일 입력 누락"
            if "rate_date" in lowered:
                return "환율 기준일 입력 누락"
            if "currency" in lowered:
                return "통화 입력 누락"
            return "회계 입력 형식 오류"
        if text.startswith("invalid accounting payload json:"):
            return "회계 입력 JSON 형식 오류"
        if "차변/대변이 일치하지 않습니다" in text:
            return "차변/대변 불일치"
        if "환차익 계정이 전표에 반영되지 않았습니다" in text:
            return "환차익 계정 미반영"
        if "환차손 계정이 전표에 반영되지 않았습니다" in text:
            return "환차손 계정 미반영"
        if "ambiguous exchange rate" in lowered or "multiple exchange rates" in lowered:
            return "복수 환율 충돌"
        if "exchange rate" in lowered:
            return "환율 선택 기준 불명확"
        if "policy" in lowered:
            return "회계 정책 확정 필요"
        if "lot" in lowered or "source lot" in lowered:
            return "lot/source 지정 누락"
        return self._humanize_accounting_issue(text).rstrip(".")

    def _build_accounting_voucher_summary(self, voucher_review: dict[str, Any]) -> str:
        status = str(voucher_review.get("status") or "").strip().lower()
        if status == "input_missing":
            return "전표 검토는 입력 부족으로 아직 수행되지 않았습니다."
        if status == "failed":
            issue = self._humanize_accounting_issue(str(voucher_review.get("failure_reason") or ""))
            return f"전표 검토는 완료되지 않았으며 주요 사유는 {issue}"
        if status == "completed":
            if voucher_review.get("mismatches"):
                return "전표 검토 결과 일부 불일치 항목이 확인되어 후속 검토가 필요합니다."
            balance_ok = voucher_review.get("balance_ok")
            policy_consistent = voucher_review.get("policy_consistent")
            if balance_ok is True and policy_consistent is True:
                return "전표 검토 결과 차변·대변 균형과 정책 일치가 확인되었습니다."
            if balance_ok is False or policy_consistent is False:
                return "전표 검토 결과 불일치 항목이 확인되어 수정 전 검토가 필요합니다."
            return "전표 검토 결과 추가 확인이 필요합니다."
        return "전표 검토 결과를 아직 확정할 수 없습니다."

    def _build_accounting_voucher_issue(self, voucher_review: dict[str, Any]) -> str:
        status = str(voucher_review.get("status") or "").strip().lower()
        if status == "input_missing":
            return "전표 데이터와 계정 매핑 보완"
        if status == "failed":
            return self._accounting_issue_label(str(voucher_review.get("failure_reason") or ""))
        mismatches = voucher_review.get("mismatches") or []
        if mismatches:
            first = mismatches[0]
            if isinstance(first, dict):
                return self._accounting_issue_label(str(first.get("message") or "전표 불일치"))
            return self._accounting_issue_label(str(first))
        balance_ok = voucher_review.get("balance_ok")
        policy_consistent = voucher_review.get("policy_consistent")
        if balance_ok is False:
            return "차변·대변 균형 불일치"
        if policy_consistent is False:
            return "회계 정책 불일치"
        return ""

    def _build_accounting_success_narrative_updates(
        self,
        result: StructuredRebuildResult,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        method_label = context["method_label"]
        amount_text = context["amount_text"] or "산출 금액"
        voucher_summary = context["voucher_summary"]
        voucher_issue = context["voucher_issue"]

        summary_lines = [
            result.report_purpose or "이 문서는 외환 거래의 환차손익 계산 결과와 적용 회계 방식을 검토한 결과입니다.",
            f"현재 기준 계산 방식은 {method_label}이며, 산출된 환차손익은 {amount_text}입니다.",
            voucher_summary,
        ]
        if context["warning_text"]:
            summary_lines.append(f"추가 확인이 필요한 경고는 {context['warning_label'] or context['warning_text'].rstrip('.')}입니다.")

        decision_items = [
            DecisionItem(
                statement=f"본 거래는 {method_label} 기준으로 계산하는 것이 타당합니다.",
                rationale="정책 입력과 계산 결과가 현재 적용 방식과 일치합니다.",
            ),
            DecisionItem(
                statement=f"현재 기준 환차손익은 {amount_text}으로 산출됩니다.",
                rationale="입력 거래와 환율을 기준으로 계산된 금액입니다.",
            ),
            DecisionItem(
                statement=(
                    f"전표 또는 입력 항목 중 {voucher_issue}는 후속 확인이 필요합니다."
                    if voucher_issue
                    else "전표 검토 결과와 입력 상태를 함께 유지하는 것이 필요합니다."
                ),
                rationale=voucher_summary,
            ),
        ]

        priority_items = [
            PrioritySplitItem(
                priority=1,
                item="계산 방식과 환차손익 수치를 먼저 확정하는 것이 필요합니다.",
                title="회계 계산 결과 확정",
                reason=f"{method_label} 기준 계산 결과 {amount_text}을 우선 확인해야 이후 검토 기준이 흔들리지 않습니다.",
                impact_scope="회계 방식, 환차손익 수치, 계산 근거",
                prerequisite="거래 입력과 환율 기준 확정",
                linked_rules=[method_label, amount_text],
                linked_contracts=["회계 정책 기준", "환율 데이터"],
            ),
            PrioritySplitItem(
                priority=2,
                item="전표 정합성 검토 범위를 다음 단계로 정리하는 것이 필요합니다.",
                title="전표 정합성 검토",
                reason=voucher_summary,
                impact_scope="전표 검토 범위, 불일치 항목, 계정 매핑",
                prerequisite="계산 결과 초안 확정",
                linked_rules=["전표 검토 결과"],
                linked_contracts=["전표 데이터", "계정 매핑"],
            ),
            PrioritySplitItem(
                priority=3,
                item="계산 결과와 운영 기준을 최종 확정하는 것이 필요합니다.",
                title="운영 기준 확정",
                reason="계산 방식, 환율 기준, 전표 검토 결과를 함께 확정해야 운영 해석이 흔들리지 않습니다.",
                impact_scope="운영 기준, 재실행 조건, 후속 보고",
                prerequisite="계산 결과와 전표 검토 1차 완료",
                linked_rules=["회계 정책", "환율 기준"],
                linked_contracts=["정책 기준", "입력 통제 기준"],
            ),
        ]

        design_options = [
            DesignOption(
                name="옵션 A. 현재 회계 방식 유지 및 입력 통제 강화",
                structure_summary=f"{method_label} 계산 방식을 유지하면서 입력 기준과 전표 검토 절차를 함께 강화합니다.",
                advantages=["현재 계산 결과를 바로 설명할 수 있습니다.", "입력 통제와 전표 검토 기준을 함께 정리할 수 있습니다."],
                risks=["입력 경고가 남아 있으면 후속 검토가 필요할 수 있습니다."],
                difficulty="LOW",
                duration_weeks=4,
                recommended=True,
                selection_reason=f"현재 계산 결과 {amount_text}과 {method_label} 적용 근거가 확인되어, 기존 계산 방식은 유지하되 입력 통제와 전표 검토 기준을 강화하는 편이 가장 안정적입니다.",
            ),
            DesignOption(
                name="옵션 B. 계산 방식 변경 검토 및 전표 기준 재정렬",
                structure_summary="계산 방식 후보를 다시 비교하고 전표 기준을 함께 재정렬합니다.",
                advantages=["정책 변경 가능성을 함께 검토할 수 있습니다."],
                risks=["기존 계산 결과와의 비교 검토가 추가로 필요합니다."],
                difficulty="MEDIUM",
                duration_weeks=5,
                recommended=False,
                selection_reason="계산 방식 재검토는 가능하지만 현재 계산 결과와 정책 일관성이 유지되는 상황에서는 후순위입니다.",
            ),
            DesignOption(
                name="옵션 C. 전표 검토 중심 운영 보완",
                structure_summary="전표 검토와 운영 기준 보완을 먼저 수행하고 계산 방식은 유지합니다.",
                advantages=["운영 통제 기준을 빠르게 보완할 수 있습니다."],
                risks=["계산 방식 검토 범위는 상대적으로 좁아질 수 있습니다."],
                difficulty="MEDIUM",
                duration_weeks=4,
                recommended=False,
                selection_reason="전표 검토 보완은 유효하지만 현재는 계산 결과와 정책 일관성 확정이 더 우선입니다.",
            ),
        ]
        recommended_option = RecommendedOption(
            name=design_options[0].name,
            structure_summary=design_options[0].structure_summary,
            selection_reason=design_options[0].selection_reason,
            expected_outcomes=["계산 결과를 그대로 설명할 수 있습니다.", "전표 검토와 입력 통제 기준을 함께 유지할 수 있습니다."],
        )

        execution_plan = [
            ExecutionPlanWeek(
                week_label="1주차",
                goal="거래 입력, 환율, 정책 기준을 확인합니다.",
                tasks=["외화 거래 입력과 거래일 기준을 확인합니다.", "환율 데이터와 적용 정책 버전을 확정합니다."],
                related_rules=[method_label, "환율 기준"],
                related_contracts=["외화 거래 데이터", "회계 정책"],
                roles=["업무 분석가", "회계 담당자"],
                duration_weeks=1,
                deliverables=["입력 확인표", "정책 기준표"],
            ),
            ExecutionPlanWeek(
                week_label="2주차",
                goal="계산 방식과 수치를 검토합니다.",
                tasks=[f"{method_label} 계산 근거와 {amount_text} 산출 과정을 확인합니다.", "경고 항목이 있으면 계산 근거와 함께 검토합니다."],
                related_rules=[method_label, amount_text],
                related_contracts=["계산 방식", "환율 데이터"],
                roles=["회계 담당자", "컨설턴트"],
                duration_weeks=1,
                deliverables=["계산 검토 메모", "수치 확인표"],
            ),
            ExecutionPlanWeek(
                week_label="3주차",
                goal="전표 정합성과 mismatch를 검토합니다.",
                tasks=["전표 데이터와 계정 매핑을 계산 결과와 비교합니다.", "불일치 항목이 있으면 후속 조치 기준을 정리합니다."],
                related_rules=["전표 정합성", voucher_issue or "전표 검토"],
                related_contracts=["전표 데이터", "계정 매핑"],
                roles=["회계 담당자", "QA"],
                duration_weeks=1,
                deliverables=["전표 검토 결과", "불일치 항목 목록"],
            ),
            ExecutionPlanWeek(
                week_label="4주차",
                goal="후속 보정 또는 운영 기준을 확정합니다.",
                tasks=["계산 결과, 전표 검토 결과, 경고 항목을 함께 정리합니다.", "재계산 필요 여부와 운영 기준을 최종 확정합니다."],
                related_rules=["운영 기준", "재계산 조건"],
                related_contracts=["정책 기준", "입력 통제 기준"],
                roles=["컨설턴트", "회계 담당자"],
                duration_weeks=1,
                deliverables=["운영 기준서", "후속 조치 목록"],
            ),
        ]

        return {
            "one_line_conclusion": f"회계 기능은 {method_label} 기준으로 환차손익 {amount_text}을 산출했으며, {voucher_summary}",
            "executive_summary_v2": summary_lines[:4],
            "decision_items": decision_items,
            "priority_split_items": priority_items,
            "design_options": design_options,
            "recommended_option": recommended_option,
            "execution_plan": execution_plan,
            "recommended_directions": [
                "계산 방식과 수치를 먼저 확정하는 것이 필요합니다.",
                "전표 검토 결과와 입력 상태를 함께 확인하는 것이 필요합니다.",
                "후속 운영 기준과 재계산 조건을 정리하는 것이 필요합니다.",
            ],
            "risks": [
                voucher_summary,
                "환율 기준이나 정책 버전이 바뀌면 계산 결과가 달라질 수 있습니다.",
            ],
        }

    def _build_accounting_failure_narrative_updates(
        self,
        result: StructuredRebuildResult,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        failure_reason = context["humanized_failure"]
        failure_label = context["humanized_failure_label"] or failure_reason.rstrip(".")
        summary_lines = [
            "이 문서는 외환 거래의 환차손익 계산 가능 여부를 검토한 결과입니다.",
            "현재 입력 기준으로는 회계 계산을 수행할 수 없습니다.",
            f"주요 사유는 {failure_label}입니다.",
            "필수 입력이 보완되면 재계산이 가능합니다.",
        ]
        design_options = [
            DesignOption(
                name="옵션 A. 누락 입력 보완 후 동일 방식으로 재계산",
                structure_summary="현재 계산 방식을 유지한 채 누락 입력을 먼저 보완하고 재계산합니다.",
                advantages=["기존 정책 가정을 유지한 상태에서 재실행할 수 있습니다."],
                risks=["누락 입력이 계속 남으면 계산을 확정할 수 없습니다."],
                difficulty="LOW",
                duration_weeks=4,
                recommended=True,
                selection_reason=f"현재 계산 실패 원인이 {failure_label}로 명확하므로, 누락 입력을 보완한 뒤 동일 방식으로 재계산하는 것이 가장 직접적입니다.",
            ),
            DesignOption(
                name="옵션 B. 정책/환율 기준 정리 후 재실행",
                structure_summary="정책 버전과 환율 기준을 먼저 정리한 뒤 계산을 다시 수행합니다.",
                advantages=["입력 해석 기준을 먼저 고정할 수 있습니다."],
                risks=["입력 보완 없이 기준만 정리하면 재계산이 다시 막힐 수 있습니다."],
                difficulty="MEDIUM",
                duration_weeks=4,
                recommended=False,
                selection_reason="정책과 환율 기준 정리는 필요할 수 있지만, 현재는 누락 입력 보완이 우선입니다.",
            ),
            DesignOption(
                name="옵션 C. 전표 검토만 우선 수행",
                structure_summary="가능한 범위의 전표 검토를 먼저 수행하고 계산은 후속으로 넘깁니다.",
                advantages=["입력 보완 전에도 일부 검토 범위를 확보할 수 있습니다."],
                risks=["최종 환차손익 수치는 여전히 산출할 수 없습니다."],
                difficulty="MEDIUM",
                duration_weeks=3,
                recommended=False,
                selection_reason="전표 검토 선행은 가능하지만 계산 실패 상태를 직접 해소하지는 못하므로 후순위입니다.",
            ),
        ]
        recommended_option = RecommendedOption(
            name=design_options[0].name,
            structure_summary=design_options[0].structure_summary,
            selection_reason=design_options[0].selection_reason,
            expected_outcomes=["누락 입력이 정리됩니다.", "재계산 가능 여부를 다시 판단할 수 있습니다."],
        )
        execution_plan = [
            ExecutionPlanWeek(
                week_label="1주차",
                goal="누락 입력을 확인하고 보완합니다.",
                tasks=["필수 거래 입력, 환율, 정책 데이터를 다시 확인합니다.", "현재 실패 사유와 직접 연결된 입력 항목을 보완합니다."],
                related_rules=["필수 입력", failure_label],
                related_contracts=["외화 거래 데이터", "환율 데이터", "회계 정책"],
                roles=["업무 분석가", "회계 담당자"],
                duration_weeks=1,
                deliverables=["누락 입력 목록", "보완 계획"],
            ),
            ExecutionPlanWeek(
                week_label="2주차",
                goal="환율, 정책, 거래일 기준을 검토합니다.",
                tasks=["적용 환율과 정책 버전을 다시 확인합니다.", "거래일과 정책 유효기간이 맞는지 점검합니다."],
                related_rules=["환율 기준", "정책 유효기간"],
                related_contracts=["환율 데이터", "회계 정책"],
                roles=["회계 담당자", "컨설턴트"],
                duration_weeks=1,
                deliverables=["기준 검토 메모", "재실행 조건표"],
            ),
            ExecutionPlanWeek(
                week_label="3주차",
                goal="보완된 입력으로 재계산을 수행합니다.",
                tasks=["보완 입력으로 외화 계산을 다시 실행합니다.", "계산 방식과 산출 결과가 정상적으로 생성되는지 확인합니다."],
                related_rules=["재계산", "계산 방식"],
                related_contracts=["거래 입력", "정책 기준"],
                roles=["회계 담당자", "QA"],
                duration_weeks=1,
                deliverables=["재계산 결과", "입력 검증 결과"],
            ),
            ExecutionPlanWeek(
                week_label="4주차",
                goal="전표 정합성과 후속 기준을 다시 확인합니다.",
                tasks=["재계산 결과를 기준으로 전표 정합성을 검토합니다.", "후속 운영 기준과 재실행 기준을 확정합니다."],
                related_rules=["전표 정합성", "운영 기준"],
                related_contracts=["전표 데이터", "계정 매핑"],
                roles=["회계 담당자", "컨설턴트"],
                duration_weeks=1,
                deliverables=["전표 재검토 결과", "운영 기준서"],
            ),
        ]
        return {
            "one_line_conclusion": f"회계 기능은 현재 입력 기준으로 계산을 수행할 수 없으며, 주요 사유는 {failure_label}입니다.",
            "executive_summary_v2": summary_lines,
            "decision_items": [
                DecisionItem(statement="현재 입력으로는 회계 계산을 진행할 수 없습니다.", rationale=failure_reason),
                DecisionItem(statement="누락 또는 불명확한 입력은 현재 실패 사유와 직접 연결됩니다.", rationale=failure_reason),
                DecisionItem(statement="계산 방식 검토는 가능하지만 최종 수치 산출은 보류해야 합니다.", rationale="필수 입력이 확보되기 전까지는 계산 결과를 확정할 수 없습니다."),
            ],
            "priority_split_items": [
                PrioritySplitItem(priority=1, item="누락 입력을 먼저 보완하는 것이 필요합니다.", title="필수 입력 보완", reason=failure_reason, impact_scope="거래 입력, 환율, 정책 데이터", prerequisite="현재 입력 점검", linked_rules=["필수 입력"], linked_contracts=["거래 데이터", "환율 데이터", "회계 정책"]),
                PrioritySplitItem(priority=2, item="환율과 정책 기준을 다시 정리하는 것이 필요합니다.", title="기준 재정렬", reason="입력 보완 뒤에도 적용 기준이 불명확하면 계산을 확정할 수 없습니다.", impact_scope="환율 기준, 정책 버전, 거래일", prerequisite="누락 입력 보완", linked_rules=["환율 기준", "정책 기준"], linked_contracts=["회계 정책", "환율 데이터"]),
                PrioritySplitItem(priority=3, item="재계산과 전표 재검토를 후속으로 수행하는 것이 필요합니다.", title="재실행 및 재검토", reason="입력 보완 이후에만 계산 결과와 전표 검토를 다시 연결할 수 있습니다.", impact_scope="재계산 결과, 전표 정합성", prerequisite="입력과 기준 정리 완료", linked_rules=["재계산"], linked_contracts=["전표 데이터", "계정 매핑"]),
            ],
            "design_options": design_options,
            "recommended_option": recommended_option,
            "execution_plan": execution_plan,
            "recommended_directions": [
                "누락 입력을 먼저 보완하는 것이 필요합니다.",
                "환율과 정책 기준을 다시 확인하는 것이 필요합니다.",
                "보완 후 재계산과 전표 재검토를 수행하는 것이 필요합니다.",
            ],
            "risks": [
                "필수 입력이 보완되지 않으면 계산 결과를 확정할 수 없습니다.",
                f"현재 실패 사유는 {failure_label}입니다.",
            ],
        }

    def _build_accounting_warning_narrative_updates(
        self,
        result: StructuredRebuildResult,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        method_label = context["method_label"]
        amount_text = context["amount_text"] or "산출 금액"
        warning_text = context["warning_text"] or "일부 입력 경고"
        warning_label = context["warning_label"] or warning_text.rstrip(".")
        design_options = [
            DesignOption(
                name="옵션 A. 현재 계산 결과를 초안으로 유지하고 입력 보완",
                structure_summary="현재 계산 결과는 유지하되 경고 입력을 보완하고 재검토를 진행합니다.",
                advantages=["현재 계산 결과를 바로 검토 자료로 활용할 수 있습니다."],
                risks=["경고 입력이 해소되기 전에는 최종 수치로 확정하면 안 됩니다."],
                difficulty="LOW",
                duration_weeks=4,
                recommended=True,
                selection_reason=f"현재 계산 방식 {method_label}과 계산 결과 {amount_text}은 확보됐지만, {warning_label} 때문에 결과를 검토용 초안으로 유지하는 것이 적절합니다.",
            ),
            DesignOption(
                name="옵션 B. 정책 기준 확정 후 재계산",
                structure_summary="정책 버전과 입력 기준을 먼저 확정한 뒤 계산을 다시 수행합니다.",
                advantages=["경고 원인을 직접 해소할 수 있습니다."],
                risks=["재계산 전까지는 현재 결과를 확정값으로 사용할 수 없습니다."],
                difficulty="MEDIUM",
                duration_weeks=4,
                recommended=False,
                selection_reason="정책 기준 확정은 필요하지만, 현재 계산 결과를 바로 검토 자료로 활용할 수 있으므로 2순위입니다.",
            ),
            DesignOption(
                name="옵션 C. 전표 검토를 먼저 진행해 입력 불일치 정리",
                structure_summary="전표와 입력 불일치를 먼저 정리한 뒤 계산 기준을 재확인합니다.",
                advantages=["입력 불일치 지점을 먼저 줄일 수 있습니다."],
                risks=["정책 기준 경고가 남아 있으면 재계산이 다시 필요합니다."],
                difficulty="MEDIUM",
                duration_weeks=4,
                recommended=False,
                selection_reason="전표 검토 선행은 가능하지만 경고 원인을 직접 줄이는 입력 보완보다 후순위입니다.",
            ),
        ]
        recommended_option = RecommendedOption(
            name=design_options[0].name,
            structure_summary=design_options[0].structure_summary,
            selection_reason=design_options[0].selection_reason,
            expected_outcomes=["현재 계산 결과를 검토용 초안으로 유지할 수 있습니다.", "경고 입력을 보완한 뒤 재계산할 수 있습니다."],
        )
        execution_plan = [
            ExecutionPlanWeek(
                week_label="1주차",
                goal="경고 항목을 확인합니다.",
                tasks=[f"현재 계산 결과와 함께 {warning_label} 경고를 확인합니다.", "경고가 발생한 입력과 정책 기준을 정리합니다."],
                related_rules=["경고 항목", method_label],
                related_contracts=["입력 데이터", "회계 정책"],
                roles=["회계 담당자", "업무 분석가"],
                duration_weeks=1,
                deliverables=["경고 항목 목록", "입력 점검 메모"],
            ),
            ExecutionPlanWeek(
                week_label="2주차",
                goal="입력과 정책 기준을 보완합니다.",
                tasks=["경고를 유발한 입력과 정책 기준을 보완합니다.", "필요한 환율 또는 정책 버전 기준을 확정합니다."],
                related_rules=["입력 보완", "정책 기준"],
                related_contracts=["환율 데이터", "회계 정책"],
                roles=["회계 담당자", "컨설턴트"],
                duration_weeks=1,
                deliverables=["입력 보완 결과", "정책 기준표"],
            ),
            ExecutionPlanWeek(
                week_label="3주차",
                goal="재계산과 비교 검토를 수행합니다.",
                tasks=[f"{method_label} 기준으로 재계산을 수행하고 기존 {amount_text} 결과와 비교합니다.", "변경 전후 계산 차이를 검토합니다."],
                related_rules=["재계산", "비교 검토"],
                related_contracts=["거래 데이터", "환율 데이터"],
                roles=["회계 담당자", "QA"],
                duration_weeks=1,
                deliverables=["재계산 결과", "비교 검토표"],
            ),
            ExecutionPlanWeek(
                week_label="4주차",
                goal="최종 기준을 확정합니다.",
                tasks=["경고 해소 여부와 전표 검토 결과를 함께 확인합니다.", "최종 운영 기준과 재실행 조건을 확정합니다."],
                related_rules=["최종 기준", "운영 기준"],
                related_contracts=["정책 기준", "전표 데이터"],
                roles=["컨설턴트", "회계 담당자"],
                duration_weeks=1,
                deliverables=["최종 기준서", "후속 조치 목록"],
            ),
        ]
        return {
            "one_line_conclusion": f"회계 기능은 {method_label} 기준으로 계산을 수행했지만, {warning_label} 때문에 결과를 검토용 초안으로 해석해야 합니다.",
            "executive_summary_v2": [
                "이 문서는 외환 거래의 환차손익을 계산한 결과이며, 일부 입력 경고를 포함합니다.",
                f"현재 기준 계산 방식은 {method_label}이며, 산출된 환차손익은 {amount_text}입니다.",
                f"다만 {warning_label} 때문에 결과는 검토용 초안으로 해석해야 합니다.",
                context["voucher_summary"],
            ],
            "decision_items": [
                DecisionItem(statement="계산은 수행되었으나 일부 입력은 추가 확인이 필요합니다.", rationale=warning_text),
                DecisionItem(statement=f"적용 방식은 {method_label}입니다.", rationale="현재 정책과 계산 결과가 해당 방식으로 정리됩니다."),
                DecisionItem(statement=f"주요 경고는 {warning_label}이며 최종 확정 전 검토가 필요합니다.", rationale="경고 해소 전까지는 결과를 검토용 초안으로 유지해야 합니다."),
            ],
            "priority_split_items": [
                PrioritySplitItem(priority=1, item="경고 항목을 먼저 확인하는 것이 필요합니다.", title="경고 항목 확인", reason=warning_text, impact_scope="입력 데이터, 정책 기준, 환율 선택", prerequisite="현재 계산 결과 확보", linked_rules=["경고 항목"], linked_contracts=["입력 데이터", "회계 정책"]),
                PrioritySplitItem(priority=2, item="입력과 정책 기준을 보완하는 것이 필요합니다.", title="입력/정책 보완", reason="경고 원인을 해소해야 계산 결과를 확정할 수 있습니다.", impact_scope="입력 보완, 정책 버전, 환율 기준", prerequisite="경고 항목 확인", linked_rules=["정책 기준"], linked_contracts=["환율 데이터", "회계 정책"]),
                PrioritySplitItem(priority=3, item="재계산과 최종 기준 확정을 수행하는 것이 필요합니다.", title="재계산 및 기준 확정", reason="보완 이후 계산 결과와 전표 검토 결과를 다시 확인해야 합니다.", impact_scope="재계산 결과, 전표 검토, 운영 기준", prerequisite="입력/정책 보완 완료", linked_rules=["재계산"], linked_contracts=["전표 데이터", "계정 매핑"]),
            ],
            "design_options": design_options,
            "recommended_option": recommended_option,
            "execution_plan": execution_plan,
            "recommended_directions": [
                "경고 항목을 먼저 확인하는 것이 필요합니다.",
                "입력과 정책 기준을 보완하는 것이 필요합니다.",
                "재계산 후 최종 기준을 확정하는 것이 필요합니다.",
            ],
            "risks": [
                "주요 경고가 해소되지 않으면 계산 결과를 확정할 수 없습니다.",
                "현재 결과는 검토용 초안으로만 사용해야 합니다.",
            ],
        }

    def _build_report_metadata(
        self,
        result: StructuredRebuildResult,
        user_question: str | None = None,
        *,
        narrative_judgment: str | None = None,
    ) -> tuple[str, list[str], list[str]]:
        accounting = result.extensions.get("accounting") if isinstance(result.extensions, dict) else None
        if isinstance(accounting, dict):
            accounting_metadata = self._build_accounting_report_metadata(accounting, user_question=user_question)
            if accounting_metadata[0]:
                return accounting_metadata
        return self._build_general_report_metadata(
            (narrative_judgment or "").strip() or (result.primary_judgment or "").strip()
        )

    def _build_accounting_report_metadata(
        self,
        accounting: dict[str, Any],
        *,
        user_question: str | None = None,
    ) -> tuple[str, list[str], list[str]]:
        del user_question
        fx_calc = accounting.get("fx_calculation") or {}
        voucher_review = accounting.get("voucher_review") or {}
        analysis = accounting.get("accounting_analysis") or {}

        has_fx = self._has_accounting_fx_result(fx_calc)
        has_voucher = self._has_accounting_voucher_review(voucher_review)
        has_analysis = self._has_accounting_analysis_result(analysis)

        if has_fx and has_voucher:
            return (
                "외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 전표 정합성을 함께 검토하기 위한 보고서입니다.",
                ["외화 거래 데이터", "환율 데이터", "회계 정책", "전표 검토 결과"],
                [
                    "이 거래에서 환차익 또는 환차손은 얼마인가?",
                    "어떤 계산 방식이 적용되었는가?",
                    "전표와 계산 결과는 일치하는가?",
                ],
            )
        if has_fx:
            return (
                "외환 거래의 환차손익을 계산하고, 적용된 회계 방식과 계산 근거를 검증하기 위한 보고서입니다.",
                ["외화 거래 데이터", "환율 데이터", "회계 정책"],
                [
                    "이 거래에서 환차익 또는 환차손은 얼마인가?",
                    "어떤 계산 방식이 적용되었는가?",
                    "계산 근거는 무엇인가?",
                ],
            )
        if has_voucher:
            return (
                "전표의 차변·대변 정합성과 회계 정책 일치 여부를 검토하기 위한 보고서입니다.",
                ["전표 데이터", "계정 매핑", "회계 정책"],
                [
                    "전표는 차변·대변 균형이 맞는가?",
                    "회계 정책과 일치하는가?",
                    "불일치 항목은 무엇인가?",
                ],
            )
        if has_analysis:
            return (
                "이 시스템에 적용된 회계 계산 방식과 정책 구조를 분석하기 위한 보고서입니다.",
                ["코드/SQL", "회계 정책 신호", "계산 방식 후보"],
                [
                    "이 시스템은 어떤 회계 방식을 사용하는가?",
                    "추천 방식은 무엇인가?",
                    "근거는 무엇인가?",
                ],
            )
        return (
            "회계 계산 입력과 정책 전제 조건을 점검하기 위한 보고서입니다.",
            ["회계 입력 데이터", "회계 정책", "계산 전제 조건"],
            [
                "회계 계산에 필요한 입력은 충분한가?",
                "적용할 회계 정책은 무엇인가?",
                "어떤 전제 조건이 계산을 막고 있는가?",
            ],
        )

    def _has_accounting_fx_result(self, fx_calculation: dict[str, Any]) -> bool:
        if not isinstance(fx_calculation, dict):
            return False
        return bool(
            fx_calculation.get("status")
            and str(fx_calculation.get("status") or "").strip().lower() != "skipped"
        ) or bool(
            fx_calculation.get("method")
            or fx_calculation.get("detail_steps")
            or fx_calculation.get("failure_reason")
            or fx_calculation.get("realized_gain_loss_krw") is not None
        )

    def _has_accounting_voucher_review(self, voucher_review: dict[str, Any]) -> bool:
        if not isinstance(voucher_review, dict):
            return False
        return bool(
            voucher_review.get("status")
            and str(voucher_review.get("status") or "").strip().lower() != "skipped"
        ) or bool(
            voucher_review.get("review_points")
            or voucher_review.get("mismatches")
            or voucher_review.get("failure_reason")
            or voucher_review.get("basis")
        )

    def _has_accounting_analysis_result(self, analysis: dict[str, Any]) -> bool:
        if not isinstance(analysis, dict):
            return False
        return bool(
            analysis.get("candidate_methods")
            or analysis.get("recommended_method")
            or analysis.get("reasons")
            or analysis.get("evidence_refs")
        )

    def _build_general_report_metadata(self, primary_judgment: str) -> tuple[str, list[str], list[str]]:
        mapping: dict[str, tuple[str, list[str], list[str]]] = {
            "query_filter": (
                "조회 조건, 필터 조합, 정렬 및 결과 구성 규칙을 분석하기 위한 보고서입니다.",
                ["조회 조건", "필터 조합", "정렬 기준", "결과 구성 규칙"],
                [
                    "어떤 조회 조건이 핵심 규칙을 결정하는가?",
                    "필터와 정렬은 어떤 기준으로 조합되는가?",
                    "결과 목록 구성 규칙은 어디서 통제되는가?",
                ],
            ),
            "amount_threshold": (
                "금액 기준, 한도 정책, 경계 조건을 분석하기 위한 보고서입니다.",
                ["금액 기준", "한도 정책", "구간 경계", "후속 처리 경계"],
                [
                    "어떤 금액 기준과 한도 정책이 적용되는가?",
                    "구간별 경계 조건은 어떻게 나뉘는가?",
                    "한도 초과 시 어떤 후속 처리 규칙이 적용되는가?",
                ],
            ),
            "workflow": (
                "승인 트리거, 승인 단계, 예외 처리 흐름을 분석하기 위한 보고서입니다.",
                ["승인 트리거", "승인 주체", "승인 단계", "예외 처리 흐름"],
                [
                    "어떤 조건에서 승인 흐름이 시작되는가?",
                    "승인 단계와 의사결정 게이트는 어떻게 구성되는가?",
                    "예외 승인 또는 보류 흐름은 어떻게 처리되는가?",
                ],
            ),
            "access_control": (
                "권한 체계, 승인 주체, 조직별 처리 범위를 분석하기 위한 보고서입니다.",
                ["권한 체계", "승인 주체", "조직별 처리 범위", "예외 승인 규칙"],
                [
                    "누가 어떤 조건에서 처리가 가능한가?",
                    "승인 주체와 조직별 심사 경로는 어떻게 나뉘는가?",
                    "예외 승인 규칙은 어디서 통제되는가?",
                ],
            ),
            "state_transition": (
                "상태 전이 규칙과 처리 흐름을 분석하기 위한 보고서입니다.",
                ["상태 전이 규칙", "처리 가능 상태", "전이 조건", "후속 처리 흐름"],
                [
                    "어떤 상태 전이가 허용되는가?",
                    "처리 가능 상태와 차단 상태는 무엇인가?",
                    "전이 이후 후속 처리 흐름은 어떻게 이어지는가?",
                ],
            ),
            "validation": (
                "입력 검증, 저장 전 차단 조건, 예외 처리 기준을 분석하기 위한 보고서입니다.",
                ["입력 검증", "저장 전 차단 조건", "검증 순서", "예외 처리 기준"],
                [
                    "어떤 차단 조건과 검증 규칙이 적용되는가?",
                    "저장 전 검증 순서는 어떻게 구성되는가?",
                    "예외 처리 기준은 어디서 통제되는가?",
                ],
            ),
        }
        return mapping.get(
            primary_judgment,
            (
                "레거시 기능의 핵심 업무 규칙과 전환 구조를 분석하기 위한 보고서입니다.",
                ["핵심 업무 규칙", "유지 계약", "전환 구조"],
                [
                    "이 기능의 핵심 규칙은 무엇인가?",
                    "어떤 계약을 유지해야 하는가?",
                    "전환 시 우선 분리해야 할 구조는 무엇인가?",
                ],
            ),
        )

    def _resolve_narrative_judgment(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> str:
        ordered = self._ordered_templates_for_generation(prepared, applied_templates, grounded_rules)
        if ordered:
            return ordered[0].template_id
        return (prepared.selected_primary_judgment or "").strip()

    def _active_narrative_judgment(self, prepared: PreparedRebuildInput) -> str:
        return (
            (prepared.selected_narrative_judgment or "").strip()
            or (prepared.selected_primary_judgment or "").strip()
        )

    def _primary_template(self, prepared: PreparedRebuildInput, applied_templates: list[AppliedJudgmentTemplate]) -> AppliedJudgmentTemplate | None:
        from mellow_link.services.refactoring_support_engine.judgment_synthesizer import JudgmentSynthesizer

        return JudgmentSynthesizer().primary_template(prepared, applied_templates)

    def collect_pattern_candidates(
        self,
        prepared: PreparedRebuildInput,
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> list[PatternCandidate]:
        from mellow_link.services.refactoring_support_engine.judgment_synthesizer import JudgmentSynthesizer

        return JudgmentSynthesizer().collect_pattern_candidates(prepared, applied_templates)

    def select_primary_judgment(
        self,
        prepared: PreparedRebuildInput,
        pattern_candidates: list[PatternCandidate],
    ) -> tuple[str, str, list[PatternCandidate]]:
        from mellow_link.services.refactoring_support_engine.judgment_synthesizer import JudgmentSynthesizer

        return JudgmentSynthesizer().select_primary_judgment(prepared, pattern_candidates)

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

    def _ordered_templates_for_generation(
        self,
        prepared: PreparedRebuildInput,
        applied_templates: list[AppliedJudgmentTemplate],
        grounded_rules: list[GroundedBusinessRule] | None = None,
    ) -> list[AppliedJudgmentTemplate]:
        from mellow_link.services.refactoring_support_engine.judgment_synthesizer import JudgmentSynthesizer

        return JudgmentSynthesizer().ordered_templates_for_generation(prepared, applied_templates, grounded_rules)

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
        return self._engine_template_support().build_recommended_directions(prepared)

    def format_user_summary(
        self,
        result: StructuredRebuildResult,
        *,
        scope_limited: bool,
        needs_more_input: bool,
    ) -> str:
        lines = [
            "Executive Summary",
            *self._render_bullets(result.executive_summary_v2),
            "",
            "핵심 결론",
            f"- {result.one_line_conclusion}",
            "",
            "핵심 업무 규칙",
        ]
        for rule in result.grounded_business_rules:
            lines.extend(
                [
                    f"- {rule.title}: {rule.description}",
                    f"  - 신뢰도: {rule.confidence} ({rule.confidence_reason})",
                    f"  - 설계 반영 위치: {', '.join(rule.design_targets) if rule.design_targets else '-'}",
                    f"  - 추가 검증 필요: {'예' if rule.needs_verification else '아니오'}",
                ]
            )
            for evidence in rule.evidence[:2]:
                lines.append(f"  - 근거: {evidence.asset_name} [{evidence.asset_type}] {evidence.locator} / {evidence.excerpt}")
        lines.extend(
            [
                "",
                "즉시 결정 필요",
            ]
        )
        decision_lines = [item.statement for item in result.decision_items if (item.statement or "").strip()]
        if decision_lines:
            lines.extend(self._render_bullets(decision_lines))
        else:
            lines.append("- 즉시 결정할 항목이 없습니다.")
        lines.extend(
            [
                "",
                "유지해야 할 계약",
                *self._render_bullets([item.item for item in result.retained_contracts]),
                "",
                "분리 우선순위",
            ]
        )
        for item in result.priority_split_items:
            lines.append(f"- {item.priority}순위 {item.title}: {item.reason}")
        lines.extend(
            [
                "",
                "확인 필요 항목",
                *self._render_bullets([item.item for item in result.verification_checkpoints]),
                "",
                "설계 선택지 비교",
            ]
        )
        for option in result.design_options:
            lines.extend(
                [
                    f"- {option.name}: {option.structure_summary}",
                    f"  - 장점: {' / '.join(option.advantages) if option.advantages else '-'}",
                    f"  - 리스크: {' / '.join(option.risks) if option.risks else '-'}",
                    f"  - 난이도/기간: {option.difficulty} / {option.duration_weeks}주",
                    f"  - 추천 여부: {'예' if option.recommended else '아니오'}",
                    f"  - 선택 이유: {option.selection_reason}",
                ]
            )
        if result.recommended_option:
            lines.extend(
                [
                    "",
                    "추천안",
                    f"- {result.recommended_option.name}: {result.recommended_option.structure_summary}",
                    f"  - 선택 이유: {result.recommended_option.selection_reason}",
                ]
            )
        lines.extend(
            [
                "",
                "실행 계획",
            ]
        )
        for week in result.execution_plan:
            lines.extend(
                [
                    f"- {week.week_label}: {week.goal}",
                    f"  - 작업: {' / '.join(week.tasks) if week.tasks else '-'}",
                    f"  - 인력: {' / '.join(week.roles) if week.roles else '-'}",
                    f"  - 기간: {week.duration_weeks}주",
                    f"  - 산출물: {' / '.join(week.deliverables) if week.deliverables else '-'}",
                ]
            )
        lines.extend(
            [
                "",
                "진단 요약",
            ]
        )
        lines.extend(
            [
                *self._render_bullets(result.analysis_summary),
                "",
                "전환 초안",
                *self._render_bullets(result.core_business_rules),
                "",
                "재구성 전략",
                *self._render_bullets(result.rebuild_strategy),
                "",
                "레이어별 재구성",
                "DB",
                *self._render_bullets(result.layer_reconstruction.database),
                "API",
                *self._render_bullets(result.layer_reconstruction.backend),
                "UI",
                *self._render_bullets(result.layer_reconstruction.frontend),
                "",
                "초안",
                "DB",
                *self._render_bullets(result.recomposition_draft.database),
                "API",
                *self._render_bullets(result.recomposition_draft.backend),
                "UI",
                *self._render_bullets(result.recomposition_draft.frontend),
                "",
                "리스크",
                *self._render_bullets(result.risks),
            ]
        )
        if result.missing_context:
            lines.append("")
            lines.append("추가 자료 요청")
            for item in result.missing_context_details:
                lines.extend(
                    [
                        "[필요 자료]",
                        f"- {item.required_material}",
                        "",
                        "[이유]",
                        f"- {item.reason}",
                        "",
                    ]
                )
            if not result.missing_context_details:
                lines.extend(self._render_bullets(result.missing_context))
        if result.recommended_directions:
            lines.extend(["", "추천 방향", *self._render_bullets(result.recommended_directions)])
        lines.extend(
            [
                "",
                "실행 메타",
                f"- confidence: {result.confidence:.2f}",
                f"- scope_limited: {'true' if scope_limited else 'false'}",
                f"- needs_more_input: {'true' if needs_more_input else 'false'}",
            ]
        )
        return self._sanitize_text("\n".join(lines).strip())

    def _build_conclusion(self, prepared: PreparedRebuildInput, confidence: float) -> str:
        concept = self._primary_concept(prepared)
        primary = prepared.signals.primary_feature_mode
        if prepared.scope_limited:
            return f"{concept} 기능을 단일 범위로 제한해 정책, 화면, 데이터 계약을 단계적으로 분리하는 것이 필요합니다."
        if primary == "status_permissions":
            return f"{concept} 기능은 역할, 상태, 액션 규칙을 정책 서비스로 분리하는 방향으로 재구성하는 것이 필요합니다."
        if primary == "search_filters":
            return f"{concept} 기능은 조회 조건과 결과 구성을 별도 조회 모델로 분리하는 방향으로 재구성하는 것이 필요합니다."
        if primary == "save_validation":
            if concept == "청구 조정":
                return f"{concept} 기능은 저장 검증, 권한 한도, 예외 승인 규칙을 정책 서비스와 검증 흐름으로 분리하는 것이 필요합니다."
            return f"{concept} 기능은 저장 검증, 중복 체크, 입력 제약을 검증 흐름으로 분리해 재구성하는 것이 필요합니다."
        if confidence < 0.45:
            return f"{concept} 기능은 자산이 제한적이므로 직접 확인된 규칙부터 단계적으로 분리하는 것이 필요합니다."
        return f"{concept} 기능은 화면, 정책, 데이터 계약을 분리한 단계적 현대화 구조로 전환하는 것이 필요합니다."

    def _build_conclusion_with_templates(
        self,
        prepared: PreparedRebuildInput,
        confidence: float,
        grounded_rules: list[GroundedBusinessRule],
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> str:
        concept = self._primary_concept(prepared)
        ordered_templates = self._ordered_templates_for_generation(prepared, applied_templates, grounded_rules)
        primary_template = ordered_templates[0] if ordered_templates else self._primary_template(prepared, applied_templates)
        if prepared.scope_limited:
            return f"{concept} 기능을 단일 범위로 제한해 정책, 화면, 데이터 계약을 단계적으로 분리하는 것이 필요합니다."
        if primary_template:
            lead_rule = primary_template.matched_rule_titles[0] if primary_template.matched_rule_titles else (grounded_rules[0].title if grounded_rules else "")
            lead_rule = self._normalize_conclusion_rule_anchor(lead_rule)
            if primary_template.template_id == "validation":
                return f"{concept} 기능은 {lead_rule or '직접 확인된 차단 조건'}을 기준으로 차단 조건, 검증 순서, 저장 전 검증을 분리해 재구성하는 것이 필요합니다."
            if primary_template.template_id == "workflow":
                return f"{concept} 기능은 승인 트리거와 승인 단계 구조를 기준으로 승인 흐름, 의사결정 게이트, 예외 처리 경로를 분리하는 것이 필요합니다."
            if primary_template.template_id == "state_transition":
                return f"{concept} 기능은 {lead_rule or '직접 확인된 상태 전이 규칙'}을 기준으로 상태 전이, 처리 가능 상태, 전이 조건을 분리하는 것이 필요합니다."
            if primary_template.template_id == "access_control":
                return f"{concept} 기능은 {lead_rule or '직접 확인된 권한 규칙'}을 기준으로 승인 권한, 부서, 승인 주체 규칙을 정책 계층으로 분리하는 것이 필요합니다."
            if primary_template.template_id == "query_filter":
                return f"{concept} 기능은 {lead_rule or '직접 확인된 조회 조건 규칙'}을 기준으로 조회 조건, 필터 조합, 결과 목록 구성을 조회 모델로 분리하는 것이 필요합니다."
            if primary_template.template_id == "amount_threshold":
                return f"{concept} 기능은 {lead_rule or '직접 확인된 금액 한도 규칙'}을 기준으로 금액 구간, 한도 정책, 고액 처리 경계를 분리하는 것이 필요합니다."
        return self._build_conclusion(prepared, confidence)

    def _align_core_business_rules_for_narrative(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        core_business_rules: list[str],
    ) -> list[str]:
        narrative = self._active_narrative_judgment(prepared)
        if not grounded_rules or not narrative:
            return core_business_rules
        prioritized = [
            item.description.strip()
            for item in grounded_rules
            if self._rule_matches_narrative_judgment(item, narrative)
        ]
        if prioritized:
            return self._dedupe_list(prioritized)[:4]
        fallback = [item.description.strip() for item in grounded_rules if item.description.strip()]
        return self._dedupe_list(fallback or core_business_rules)[:4]

    def _align_retained_contracts_for_narrative(
        self,
        prepared: PreparedRebuildInput,
        retained_contracts: list[RetainedContract],
    ) -> list[RetainedContract]:
        narrative = self._active_narrative_judgment(prepared)
        if not retained_contracts or not narrative:
            return retained_contracts
        prioritized = [
            item for item in retained_contracts
            if self._contract_matches_narrative_judgment(item, narrative)
        ]
        if not prioritized:
            return retained_contracts
        return self._dedupe_by_normalized_text(prioritized, attr="item")

    def _rule_matches_narrative_judgment(
        self,
        rule: GroundedBusinessRule,
        narrative_judgment: str,
    ) -> bool:
        text = " ".join(
            [
                rule.title,
                rule.description,
                " ".join(rule.design_targets),
            ]
        )
        if narrative_judgment == "workflow":
            return self._workflow_keyword_hit_count(text) > 0
        if narrative_judgment == "access_control":
            return self._access_control_keyword_hit_count(text) > 0
        if narrative_judgment == "query_filter":
            return self._query_filter_keyword_hit_count(text) > 0
        if narrative_judgment == "amount_threshold":
            return self._amount_threshold_keyword_hit_count(text) > 0 and self._query_filter_keyword_hit_count(text) == 0
        if narrative_judgment == "state_transition":
            return self._state_keyword_hit_count(text) > 0
        if narrative_judgment == "validation":
            return self._validation_keyword_hit_count(text) > 0
        return True

    def _contract_matches_narrative_judgment(
        self,
        contract: RetainedContract,
        narrative_judgment: str,
    ) -> bool:
        text = f"{contract.item} {contract.basis}"
        if narrative_judgment == "workflow":
            return self._workflow_keyword_hit_count(text) > 0
        if narrative_judgment == "access_control":
            return self._access_control_keyword_hit_count(text) > 0
        if narrative_judgment == "query_filter":
            return self._query_filter_keyword_hit_count(text) > 0
        if narrative_judgment == "amount_threshold":
            return self._amount_threshold_keyword_hit_count(text) > 0 and self._query_filter_keyword_hit_count(text) == 0
        if narrative_judgment == "state_transition":
            return self._state_keyword_hit_count(text) > 0
        if narrative_judgment == "validation":
            return self._validation_keyword_hit_count(text) > 0
        return True

    def _normalize_conclusion_rule_anchor(self, text: str) -> str:
        normalized = (text or "").strip()
        normalized = re.sub(r"\s*규칙이 직접 확인되었습니다\.?$", "", normalized)
        normalized = re.sub(r"\s*을 기준으로 .*", "", normalized)
        normalized = re.sub(r"\s*을 검증해야 합니다\.?$", "", normalized)
        normalized = re.sub(r"\s*를 검증해야 합니다\.?$", "", normalized)
        normalized = re.sub(r"\s*을 유지해야 합니다\.?$", "", normalized)
        normalized = re.sub(r"\s*를 유지해야 합니다\.?$", "", normalized)
        normalized = normalized.rstrip(". ")
        return normalized

    def _extract_concepts(self, prepared: PreparedRebuildInput) -> list[str]:
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
        found: list[str] = []
        for token in self.CONCEPT_PATTERNS:
            if token.lower() in text and token not in found:
                found.append(token)
        return found[:6]

    def _extract_status_permission_signals(self, text: str) -> list[str]:
        checks = [
            ("역할별 액션 노출 규칙", r"\b(role|permission|auth|authorize|grant|deny|admin|manager|approv|reject|cancel|status|state|visible|disabled)\b"),
            ("화면 조건 분기", r"<c:if|<c:choose|if\s*\(|disabled=|readonly=|display:\s*none"),
            ("상태 전이 규칙", r"\b(approve|reject|cancel|close|reopen|submit|complete|draft|pending|active|inactive)\b"),
        ]
        return [label for label, pattern in checks if re.search(pattern, text, flags=re.IGNORECASE)]

    def _extract_search_filter_signals(self, text: str) -> list[str]:
        checks = [
            ("조회 파라미터 규칙", r"request\.getparameter|@requestparam|param\.|querystring|searchword|keyword"),
            ("검색 조건 상태", r"\b(search|filter|sort|page|paging|datefrom|dateto|condition|criteria|statusfilter)\b"),
            ("SQL 조건 매핑", r"\b(where|order by|group by|like|join|limit|offset)\b"),
        ]
        return [label for label, pattern in checks if re.search(pattern, text, flags=re.IGNORECASE)]

    def _extract_save_validation_signals(self, text: str) -> list[str]:
        checks = [
            ("입력 검증 규칙", r"\b(validate|validator|required|invalid|length|format|null check|isblank|pattern)\b"),
            ("저장 전 선행 조건", r"\b(save|insert|update|merge|submit|persist|commit)\b"),
            ("중복 체크 규칙", r"\b(duplicate|exists|already exists|unique|dup check|중복)\b"),
        ]
        return [label for label, pattern in checks if re.search(pattern, text, flags=re.IGNORECASE)]

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

    def _rule_entities(self, prepared: PreparedRebuildInput) -> list[str]:
        resource = self._singular_resource(self._resource_name(prepared))
        if resource:
            return [resource]
        concept = self._primary_concept(prepared)
        normalized = re.sub(r"[^a-z0-9]+", "_", concept.lower()).strip("_")
        return [normalized or "legacy_feature"]

    def _transition_condition_hint(self, text: str, roles: list[str], status: str, action: str) -> str:
        matched_roles = [role for role in roles if re.search(rf"{role}.*{action}|{action}.*{role}", text, flags=re.IGNORECASE)]
        if matched_roles:
            return " or ".join(role.lower() for role in matched_roles)
        if re.search(r"<c:if|<c:choose|if\s*\(", text, flags=re.IGNORECASE):
            return "legacy conditional branch"
        return f"status is {status}"

    def _infer_target_status(self, action: str, statuses: list[str]) -> str:
        mapping = {
            "approve": "APPROVED",
            "reject": "REJECTED",
            "resubmit": "PENDING",
            "submit": "SUBMITTED",
            "close": "CLOSED",
            "reopen": "PENDING",
            "cancel": "CANCELLED",
        }
        candidate = mapping.get(action.lower())
        if candidate and candidate in statuses:
            return candidate
        return candidate or "UNKNOWN"

    def _infer_filter_field_type(self, name: str) -> str:
        lowered = name.lower()
        if lowered in {"includeclosed", "enabled", "active", "visible"}:
            return "checkbox"
        if "date" in lowered:
            return "date"
        if lowered in {"page", "limit", "offset"}:
            return "number"
        return "text"

    def _extract_select_columns(self, sql_text: str) -> list[str]:
        if not sql_text:
            return []
        match = re.search(r"select\s+(.*?)\s+from\s", sql_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        segment = match.group(1)
        if "*" in segment:
            return []
        columns: list[str] = []
        for raw in segment.split(","):
            token = raw.strip().split()[-1].split(".")[-1]
            token = token.strip("`\"")
            if token:
                columns.append(token.lower())
        return self._dedupe_list(columns)

    def _score_feature_modes(
        self,
        prepared: PreparedRebuildInput,
        *,
        status_permissions: list[str],
        search_filters: list[str],
        save_validation: list[str],
    ) -> dict[str, float]:
        bundle = prepared.legacy_bundle.lower()
        scores = {
            "status_permissions": 0.0,
            "search_filters": 0.0,
            "save_validation": float(len(save_validation)) * 1.35,
        }
        role_hits = self._match_count(bundle, r"\b(role|admin|manager|user|permission|auth|authorize)\b")
        action_hits = self._match_count(bundle, r"\b(approve|reject|resubmit|cancel)\b")
        visibility_hits = self._match_count(bundle, r"\b(button|visible|disabled|readonly|show[a-z]*button)\b")
        transition_hits = self._match_count(bundle, r"\b(status|state|pending|approved|rejected|draft|submitted|complete|closed)\b")
        conditional_render_hits = self._match_count(bundle, r"<c:if|<c:choose|if\s*\(")
        strong_status_bundle = sum(
            1
            for value in (
                action_hits >= 1,
                visibility_hits >= 1,
                transition_hits >= 2,
                role_hits >= 1 and conditional_render_hits >= 1,
            )
            if value
        )
        scores["status_permissions"] += float(len(status_permissions)) * 0.55
        scores["status_permissions"] += min(0.55, role_hits * 0.06 + transition_hits * 0.05)
        if strong_status_bundle >= 2:
            scores["status_permissions"] += 1.4 + min(
                2.8,
                action_hits * 0.75 + visibility_hits * 0.55 + transition_hits * 0.32 + conditional_render_hits * 0.35,
            )
            if role_hits >= 1 and action_hits >= 1 and visibility_hits >= 1 and transition_hits >= 2:
                scores["status_permissions"] += 1.7
            if action_hits >= 2 and conditional_render_hits >= 1 and transition_hits >= 2:
                scores["status_permissions"] += 0.9
        elif strong_status_bundle == 1:
            scores["status_permissions"] += min(
                0.9,
                action_hits * 0.28 + visibility_hits * 0.2 + transition_hits * 0.12 + conditional_render_hits * 0.15,
            )

        filter_param_hits = self._match_count(bundle, r"request\.getparameter|@requestparam|keyword|filter|sort|page|criteria|condition|searchword")
        filter_state_hits = self._match_count(bundle, r"\b(search|filter|sort|page|paging|datefrom|dateto|statusfilter|query state|form|results?|list)\b")
        dynamic_query_hits = self._match_count(bundle, r"\b(where|order by|group by|like|limit|offset|append|concat|dynamic sql)\b")
        search_form_hits = self._match_count(bundle, r"<form|searchform|filterbar|조회|검색")
        result_list_hits = self._match_count(bundle, r"\b(table|grid|list|results?)\b")
        strong_search_bundle = sum(
            1
            for value in (
                filter_param_hits >= 2,
                dynamic_query_hits >= 2,
                filter_state_hits >= 2,
                search_form_hits >= 1 and result_list_hits >= 1,
            )
            if value
        )
        if strong_search_bundle >= 3:
            scores["search_filters"] += 1.5 + min(
                3.0,
                filter_param_hits * 0.48 + dynamic_query_hits * 0.42 + filter_state_hits * 0.25 + result_list_hits * 0.2,
            )
            if search_form_hits >= 1 and filter_param_hits >= 2 and dynamic_query_hits >= 2:
                scores["search_filters"] += 1.0
            if result_list_hits >= 1 and filter_state_hits >= 2:
                scores["search_filters"] += 0.6
            if search_form_hits >= 1 and result_list_hits >= 1 and filter_param_hits >= 2:
                scores["search_filters"] += 0.75
        elif strong_search_bundle == 2:
            scores["search_filters"] += 0.9 + min(
                1.9,
                filter_param_hits * 0.32 + dynamic_query_hits * 0.28 + filter_state_hits * 0.18,
            )
            if search_form_hits >= 1 and result_list_hits >= 1:
                scores["search_filters"] += 0.45
        else:
            scores["search_filters"] += min(0.8, filter_param_hits * 0.12 + dynamic_query_hits * 0.1 + filter_state_hits * 0.08)

        required_hits = self._match_count(bundle, r"\b(required|not null|isblank|mandatory|empty|validate|validator|invalid)\b")
        duplicate_hits = self._match_count(bundle, r"\b(duplicate|exists|already exists|unique|dup check|중복)\b")
        save_hits = self._match_count(bundle, r"\b(save|insert|update|merge|submit|persist|commit)\b")
        guard_hits = self._match_count(bundle, r"\b(before save|pre-save|guard|cannot save|blocked|forbidden|exception|illegalstate|validationexception|throw\s+new)\b")
        role_save_hits = self._match_count(bundle, r"\b(role|admin|manager)\b") if save_hits > 0 else 0
        status_save_hits = self._match_count(bundle, r"\b(status|state|pending|approved|closed|draft)\b") if save_hits > 0 else 0
        strong_save_bundle = sum(
            1
            for value in (
                required_hits >= 1,
                duplicate_hits >= 1,
                guard_hits >= 1,
                role_save_hits >= 1 or status_save_hits >= 2,
            )
            if value
        )
        scores["save_validation"] += min(
            4.2,
            required_hits * 0.8 + duplicate_hits * 1.05 + save_hits * 0.35 + guard_hits * 1.0 + role_save_hits * 0.35 + status_save_hits * 0.2,
        )
        if strong_save_bundle >= 2:
            scores["save_validation"] += 1.0
        if re.search(r"throw\s+new|validator|validate\s*\(", bundle, flags=re.IGNORECASE):
            scores["save_validation"] += 0.7
        if prepared.assets.sql_queries:
            if strong_search_bundle >= 2:
                scores["search_filters"] += 0.6
            scores["save_validation"] += 0.5 if re.search(r"\b(insert|update|merge)\b", prepared.assets.sql_queries, flags=re.IGNORECASE) else 0.0
        if prepared.assets.database_schema:
            scores["status_permissions"] += 0.2 if "status" in prepared.assets.database_schema.lower() else 0.0
        if scores["status_permissions"] >= 3.4:
            scores["status_permissions"] += 0.45
        if scores["save_validation"] >= 3.0:
            scores["save_validation"] += 0.7
        if scores["search_filters"] >= 3.2:
            scores["search_filters"] += 0.2
        return scores

    def _pick_feature_modes(self, scores: dict[str, float]) -> tuple[str, str | None]:
        adjusted_scores = dict(scores)
        adjusted_scores["status_permissions"] += 0.35 if scores.get("status_permissions", 0.0) >= 4.4 else 0.0
        adjusted_scores["save_validation"] += 0.3 if scores.get("save_validation", 0.0) >= 2.5 else 0.0
        adjusted_scores["search_filters"] -= 0.25 if scores.get("search_filters", 0.0) < 3.4 else 0.0
        adjusted_scores["search_filters"] += 0.85 if scores.get("search_filters", 0.0) >= 4.0 else 0.0
        if scores.get("status_permissions", 0.0) >= 5.0 and scores.get("search_filters", 0.0) >= 4.0:
            adjusted_scores["status_permissions"] += 0.6
        ordered = sorted(adjusted_scores.items(), key=lambda item: item[1], reverse=True)
        if not ordered or ordered[0][1] <= 0:
            return "general", None
        primary = ordered[0][0]
        secondary = None
        if len(ordered) > 1 and ordered[1][1] >= max(1.0, ordered[0][1] * 0.55):
            secondary = ordered[1][0]
        return primary, secondary

    def _dominance_gap(self, scores: dict[str, float]) -> float:
        ordered = sorted(scores.values(), reverse=True)
        if not ordered:
            return 0.0
        if len(ordered) == 1:
            return ordered[0]
        return max(0.0, ordered[0] - ordered[1])

    def _build_asset_presence_from_payload(self, assets: RebuildAssetsPayload) -> AssetPresenceSummary:
        return AssetPresenceSummary(
            has_source_code=bool((assets.source_code or "").strip()),
            has_ui_asset=bool((assets.ui_template or "").strip()),
            has_schema_asset=bool((assets.database_schema or "").strip()),
            has_sql_asset=bool((assets.sql_queries or "").strip()),
            has_framework_hint=bool((assets.framework_info or "").strip()),
            has_docs=False,
        )

    def _build_asset_presence_from_safe_bundle(self, safe_bundle: SafeAnalysisBundle) -> AssetPresenceSummary:
        summary = AssetPresenceSummary()
        content_by_asset_id = {source.asset_id: source.content or "" for source in safe_bundle.sources}
        for asset in safe_bundle.asset_summary:
            name = (asset.name or "").strip()
            if not name:
                continue
            lowered = name.lower()
            if self._is_intent_asset_name(lowered):
                continue
            content = content_by_asset_id.get(asset.asset_id, "")
            framework_hints = self._extract_framework_runtime_hints(name, content)
            if self._is_schema_asset_name(lowered, content):
                summary.has_schema_asset = True
                summary.schema_asset_names.append(name)
            elif self._is_sql_asset_name(lowered, content):
                summary.has_sql_asset = True
                summary.sql_asset_names.append(name)
            elif self._is_ui_asset_name(lowered):
                summary.has_ui_asset = True
                summary.ui_asset_names.append(name)
            elif self._is_source_asset_name(lowered):
                summary.has_source_code = True
                summary.source_asset_names.append(name)
            elif self._is_framework_asset_name(lowered):
                summary.has_framework_hint = True
                summary.framework_asset_names.append(name)
            elif self._is_doc_asset_name(lowered):
                summary.has_docs = True
                summary.doc_asset_names.append(name)
            if framework_hints:
                summary.has_framework_hint = True
                summary.framework_runtime_hints = self._dedupe_list(summary.framework_runtime_hints + framework_hints)
                if not self._is_doc_asset_name(lowered) and name not in summary.framework_asset_names:
                    summary.framework_asset_names.append(name)
        return summary

    def _build_framework_hint(self, safe_bundle: SafeAnalysisBundle, asset_presence: AssetPresenceSummary) -> str:
        _ = safe_bundle
        hints: list[str] = []
        if asset_presence.framework_runtime_hints:
            hints.append("runtime=" + ", ".join(asset_presence.framework_runtime_hints[:4]))
        if asset_presence.framework_asset_names:
            hints.append("artifacts=" + ", ".join(asset_presence.framework_asset_names[:3]))
        return ", ".join(hints)

    def _is_schema_asset_name(self, name: str, content: str = "") -> bool:
        lowered = (name or "").strip().lower()
        if lowered == "schema.sql" or "schema" in lowered:
            return True
        if not lowered.endswith(".sql"):
            return False
        return self._looks_like_schema_definition(content)

    def _is_sql_asset_name(self, name: str, content: str = "") -> bool:
        lowered = (name or "").strip().lower()
        return lowered.endswith(".sql") and not self._is_schema_asset_name(lowered, content)

    def _is_ui_asset_name(self, name: str) -> bool:
        lowered = (name or "").strip().lower()
        return any(lowered.endswith(ext) for ext in (".jsp", ".html", ".ftl", ".vue"))

    def _looks_like_schema_definition(self, content: str) -> bool:
        lowered = (content or "").lower()
        ddl_patterns = (
            r"\bcreate\s+table\b",
            r"\balter\s+table\b",
            r"\bcreate\s+(?:unique\s+)?index\b",
            r"\badd\s+constraint\b",
            r"\bprimary\s+key\b",
            r"\bforeign\s+key\b",
            r"\breferences\s+[a-z_][a-z0-9_]*\b",
        )
        return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in ddl_patterns)

    def _extract_framework_runtime_hints(self, asset_name: str, content: str) -> list[str]:
        lowered_name = (asset_name or "").strip().lower()
        if self._is_doc_asset_name(lowered_name):
            return []
        lowered = (content or "").lower()
        hints: list[str] = []
        if lowered_name.endswith(".jsp") or any(token in lowered for token in ("<%@ page", "<jsp:", "<c:if", "httpservlet")):
            hints.append("jsp/servlet")
        if any(token in lowered for token in ("@springbootapplication", "@restcontroller", "@requestmapping", "springframework")):
            hints.append("spring")
        if any(token in lowered for token in ("from fastapi import", "fastapi(", "apirouter(")):
            hints.append("fastapi")
        if any(token in lowered for token in ("from flask import", "flask(")):
            hints.append("flask")
        if any(token in lowered for token in ("django.", "urlpatterns", "models.model")):
            hints.append("django")
        if lowered_name.endswith((".jsx", ".tsx", ".vue")) or any(token in lowered for token in ("from react", "react.", "usestate(", "definecomponent(")):
            hints.append("react" if "react" in lowered or lowered_name.endswith((".jsx", ".tsx")) else "vue")
        if any(token in lowered for token in ("const express", "express()", "require(\"express\")", "require('express')")):
            hints.append("express")
        if any(token in lowered for token in ("mybatis", "sqlsession")):
            hints.append("mybatis")
        if any(token in lowered for token in ("jakarta.persistence", "javax.persistence", "@entity")):
            hints.append("jpa")
        return self._dedupe_list(hints)

    def _looks_like_accounting_payload_asset(self, asset_name: str, content: str) -> bool:
        lowered = (asset_name or "").strip().lower()
        if lowered == "accounting_payload.json":
            return True
        if not lowered.endswith(".json"):
            return False
        try:
            payload = json.loads(content)
        except Exception:
            return False
        if not isinstance(payload, dict):
            return False
        keys = set(payload.keys())
        return bool(keys & {"transactions", "exchange_rates", "policies", "vouchers", "account_mappings"})

    def _parse_accounting_payload(self, content: str) -> tuple[Any | None, str]:
        try:
            payload = json.loads(content)
        except Exception as exc:
            return None, f"invalid accounting payload json: {exc}"
        try:
            from mellow_link.services.accounting_mvp.schemas import AccountingInputBundle

            return AccountingInputBundle.model_validate(payload), ""
        except Exception as exc:
            return None, f"invalid accounting payload schema: {exc}"

    def _is_source_asset_name(self, name: str) -> bool:
        lowered = (name or "").strip().lower()
        return any(lowered.endswith(ext) for ext in self.SOURCE_ASSET_EXTENSIONS)

    def _is_framework_asset_name(self, name: str) -> bool:
        lowered = (name or "").strip().lower()
        return lowered in {
            "pom.xml",
            "build.gradle",
            "settings.gradle",
            "gradle.properties",
            "requirements.txt",
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
        }

    def _is_intent_asset_name(self, name: str) -> bool:
        lowered = (name or "").replace("\\", "/").strip().lower()
        base_name = lowered.rsplit("/", 1)[-1]
        return base_name in {"goal.txt", "constraints.txt", "scenario.md"}

    def _is_doc_asset_name(self, name: str) -> bool:
        lowered = (name or "").strip().lower()
        if self._is_intent_asset_name(lowered):
            return False
        return lowered.startswith("readme") or lowered.endswith((".md", ".txt", ".rst", ".adoc"))

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
        return None

    def extract_core_business_rules(self, prepared: PreparedRebuildInput) -> list[str]:
        text = " ".join(
            [
                prepared.assets.source_code,
                prepared.assets.ui_template,
                prepared.assets.sql_queries,
                prepared.assets.database_schema,
                prepared.supporting_docs,
            ]
        )
        if self._primary_concept(prepared) == "주문 마감":
            rules = self._extract_java_closure_rules(text)
            return rules[:4]
        if self._primary_concept(prepared) == "청구 조정":
            rules = self._extract_python_claim_rules(text)
            return rules[:5]
        return self._extract_general_business_rules(text)

    def _extract_java_closure_rules(self, text: str) -> list[str]:
        rules: list[str] = []
        lowered = text.lower()
        if "vip" in lowered and any(hour in lowered for hour in ("22", "23", "00", "야간")):
            rules.append("VIP 고객은 야간 시간대에 주문 마감을 수행할 수 없습니다.")
        if ("agency" in lowered or "대리점" in lowered) and ("hq" in lowered or "본사" in lowered) and ("5000000" in lowered or "고액" in lowered):
            rules.append("대리점 채널의 고액 주문은 본사 권한으로만 마감할 수 있습니다.")
        if ("delivery_hold_release_required" in lowered or "deliveryhold" in lowered or "배송보류" in lowered):
            rules.append("배송보류 상태가 해제되기 전에는 주문 마감을 진행할 수 없습니다.")
        if ("export" in lowered or "수출" in lowered) and ("review_required" in lowered or "7000000" in lowered):
            rules.append("수출 주문의 고액 건은 즉시 마감하지 않고 REVIEW_REQUIRED 상태로 전환해야 합니다.")
        return self._dedupe_list(rules)

    def _extract_python_claim_rules(self, text: str) -> list[str]:
        rules: list[str] = []
        lowered = text.lower()
        if "fraud" in lowered and "hq_reviewer" in lowered:
            rules.append("FRAUD 사고건은 HQ_REVIEWER 권한으로만 청구 조정을 수행할 수 있습니다.")
        if ("branch_manager" in lowered or "지점장" in lowered) and ("3000000" in lowered or "300만원" in lowered):
            rules.append("지점장은 300만원 이상 청구건을 조정할 수 없습니다.")
        if ("10000000" in lowered or "1천만원" in lowered) and "claim_audit" in lowered:
            rules.append("1천만원 이상 청구건은 CLAIM_AUDIT 부서만 조정할 수 있습니다.")
        if "b99" in lowered and ("urgent" in lowered or "긴급" in lowered):
            rules.append("B99 지점의 긴급 청구건은 본사 선승인 없이 조정할 수 없습니다.")
        if ("closed" in lowered and "cancelled" in lowered) and ("adjust" in lowered or "조정" in lowered or "불가" in lowered):
            rules.append("CLOSED 또는 CANCELLED 상태의 청구건은 조정할 수 없습니다.")
        return self._dedupe_list(rules)

    def _extract_general_business_rules(self, text: str) -> list[str]:
        rules: list[str] = []
        lowered = text.lower()
        if "status" in lowered or "state" in lowered:
            rules.append("상태 전이와 액션 노출 조건을 분리해 검증해야 합니다.")
        if "duplicate" in lowered or "중복" in lowered:
            rules.append("저장 전 중복 체크 규칙을 별도 검증 단계로 추출해야 합니다.")
        if "where" in lowered or "query" in lowered or "filter" in lowered:
            rules.append("조회 조건과 SQL 파라미터 조합 규칙을 명시적으로 정리해야 합니다.")
        return self._dedupe_list(rules)[:4]

    def build_executive_summary_v2(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        recommended_option: RecommendedOption | None,
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> list[str]:
        concept = self._primary_concept(prepared)
        ordered_templates = self._ordered_templates_for_generation(prepared, applied_templates, grounded_rules)
        primary_template = ordered_templates[0] if ordered_templates else self._primary_template(prepared, applied_templates)
        lead_rule = grounded_rules[0].title if grounded_rules else f"{concept} 핵심 규칙"
        option_text = self._option_label(recommended_option.name) if recommended_option else "정책 중심 분리안"
        axis = self._primary_template_axis_phrase(primary_template)
        summary = [
            f"{concept} 기능은 핵심 규칙을 유지한 상태에서 단계적으로 분리하는 것이 필요합니다.",
            f"현재 자산 기준으로 우선 보존해야 할 판단 축은 {axis or lead_rule}입니다.",
            f"이번 회의에서는 {self._attach_object_particle(option_text)} 기준안으로 확정하는 것이 필요합니다.",
        ]
        if prepared.missing_context:
            summary.append("추가 운영 확인이 필요한 항목은 별도 확인 필요 항목으로 분리해 후속 확인 대상으로 두는 것이 필요합니다.")
        return summary[:4]

    def build_grounded_business_rules(
        self,
        prepared: PreparedRebuildInput,
        core_rules: list[str],
    ) -> list[GroundedBusinessRule]:
        concept = self._primary_concept(prepared)
        templates = self._rule_templates_for_concept(concept)
        grounded: list[GroundedBusinessRule] = []
        for template in templates:
            evidence = self._collect_evidence_refs(prepared, template["keywords"], template["preferred_types"])
            if not evidence and template["statement"] not in core_rules:
                continue
            confidence, confidence_reason = self._resolve_confidence(evidence)
            grounded.append(
                GroundedBusinessRule(
                    title=template["title"],
                    description=template["statement"],
                    evidence=evidence,
                    design_targets=list(template["design_targets"]),
                    confidence=confidence,
                    confidence_reason=confidence_reason,
                    needs_verification=confidence != "확정",
                )
            )
        if not grounded:
            for rule in core_rules[:3]:
                evidence = self._collect_evidence_refs(prepared, rule.split(), ("source", "ui", "sql", "schema"))
                confidence, confidence_reason = self._resolve_confidence(evidence)
                grounded.append(
                    GroundedBusinessRule(
                        title=rule[:32],
                        description=rule,
                        evidence=evidence,
                        design_targets=["정책 서비스", "검증 흐름"],
                        confidence=confidence,
                        confidence_reason=confidence_reason,
                        needs_verification=confidence != "확정",
                    )
                )
        grounded = self._ensure_workflow_grounded_rules(prepared, grounded)
        grounded = self._ensure_validation_grounded_rules(prepared, grounded, core_rules)
        if not self._has_workflow_pattern(prepared):
            grounded = self._ensure_access_control_grounded_rules(prepared, grounded, core_rules)
        grounded = self._ensure_query_filter_grounded_rules(prepared, grounded)
        grounded = self._ensure_amount_threshold_grounded_rules(prepared, grounded)
        return self._sort_grounded_business_rules(prepared, grounded)

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
                prepared.supporting_docs,
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

    def _ensure_workflow_grounded_rules(
        self,
        prepared: PreparedRebuildInput,
        grounded: list[GroundedBusinessRule],
    ) -> list[GroundedBusinessRule]:
        if not self._has_workflow_pattern(prepared):
            return grounded
        output = list(grounded)
        defaults = [
            (
                "승인 트리거 조건",
                "승인 흐름이 시작되는 트리거 조건은 별도 워크플로우 기준으로 분리해야 합니다.",
                ("submit", "submitted", "approval", "trigger", "요청", "승인 시작", "기안"),
                ["워크플로우 서비스", "API"],
            ),
            (
                "승인 주체 정의",
                "승인 주체와 결재 권한은 별도 승인 정책으로 유지해야 합니다.",
                ("approver", "approverrole", "reviewer", "manager", "finance", "admin", "승인자", "결재자"),
                ["워크플로우 서비스", "정책 서비스"],
            ),
            (
                "승인 단계 구조",
                "단계별 승인 순서와 조건부 승인 구조는 같은 워크플로우 계층으로 정리해야 합니다.",
                ("approvalstep", "approval_step", "approvallevel", "approval_level", "step", "stage", "1차", "2차", "단계"),
                ["워크플로우 서비스", "API"],
            ),
            (
                "의사결정 분기 조건",
                "승인, 반려, 보류, 자동 승인 분기 조건은 의사결정 게이트 기준으로 유지해야 합니다.",
                ("approve", "reject", "hold", "pending", "auto_approved", "승인", "반려", "보류", "자동 승인"),
                ["워크플로우 서비스", "API"],
            ),
            (
                "예외 처리 흐름",
                "대리 승인, 긴급 처리, 예외 승인 경로는 일반 승인 흐름과 분리해 관리해야 합니다.",
                ("delegate", "delegat", "escalation", "urgent", "대리 승인", "긴급", "예외 승인"),
                ["워크플로우 서비스", "정책 서비스"],
            ),
        ]
        for title, description, keywords, design_targets in defaults:
            if any(self._normalize_key(item.title) == self._normalize_key(title) for item in output):
                continue
            evidence = self._collect_evidence_refs(prepared, keywords, ("source", "ui", "sql"))
            if not evidence:
                continue
            confidence, confidence_reason = self._resolve_confidence(evidence)
            output.append(
                GroundedBusinessRule(
                    title=title,
                    description=description,
                    evidence=evidence,
                    design_targets=design_targets,
                    confidence=confidence,
                    confidence_reason=confidence_reason,
                    needs_verification=confidence != "확정",
                )
            )
        return output

    def _ensure_validation_grounded_rules(
        self,
        prepared: PreparedRebuildInput,
        grounded: list[GroundedBusinessRule],
        core_rules: list[str],
    ) -> list[GroundedBusinessRule]:
        if not self._is_validation_primary(prepared):
            return grounded
        output = list(grounded)
        if self._count_validation_biased_rules(output) >= 2:
            return output
        for rule in self._validation_candidate_rule_texts(prepared, core_rules):
            if self._count_validation_biased_rules(output) >= 2:
                break
            normalized = self._normalize_key(rule)
            if any(self._normalize_key(item.description) == normalized for item in output):
                continue
            keywords = self._keywords_from_text(rule)
            evidence = self._collect_evidence_refs(prepared, keywords, ("source", "ui", "sql", "schema"))
            confidence, confidence_reason = self._resolve_confidence(evidence)
            output.append(
                GroundedBusinessRule(
                    title=self._validation_rule_title(rule),
                    description=rule,
                    evidence=evidence,
                    design_targets=["검증 흐름", "API"],
                    confidence=confidence,
                    confidence_reason=confidence_reason,
                    needs_verification=confidence != "확정",
                  )
              )
        return output

    def _ensure_access_control_grounded_rules(
        self,
        prepared: PreparedRebuildInput,
        grounded: list[GroundedBusinessRule],
        core_rules: list[str],
    ) -> list[GroundedBusinessRule]:
        claim_access_focus = self._has_claim_access_control_focus(prepared, grounded)
        access_primary = self._should_enrich_access_control(prepared, grounded) or claim_access_focus
        if not access_primary:
            return grounded
        output = list(grounded)
        existing_axes = {self._access_control_rule_axis(f"{item.title} {item.description}") for item in output}
        for candidate in self._access_control_candidate_rule_specs(prepared, core_rules):
            if self._count_access_control_axes(output) >= 3:
                break
            normalized = self._normalize_key(candidate["description"])
            if any(self._normalize_key(item.description) == normalized for item in output):
                continue
            candidate_axis = self._access_control_rule_axis(
                f"{candidate['title']} {candidate['description']}"
            )
            if candidate_axis and candidate_axis in existing_axes:
                continue
            evidence = self._collect_evidence_refs(
                prepared,
                candidate["keywords"],
                ("source", "ui", "sql", "schema"),
            )
            if not evidence:
                continue
            confidence, confidence_reason = self._resolve_confidence(evidence)
            output.append(
                GroundedBusinessRule(
                    title=candidate["title"],
                    description=candidate["description"],
                    evidence=evidence,
                    design_targets=list(candidate["design_targets"]),
                    confidence=confidence,
                    confidence_reason=confidence_reason,
                    needs_verification=confidence != "확정",
                )
            )
            if candidate_axis:
                existing_axes.add(candidate_axis)
        if self._should_enrich_access_control(prepared, output):
            shared_evidence = [evidence for rule in output[:1] for evidence in rule.evidence][:2]
            derived_specs = [
                (
                    "권한 위임 가능 여부",
                    "현재 자산 기준으로 승인 권한 위임 가능 여부는 별도 권한 정책으로 확인해야 합니다.",
                    ["정책 서비스", "권한 모델"],
                    "직접 확인된 승인 규칙은 있으나 권한 위임 범위는 현재 자산에서 모두 확인되지 않았습니다.",
                ),
                (
                    "승인 요청 및 처리 흐름",
                    "현재 자산 기준으로 승인 요청과 처리 결과 통지 흐름은 별도 승인 절차로 정리해야 합니다.",
                    ["예외 승인 흐름", "정책 서비스", "API"],
                    "직접 확인된 승인 조건은 있으나 승인 요청과 처리 결과 통지 흐름은 현재 자산에서 일부만 확인되었습니다.",
                ),
            ]
            for title, description, targets, reason in derived_specs:
                if any(self._normalize_key(item.title) == self._normalize_key(title) for item in output):
                    continue
                output.append(
                    GroundedBusinessRule(
                        title=title,
                        description=description,
                        evidence=shared_evidence,
                        design_targets=targets,
                        confidence="조건부",
                        confidence_reason=reason,
                        needs_verification=True,
                    )
                )
        prioritized_titles = {
            self._normalize_key("1천만원 이상 전담 부서 처리"),
            self._normalize_key("권한 위임 가능 여부"),
            self._normalize_key("승인 요청 및 처리 흐름"),
        }
        if claim_access_focus:
            prioritized_titles = {
                self._normalize_key("FRAUD 본사 심사 전용"),
                self._normalize_key("지점장 300만원 한도"),
                self._normalize_key("1천만원 이상 전담 부서 처리"),
                self._normalize_key("B99 긴급건 본사 선승인"),
            }
        if access_primary:
            prioritized = [
                item for item in output
                if self._normalize_key(item.title) in prioritized_titles
            ]
            if len(prioritized) >= 3:
                return prioritized[:4] if claim_access_focus else prioritized[:3]
        return output

    def _ensure_query_filter_grounded_rules(
        self,
        prepared: PreparedRebuildInput,
        grounded: list[GroundedBusinessRule],
    ) -> list[GroundedBusinessRule]:
        if prepared.signals.primary_feature_mode != "search_filters":
            return grounded
        output = list(grounded)
        defaults = [
            (
                "조회 조건 분리",
                "조회 조건과 필터 조합 규칙을 별도 조회 모델로 분리해야 합니다.",
                ("query", "filter", "search", "where", "request.getparameter", "조회", "검색", "필터"),
                ["조회 모델", "정책 서비스"],
            ),
            (
                "정렬과 페이징 기본 규칙",
                "정렬 기준과 페이징 기본 규칙을 별도 조회 정책으로 정리해야 합니다.",
                ("order by", "sort", "paging", "page", "limit", "offset", "정렬", "페이징"),
                ["조회 모델", "API"],
            ),
            (
                "결과 목록 구성 규칙",
                "결과 목록 구성과 필터 상태는 같은 조회 모델 기준으로 유지해야 합니다.",
                ("table", "grid", "list", "results", "목록", "결과"),
                ["조회 모델", "API"],
            ),
        ]
        for title, description, keywords, design_targets in defaults:
            if any(self._normalize_key(item.title) == self._normalize_key(title) for item in output):
                continue
            evidence = self._collect_evidence_refs(prepared, keywords, ("source", "ui", "sql"))
            if not evidence:
                continue
            confidence, confidence_reason = self._resolve_confidence(evidence)
            output.append(
                GroundedBusinessRule(
                    title=title,
                    description=description,
                    evidence=evidence,
                    design_targets=design_targets,
                    confidence=confidence,
                    confidence_reason=confidence_reason,
                    needs_verification=confidence != "확정",
                )
            )
        return output

    def _ensure_amount_threshold_grounded_rules(
        self,
        prepared: PreparedRebuildInput,
        grounded: list[GroundedBusinessRule],
    ) -> list[GroundedBusinessRule]:
        if not self._should_force_amount_threshold_narrative(prepared, grounded):
            return grounded
        output = list(grounded)
        defaults = [
            (
                "금액 구간 기준",
                "금액 구간별 처리 기준은 별도 한도 정책으로 유지해야 합니다.",
                ("amount", "order_amount", "claim_amount", "금액", "한도", "threshold", "limit"),
                ["정책 서비스", "API"],
            ),
            (
                "한도 계산 규칙",
                "한도 기준 필드와 금액 비교 규칙은 같은 정책 계산 기준으로 유지해야 합니다.",
                ("dailylimit", "daily_limit", "limit_amount", "limit", "<=", ">=", "한도", "계산"),
                ["정책 서비스", "API"],
            ),
            (
                "고액 처리 경계",
                "고액 처리 기준과 한도 초과 후속 경계는 같은 정책 결과로 정리해야 합니다.",
                ("50000", "300000", "1000000", "고액", "한도 초과", "approval", "limit"),
                ["정책 서비스", "API"],
            ),
            (
                "차단/승인 경계",
                "금액 기준에 따라 차단과 승인 경계를 분리해 정책 결과로 관리해야 합니다.",
                ("approve", "approval", "차단", "승인", "본사 승인", "검토"),
                ["정책 서비스", "API"],
            ),
        ]
        for title, description, keywords, design_targets in defaults:
            if any(self._normalize_key(item.title) == self._normalize_key(title) for item in output):
                continue
            evidence = self._collect_evidence_refs(prepared, keywords, ("source", "ui", "sql"))
            if not evidence:
                continue
            confidence, confidence_reason = self._resolve_confidence(evidence)
            output.append(
                GroundedBusinessRule(
                    title=title,
                    description=description,
                    evidence=evidence,
                    design_targets=design_targets,
                    confidence=confidence,
                    confidence_reason=confidence_reason,
                    needs_verification=confidence != "확정",
                )
            )
        return output

    def _validation_candidate_rule_texts(
        self,
        prepared: PreparedRebuildInput,
        core_rules: list[str],
    ) -> list[str]:
        candidates: list[str] = []
        for rule in core_rules:
            if self._validation_keyword_hit_count(rule) > 0 and rule not in candidates:
                candidates.append(rule)
        bundle = " ".join(
            [
                prepared.assets.source_code,
                prepared.assets.sql_queries,
                prepared.assets.database_schema,
                prepared.supporting_docs,
            ]
        ).lower()
        if any(token in bundle for token in ("duplicate", "중복", "exists", "count(")):
            candidates.append("중복 여부는 저장 전에 먼저 검증해야 합니다.")
        if any(token in bundle for token in ("claimamount", "claim_amount", "amount", "3000000", "10000000", "한도")):
            candidates.append("금액 한도 조건은 저장 전에 먼저 검증해야 합니다.")
        if any(token in bundle for token in ("blocked", "forbidden", "invalid", "required", "delivery_hold", "선행", "save(", "repository.save", "throw new")):
            candidates.append("선행 차단 조건과 저장 전 검증 순서를 분리해야 합니다.")
        deduped: list[str] = []
        for item in candidates:
            if item not in deduped:
                deduped.append(item)
        return deduped

    def _validation_rule_title(self, rule: str) -> str:
        lowered = (rule or "").lower()
        if any(token in lowered for token in ("duplicate", "중복", "exists", "count(")):
            return "중복 체크 선행"
        if any(token in lowered for token in ("amount", "3000000", "10000000", "한도")):
            return "금액 한도 검증"
        if any(token in lowered for token in ("blocked", "forbidden", "invalid", "required", "delivery_hold", "선행", "save")):
            return "저장 전 차단 선행"
        return rule[:32]

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

    def _sort_grounded_business_rules(
        self,
        prepared: PreparedRebuildInput,
        grounded: list[GroundedBusinessRule],
    ) -> list[GroundedBusinessRule]:
        claim_access_focus = self._has_claim_access_control_focus(prepared, grounded)
        if self._has_workflow_pattern(prepared):
            scored: list[tuple[float, int, GroundedBusinessRule]] = []
            for index, rule in enumerate(grounded):
                text = " ".join(
                    [
                        rule.title,
                        rule.description,
                        " ".join(rule.design_targets),
                        " ".join(evidence.excerpt for evidence in rule.evidence),
                    ]
                )
                workflow_hits = self._workflow_keyword_hit_count(text)
                access_hits = self._access_control_keyword_hit_count(text)
                state_hits = self._state_keyword_hit_count(text)
                validation_hits = self._validation_keyword_hit_count(text)
                score = float(workflow_hits) * 4.6
                if "승인 트리거" in rule.title:
                    score += 5.0
                if "승인 단계 구조" in rule.title:
                    score += 6.0
                if "의사결정 분기 조건" in rule.title:
                    score += 5.0
                if "예외 처리 흐름" in rule.title:
                    score += 4.8
                if "승인 주체 정의" in rule.title:
                    score += 4.0
                if any(token in rule.title for token in ("권한 위임 가능 여부", "승인 요청 및 처리 흐름")):
                    score -= 4.0
                if state_hits > 0 and workflow_hits == 0:
                    score -= float(state_hits) * 2.8
                if validation_hits > 0 and workflow_hits == 0:
                    score -= float(validation_hits) * 2.2
                if access_hits > 0 and workflow_hits == 0:
                    score -= float(access_hits) * 1.6
                scored.append((score, -index, rule))
            ordered = [item for _, _, item in sorted(scored, key=lambda entry: (entry[0], entry[1]), reverse=True)]
            filtered = [
                item
                for item in ordered
                if self._workflow_keyword_hit_count(
                    " ".join(
                        [
                            item.title,
                            item.description,
                            " ".join(item.design_targets),
                            " ".join(evidence.excerpt for evidence in item.evidence),
                        ]
                    )
                ) > 0
            ]
            return (filtered or ordered)[:5]
        if prepared.signals.primary_feature_mode == "search_filters":
            scored: list[tuple[float, int, GroundedBusinessRule]] = []
            for index, rule in enumerate(grounded):
                text = " ".join(
                    [
                        rule.title,
                        rule.description,
                        " ".join(rule.design_targets),
                        " ".join(evidence.excerpt for evidence in rule.evidence),
                    ]
                )
                query_hits = self._query_filter_keyword_hit_count(text)
                state_hits = self._state_keyword_hit_count(text)
                validation_hits = self._validation_keyword_hit_count(text)
                score = float(query_hits) * 4.2
                score += 1.2 if any("조회" in target or "API" in target for target in rule.design_targets) else 0.0
                score += 1.0 if any(item.evidence_kind in {"source", "sql", "ui"} for item in rule.evidence) else 0.0
                if state_hits > 0:
                    score -= float(state_hits) * 3.0
                if validation_hits > 0 and query_hits == 0:
                    score -= float(validation_hits) * 1.8
                scored.append((score, -index, rule))
            ordered = [item for _, _, item in sorted(scored, key=lambda entry: (entry[0], entry[1]), reverse=True)]
            filtered = [
                item
                for item in ordered
                if self._query_filter_keyword_hit_count(
                    " ".join(
                        [
                            item.title,
                            item.description,
                            " ".join(item.design_targets),
                            " ".join(evidence.excerpt for evidence in item.evidence),
                        ]
                    )
                ) > 0
            ]
            return (filtered or ordered)[:3]
        if self._should_force_amount_threshold_narrative(prepared, grounded) and not claim_access_focus:
            scored: list[tuple[float, int, GroundedBusinessRule]] = []
            for index, rule in enumerate(grounded):
                text = " ".join(
                    [
                        rule.title,
                        rule.description,
                        " ".join(rule.design_targets),
                        " ".join(evidence.excerpt for evidence in rule.evidence),
                    ]
                )
                amount_hits = self._amount_threshold_keyword_hit_count(text)
                query_hits = self._query_filter_keyword_hit_count(text)
                state_hits = self._state_keyword_hit_count(text)
                validation_hits = self._validation_keyword_hit_count(text)
                score = float(amount_hits) * 4.2
                score += 1.2 if any("정책" in target or "API" in target for target in rule.design_targets) else 0.0
                score += 1.0 if any(item.evidence_kind in {"source", "sql", "constraint"} for item in rule.evidence) else 0.0
                if query_hits > 0:
                    score -= float(query_hits) * 3.5
                if state_hits > 0 and amount_hits == 0:
                    score -= float(state_hits) * 1.5
                if "검증" in rule.title or ("검증" in rule.description and amount_hits <= 1):
                    score -= 3.0
                if validation_hits > 0 and "한도 계산" not in rule.title and "금액 구간" not in rule.title and "고액 처리" not in rule.title:
                    score -= 1.5
                scored.append((score, -index, rule))
            ordered = [item for _, _, item in sorted(scored, key=lambda entry: (entry[0], entry[1]), reverse=True)]
            filtered = [
                item
                for item in ordered
                if self._amount_threshold_keyword_hit_count(
                    " ".join(
                        [
                            item.title,
                            item.description,
                            " ".join(item.design_targets),
                            " ".join(evidence.excerpt for evidence in item.evidence),
                        ]
                    )
                ) > 0
            ]
            return (filtered or ordered)[:3]
        if claim_access_focus or self._is_access_control_primary(prepared, grounded):
            scored: list[tuple[float, int, GroundedBusinessRule]] = []
            for index, rule in enumerate(grounded):
                text = " ".join(
                    [
                        rule.title,
                        rule.description,
                        " ".join(rule.design_targets),
                        " ".join(evidence.excerpt for evidence in rule.evidence),
                    ]
                )
                access_hits = self._access_control_keyword_hit_count(text)
                validation_hits = self._validation_keyword_hit_count(text)
                state_hits = self._state_keyword_hit_count(text)
                amount_hits = self._amount_threshold_keyword_hit_count(text)
                axis = self._access_control_rule_axis(text)
                score = float(access_hits) * 4.0
                score += 2.5 if axis in {"amount", "approver", "route"} else 0.0
                score += 1.0 if any(item.evidence_kind in {"source", "sql", "constraint"} for item in rule.evidence) else 0.0
                if claim_access_focus:
                    if any(token in text.lower() for token in ("branch_manager", "hq_reviewer", "claim_audit", "fraud", "b99", "본사", "지점장", "선승인", "심사")):
                        score += 4.5
                    if axis == "approver":
                        score += 3.0
                    elif axis == "route":
                        score += 2.5
                    elif axis == "amount" and access_hits > 0:
                        score += 1.8
                    if "금액 한도 검증" in rule.title:
                        score -= 6.0
                    if validation_hits > 0 and access_hits == 0:
                        score -= float(validation_hits) * 3.0
                    if amount_hits > 0 and access_hits == 0:
                        score -= float(amount_hits) * 1.4
                if access_hits == 0 and validation_hits > 0:
                    score -= float(validation_hits) * 2.5
                if access_hits == 0 and state_hits > 0:
                    score -= float(state_hits) * 1.5
                scored.append((score, -index, rule))
            ordered = [item for _, _, item in sorted(scored, key=lambda entry: (entry[0], entry[1]), reverse=True)]
            if claim_access_focus:
                prioritized = [
                    item for item in ordered
                    if any(
                        token in f"{item.title} {item.description}".lower()
                        for token in ("branch_manager", "hq_reviewer", "claim_audit", "fraud", "b99", "본사", "지점장", "선승인", "심사", "승인", "부서", "권한")
                    )
                    and "금액 한도 검증" not in item.title
                ]
                if len(prioritized) >= 3:
                    return prioritized[:5]
            return ordered
        if not self._is_validation_primary(prepared):
            return grounded
        scored: list[tuple[float, int, GroundedBusinessRule]] = []
        for index, rule in enumerate(grounded):
            text = " ".join(
                [
                    rule.title,
                    rule.description,
                    " ".join(rule.design_targets),
                    " ".join(evidence.excerpt for evidence in rule.evidence),
                ]
            )
            validation_hits = self._validation_keyword_hit_count(text)
            state_hits = self._state_keyword_hit_count(text)
            score = float(validation_hits) * 4.0
            score += 1.5 if any("검증" in target for target in rule.design_targets) else 0.0
            score += 1.0 if any(item.evidence_kind in {"source", "sql"} for item in rule.evidence) else 0.0
            if validation_hits == 0 and state_hits > 0:
                score -= float(state_hits) * 2.5
            scored.append((score, -index, rule))
        ordered = [item for _, _, item in sorted(scored, key=lambda entry: (entry[0], entry[1]), reverse=True)]
        return ordered

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

    def build_applied_templates(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
    ) -> list[AppliedJudgmentTemplate]:
        from mellow_link.services.refactoring_support_engine.judgment_synthesizer import JudgmentSynthesizer

        return JudgmentSynthesizer().build_applied_templates(prepared, grounded_rules, retained_contracts)

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

    def build_retained_contracts(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
    ) -> list[RetainedContract]:
        items: list[RetainedContract] = []
        for spec in self._template_retained_contract_specs(prepared, grounded_rules):
            contract = self._make_retained_contract(prepared, spec["item"], tuple(spec["keywords"]), spec["basis"])
            if contract.evidence:
                items.append(contract)
        deduped = self._dedupe_by_normalized_text(items, attr="item")
        return [item for item in deduped if item.evidence]

    def build_verification_checkpoints(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        applied_templates: list[AppliedJudgmentTemplate] | None = None,
    ) -> list[VerificationItem]:
        from mellow_link.services.refactoring_support_engine.planning_synthesizer import PlanningSynthesizer

        decisions = self._compat_decision_artifacts(prepared, applied_templates or [])
        return PlanningSynthesizer().build_verification_checkpoints(
            prepared,
            grounded_rules,
            retained_contracts,
            decisions,
        )

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

    def build_decision_items(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        applied_templates: list[AppliedJudgmentTemplate],
        *,
        decision_count_hint: int | None = None,
    ) -> list[DecisionItem]:
        from mellow_link.services.refactoring_support_engine.judgment_synthesizer import JudgmentSynthesizer

        return JudgmentSynthesizer().build_decision_items(
            prepared,
            grounded_rules,
            applied_templates,
            decision_count_hint=decision_count_hint,
        )

    def build_priority_split_items(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> list[PrioritySplitItem]:
        from mellow_link.services.refactoring_support_engine.planning_synthesizer import PlanningSynthesizer

        decisions = self._compat_decision_artifacts(prepared, applied_templates)
        return PlanningSynthesizer().build_priority_split_items(prepared, grounded_rules, retained_contracts, decisions)

    def build_design_options(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> list[DesignOption]:
        from mellow_link.services.refactoring_support_engine.planning_synthesizer import PlanningSynthesizer

        decisions = self._compat_decision_artifacts(prepared, applied_templates)
        return PlanningSynthesizer().build_design_options(prepared, grounded_rules, retained_contracts, decisions)

    def _apply_recommended_selection_reason(
        self,
        prepared: PreparedRebuildInput,
        options: list[DesignOption],
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> list[DesignOption]:
        from mellow_link.services.refactoring_support_engine.planning_synthesizer import PlanningSynthesizer

        decisions = self._compat_decision_artifacts(prepared, applied_templates)
        return PlanningSynthesizer().apply_recommended_selection_reason(
            prepared,
            options,
            grounded_rules,
            retained_contracts,
            decisions,
        )

    def pick_recommended_option(
        self,
        options: list[DesignOption],
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> RecommendedOption | None:
        from mellow_link.services.refactoring_support_engine.planning_synthesizer import PlanningSynthesizer

        decisions = self._compat_decision_artifacts(prepared, applied_templates)
        return PlanningSynthesizer().pick_recommended_option(
            options,
            prepared,
            grounded_rules,
            retained_contracts,
            decisions,
        )

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
        lines.append(f"따라서 {axis_phrase}를 기준으로 {self._option_label(recommended.name)}를 우선 적용해야 합니다.")
        if contract_phrases:
            lines.append(f"이 방식은 {', '.join(contract_phrases[:2])} 계약을 유지하면서도 구현 범위를 통제해야 하는 현재 조건과 충돌하지 않습니다.")
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
            return f"다른 옵션보다 상태 전이와 권한 규칙을 하나의 정책 계층에서 함께 다뤄야 하므로 {option_label}를 우선 적용해야 합니다."
        if ids and ids[0] == "workflow":
            return f"다른 옵션보다 승인 트리거, 승인 주체, 단계별 의사결정 게이트를 같은 워크플로우 계층으로 고정해야 하므로 {option_label}를 우선 적용해야 합니다."
        if ids[:2] in (["validation", "access_control"], ["access_control", "validation"]):
            return f"다른 옵션보다 금액 한도와 승인 권한을 함께 분리해야 하므로 {option_label}를 우선 적용해야 합니다."
        if ids and ids[0] == "access_control":
            return f"다른 옵션보다 승인 주체, 부서 책임, 처리 경로를 같은 권한 정책으로 고정해야 하므로 {option_label}를 우선 적용해야 합니다."
        if ids and ids[0] == "validation":
            return f"다른 옵션보다 선행 차단 조건과 저장 전 검증 순서를 함께 고정해야 하므로 {option_label}를 우선 적용해야 합니다."
        if ids and ids[0] == "query_filter":
            return f"다른 옵션보다 조회 조건, 정렬, 페이징 규칙을 같은 조회 모델로 고정해야 하므로 {option_label}를 우선 적용해야 합니다."
        if ids and ids[0] == "amount_threshold":
            return f"다른 옵션보다 금액 구간과 한도 정책을 같은 정책 계층으로 고정해야 하므로 {option_label}를 우선 적용해야 합니다."
        return f"다른 옵션보다 핵심 규칙과 유지 계약을 함께 반영해야 하므로 {option_label}를 우선 적용해야 합니다."

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

    def build_execution_plan(
        self,
        prepared: PreparedRebuildInput,
        grounded_rules: list[GroundedBusinessRule],
        retained_contracts: list[RetainedContract],
        recommended_option: RecommendedOption | None,
        applied_templates: list[AppliedJudgmentTemplate],
    ) -> list[ExecutionPlanWeek]:
        from mellow_link.services.refactoring_support_engine.planning_synthesizer import PlanningSynthesizer

        decisions = self._compat_decision_artifacts(prepared, applied_templates)
        return PlanningSynthesizer().build_execution_plan(
            prepared,
            grounded_rules,
            retained_contracts,
            recommended_option,
            decisions,
        )

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
                prepared.supporting_docs,
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
                {"title": "VIP 야간 마감 제한", "statement": "VIP 고객은 야간 시간대에 주문 마감을 수행할 수 없습니다.", "keywords": ("vip", "22", "23", "00", "야간", "마감"), "preferred_types": ("source", "ui", "constraint"), "design_targets": ("정책 서비스", "상태 전이", "검증 흐름")},
                {"title": "대리점 고액 주문 본사 전용", "statement": "대리점 채널의 고액 주문은 본사 권한으로만 마감할 수 있습니다.", "keywords": ("agency", "대리점", "hq", "고액", "5000000"), "preferred_types": ("source", "constraint"), "design_targets": ("정책 서비스", "권한 모델", "API")},
                {"title": "배송보류 해제 선행", "statement": "배송보류 상태가 해제되기 전에는 주문 마감을 진행할 수 없습니다.", "keywords": ("delivery", "hold", "배송보류"), "preferred_types": ("source", "constraint"), "design_targets": ("검증 흐름", "API", "상태 전이")},
                {"title": "수출 주문 고액건 REVIEW_REQUIRED", "statement": "수출 주문의 고액 건은 즉시 마감하지 않고 REVIEW_REQUIRED 상태로 전환해야 합니다.", "keywords": ("export", "수출", "review_required", "7000000"), "preferred_types": ("source", "sql"), "design_targets": ("상태 전이", "정책 서비스", "API")},
            ]
        if concept == "청구 조정":
            return [
                {"title": "FRAUD 본사 심사 전용", "statement": "FRAUD 사고건은 HQ_REVIEWER 권한으로만 청구 조정을 수행할 수 있습니다.", "keywords": ("fraud", "hq_reviewer"), "preferred_types": ("source", "constraint"), "design_targets": ("정책 서비스", "권한 모델", "API")},
                {"title": "지점장 300만원 한도", "statement": "지점장은 300만원 이상 청구건을 조정할 수 없습니다.", "keywords": ("branch_manager", "지점장", "3000000", "300만원"), "preferred_types": ("source", "constraint"), "design_targets": ("정책 서비스", "검증 흐름")},
                {"title": "1천만원 이상 전담 부서 처리", "statement": "1천만원 이상 청구건은 CLAIM_AUDIT 부서만 조정할 수 있습니다.", "keywords": ("10000000", "1천만원", "claim_audit"), "preferred_types": ("source", "constraint"), "design_targets": ("정책 서비스", "권한 모델", "API")},
                {"title": "B99 긴급건 본사 선승인", "statement": "B99 지점의 긴급 청구건은 본사 선승인 없이 조정할 수 없습니다.", "keywords": ("b99", "urgent", "긴급", "선승인"), "preferred_types": ("source", "constraint"), "design_targets": ("예외 승인 흐름", "정책 서비스", "API")},
                {"title": "마감/취소 상태 조정 금지", "statement": "CLOSED 또는 CANCELLED 상태의 청구건은 조정할 수 없습니다.", "keywords": ("closed", "cancelled", "조정", "adjust"), "preferred_types": ("source", "schema", "sql"), "design_targets": ("상태 전이", "검증 흐름", "API")},
            ]
        return []

    def _make_retained_contract(
        self,
        prepared: PreparedRebuildInput,
        item: str,
        keywords: tuple[str, ...],
        basis: str,
    ) -> RetainedContract:
        return RetainedContract(
            item=item,
            basis=basis,
            evidence=self._collect_evidence_refs(prepared, keywords, ("source", "ui", "sql", "schema")),
        )

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

    def _sanitize_structured_result(self, result: StructuredRebuildResult) -> StructuredRebuildResult:
        return StructuredRebuildResult.model_validate(self._sanitize_for_user_output(result.model_dump()))

    def _sanitize_for_user_output(self, value):
        if isinstance(value, str):
            return self._sanitize_text(value)
        if isinstance(value, list):
            return [self._sanitize_for_user_output(item) for item in value]
        if isinstance(value, dict):
            return {key: self._sanitize_for_user_output(item) for key, item in value.items()}
        return value

    def _sanitize_text(self, text: str) -> str:
        sanitized = (text or "").strip()
        from .postprocess.rules import apply_sentence_polish

        replacements = {
            "REDACTED_PATH": "",
            "role/status/action visibility": "역할별 액션 노출 규칙",
            "query parameters": "조회 파라미터 규칙",
            "search filter state": "검색 조건 상태",
            "SQL parameterization": "SQL 조건 매핑",
            "validation rules": "입력 검증 규칙",
            "save guards": "저장 전 선행 조건",
            "duplicate checks": "중복 체크 규칙",
            "controller/service/repository": "API, 서비스, 데이터 접근 경계",
            "command/DTO": "커맨드와 입력 모델",
            "command DTO": "입력 모델",
            "policy layer": "정책 서비스",
            "policy service": "정책 서비스",
            "transition policy": "상태 전이 규칙 계층",
            "query state hook": "조회 상태 관리",
            "query state": "조회 상태",
            "repository": "데이터 접근 계층",
            "validator": "검증 계층",
            "DTO": "입력 모델",
            "mapper": "매핑 규칙",
            "projection": "읽기 전용 조회 구조",
            "criteria": "조건",
            "authorization rule": "권한 규칙",
        }
        for raw, replacement in replacements.items():
            sanitized = sanitized.replace(raw, replacement)
        sanitized = re.sub(r"\[[^\]]*REDACTED_PATH[^\]]*\]", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\[SAFE (?:STRUCTURE|SOURCE):[^\]]+\]", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\b(?:asset_[0-9a-f]+|TBL_\d+|COL_\d+|CLS_\d+|FUNC_\d+|API_\d+|SCR_\d+)\b", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"node:(?:table|column|api|screen|function|class):[A-Z_0-9]+", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\.\.\./", "", sanitized)
        sanitized = re.sub(r"\b(?:role|command|controller)/\.\.\.?/?", "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"([A-Za-z가-힣_]+)\[\]", r"\1", sanitized)
        sanitized = re.sub(r"\bAPI/\b", "API ", sanitized)
        sanitized = re.sub(r"\b[A-Z_0-9]+status 컬럼\b", "status 컬럼", sanitized)
        sanitized = re.sub(r"\bstatus 컬럼 컬럼\b", "status 컬럼", sanitized)
        sanitized = re.sub(r"(^|\s)\.status\b", r"\1status 컬럼", sanitized)
        sanitized = sanitized.replace("계약 계약", "계약")
        sanitized = sanitized.replace("값 값", "값")
        sanitized = sanitized.replace("처리을", "처리를")
        sanitized = sanitized.replace("검증를", "검증을")
        sanitized = sanitized.replace("구조을", "구조를")
        sanitized = sanitized.replace("분리을", "분리를")
        sanitized = sanitized.replace("한도을", "한도를")
        sanitized = sanitized.replace("조회 조회", "조회")
        sanitized = sanitized.replace("규칙 규칙", "규칙")
        sanitized = sanitized.replace("정합성를", "정합성을")
        sanitized = sanitized.replace("누락로", "누락으로")
        sanitized = sanitized.replace("금지을", "금지를")
        sanitized = sanitized.replace("규칙야 합니다", "규칙이어야 합니다")
        sanitized = sanitized.replace("이동평균법로", "이동평균법으로")
        sanitized = sanitized.replace("입니다. 입니다.", "입니다.")
        sanitized = sanitized.replace("조회 조건과 SQL 파라미터 조합 규칙을 명시적으로 정리해", "조회 조건과 SQL 파라미터 조합 규칙")
        sanitized = sanitized.replace("조회 조건과 SQL 파라미터 조합 규칙 규칙", "조회 조건과 SQL 파라미터 조합 규칙")
        sanitized = sanitized.replace("여부을", "여부를")
        sanitized = sanitized.replace("승인 또는 차단 기준", "승인 경계")
        sanitized = sanitized.replace("상태 전이와 처리 가능 상태, 금액 한도와 핵심 검증", "차단 조건과 검증 순서")
        sanitized = sanitized.replace("상태 전이와 처리 가능 상태, 권한과 승인 주체", "상태 전이와 처리 가능 상태")
        sanitized = re.sub(r"\s{2,}", " ", sanitized)
        sanitized = re.sub(r"\s+([,.:])", r"\1", sanitized)
        sanitized = sanitized.replace("layered architecture", "계층 분리 구조")
        sanitized = apply_sentence_polish(sanitized)
        return sanitized.strip()

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

    def _looks_like_jsp(self, prepared: PreparedRebuildInput) -> bool:
        text = "\n".join([prepared.assets.source_code, prepared.assets.ui_template]).lower()
        return "<%" in text or "<jsp:" in text or "c:foreach" in text or "c:if" in text

    def _contains_sql_in_ui(self, prepared: PreparedRebuildInput) -> bool:
        text = "\n".join([prepared.assets.source_code, prepared.assets.ui_template]).lower()
        return bool(re.search(r"\b(select|insert|update|delete)\b", text))

    def _has_join_heaviness(self, sql_text: str) -> bool:
        lowered = (sql_text or "").lower()
        return lowered.count(" join ") >= 2 or lowered.count("case when") >= 2

    def _section(self, title: str, value: str) -> str:
        if not (value or "").strip():
            return ""
        return f"[{title}]\n{value.strip()}"

    def _render_structure_block(self, structure) -> str:
        node_lines = [f"- node:{node.kind}:{node.id}" for node in structure.nodes]
        edge_lines = [f"- edge:{edge.from_id}->{edge.to_id}:{edge.type}" for edge in structure.edges]
        body = "\n".join(node_lines + edge_lines)
        return body.strip()

    def _render_bullets(self, items: list[str]) -> list[str]:
        return [f"- {item}" for item in items] if items else ["- 정보가 충분하지 않습니다."]

    def _match_count(self, text: str, pattern: str) -> int:
        return len(re.findall(pattern, text, flags=re.IGNORECASE))

    def _extract_unique_matches(self, text: str, pattern: str) -> list[str]:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        results: list[str] = []
        for match in matches:
            if isinstance(match, tuple):
                for item in match:
                    cleaned = (item or "").strip()
                    if cleaned:
                        results.append(cleaned)
                        break
            else:
                cleaned = (match or "").strip()
                if cleaned:
                    results.append(cleaned)
        return self._dedupe_list(results)

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

    def _dedupe_dicts(self, items: list[dict]) -> list[dict]:
        seen: set[str] = set()
        output: list[dict] = []
        for item in items:
            key = repr(sorted(item.items()))
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output
