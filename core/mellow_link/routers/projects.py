from __future__ import annotations

import json
import logging
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from mellow_link import app_state
from mellow_link.infra import (
    AgentRun,
    AnalysisContext,
    ModernizationProject,
    ProjectAsset,
    ProjectRunHistory,
    TempResource,
    User,
    UserRole,
    get_current_user,
    get_current_user_optional,
    get_db,
)
from mellow_link.infra.run_events import get_run_events, get_run_snapshot
from mellow_link.modules.rebuild_assistant.api import (
    create_project_wrapped_run,
    resolve_project_goal,
    start_project_wrapped_run,
)
from mellow_link.modules.rebuild_assistant.decision_document import build_decision_brief
from mellow_link.modules.rebuild_assistant.manifest import MANIFEST as REBUILD_ASSISTANT_MANIFEST, MODULE_VERSION
from mellow_link.modules.rebuild_assistant.postprocess.consulting_contract import (
    build_consulting_min_contract,
)
from mellow_link.modules.rebuild_assistant.postprocess.consulting_deck import (
    build_consulting_deck,
)
from mellow_link.modules.rebuild_assistant.postprocess.information_separation import (
    package_information_role,
    package_question_axis,
    purify_diagnosis_lines,
    role_header,
)
from mellow_link.modules.rebuild_assistant.postprocess.schemas import (
    ConsultingDeck,
    ConsultingMinContract,
)
from mellow_link.modules.rebuild_assistant.postprocess.slide_schema import build_slide_schema
from mellow_link.modules.rebuild_assistant.schemas import (
    ProjectAssetItem,
    ProjectAnonymizationPreviewRequest,
    ProjectAnonymizationPreviewResponse,
    ResultExplanationResponse,
    ResultQARequest,
    ResultQAResponse,
    ProjectReanalysisRequest,
    ProjectReanalysisResponse,
    ProjectStartRequest,
    ProjectStartResponse,
    StructuredRebuildResult,
)
from mellow_link.services import DocumentRequest, DocumentType
from mellow_link.services.anonymization import (
    AnonymizationAsset,
    AnonymizationRunRequest,
    AnonymizationService,
    build_display_review_report,
    MaskingLevel,
)
from mellow_link.services.refactoring_support_engine.analysis_context_builder import AnalysisContextBuilder
from mellow_link.services.refactoring_support_engine.source_question_guard import SourceQuestionGuardService
from mellow_link.services.refactoring_support_engine.schemas import AnalysisContextBundle
from mellow_link.services.project_assets import (
    build_temp_context,
    cleanup_project_asset_dir,
    make_project_asset_id,
    promote_staged_asset,
    read_text,
    resolve_temp_upload_path,
    resolve_project_asset_path,
)
from mellow_link.services.project_results.archive import (
    build_project_result_archive_paths as _build_project_result_archive_paths_impl,
    persist_project_result_archive as _persist_project_result_archive_impl,
)
from mellow_link.services.project_results.presentation import (
    answer_project_result_question as _answer_project_result_question_impl,
    present_project_result as _present_project_result_impl,
    render_result_explanation_markdown as _render_result_explanation_markdown_impl,
)
from mellow_link.services.refactoring_support_engine.narrative_augmentation import (
    NarrativeAugmentationService,
)
from mellow_link.services.refactoring_support_engine.result_packager import ResultPackager
from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.refactoring_support_engine.surface_access import (
    can_export_review_artifacts,
    capabilities_dict,
    filter_decision_governance_for_access,
    filter_review_diff_for_access,
    normalize_surface_mode,
    policy_for_surface_mode,
)
from mellow_link.services.refactoring_support_engine.template_support import TemplateSupport
from mellow_link.services.scope_notice import PROJECT_SCOPE_NOTICE

router = APIRouter(tags=["Projects"])
logger = logging.getLogger(__name__)
_TEMPLATE_SUPPORT = TemplateSupport()
_PROJECT_RESULT_ARCHIVE_ROOT = Path(__file__).resolve().parents[3] / "data" / "outputs" / "final" / "project_results"
_SOURCE_QUESTION_GUARD = SourceQuestionGuardService()
_MARKDOWN_SECTION_REGISTRY: dict[str, tuple[dict[str, Any], ...]] = {
    "operational_source": (
        {"semantic": "analysis_purpose", "section_key": "report_purpose", "render": "paragraph"},
        {"semantic": "current_analysis_summary", "section_key": "executive_summary_v2", "render": "list"},
        {"semantic": "asset_identity", "section_key": "one_line_conclusion", "render": "paragraph"},
        {"semantic": "core_objects", "section_key": "analysis_summary", "render": "list"},
        {"semantic": "review_focus", "section_key": "primary_judgment_reason", "render": "paragraph"},
        {"semantic": "review_steps", "section_key": "execution_plan", "render": "list"},
        {"semantic": "operational_risks", "section_key": "risks", "render": "list"},
        {
            "semantic": "follow_up_checks",
            "section_key": "recommended_option",
            "render": "list",
            "source_keys": ("recommended_option", "recommended_directions"),
        },
    ),
    "option_comparison": (
        {"semantic": "comparison_purpose", "section_key": "report_purpose", "render": "paragraph"},
        {"semantic": "option_summary", "section_key": "executive_summary_v2", "render": "list"},
        {"semantic": "recommended_option", "section_key": "one_line_conclusion", "render": "paragraph"},
        {"semantic": "comparison_criteria", "section_key": "primary_judgment_reason", "render": "paragraph"},
        {"semantic": "recommendation_reason", "section_key": "recommended_option", "render": "list"},
        {"semantic": "execution_plan", "section_key": "execution_plan", "render": "list"},
        {"semantic": "option_risks", "section_key": "risks", "render": "list"},
    ),
    "default": (
        {"semantic": "report_purpose", "section_key": "report_purpose", "render": "paragraph"},
        {"semantic": "executive_summary", "section_key": "executive_summary_v2", "render": "list"},
        {"semantic": "one_line_conclusion", "section_key": "one_line_conclusion", "render": "paragraph"},
        {"semantic": "primary_judgment_reason", "section_key": "primary_judgment_reason", "render": "paragraph"},
        {"semantic": "recommended_option", "section_key": "recommended_option", "render": "list"},
        {"semantic": "execution_plan", "section_key": "execution_plan", "render": "list"},
        {"semantic": "risks", "section_key": "risks", "render": "list"},
    ),
}
_OPERATIONAL_ROLE_MARKDOWN_SECTION_REGISTRY: dict[str, tuple[dict[str, Any], ...]] = {
    "structure": (
        {"semantic": "analysis_purpose", "section_key": "report_purpose", "render": "paragraph"},
        {"semantic": "current_analysis_summary", "section_key": "executive_summary_v2", "render": "list"},
        {"semantic": "asset_identity", "section_key": "one_line_conclusion", "render": "paragraph"},
        {"semantic": "core_objects", "section_key": "analysis_summary", "render": "list"},
        {"semantic": "review_steps", "section_key": "execution_plan", "render": "list"},
    ),
    "diagnosis": (
        {"semantic": "diagnosis_purpose", "section_key": "report_purpose", "render": "paragraph"},
        {"semantic": "diagnosis_summary", "section_key": "executive_summary_v2", "render": "list"},
        {"semantic": "diagnosis_reason", "section_key": "primary_judgment_reason", "render": "paragraph"},
        {"semantic": "operational_risks", "section_key": "risks", "render": "list"},
    ),
    "decision": (
        {"semantic": "decision_purpose", "section_key": "report_purpose", "render": "paragraph"},
        {"semantic": "decision_summary", "section_key": "executive_summary_v2", "render": "list"},
        {"semantic": "decision_basis", "section_key": "primary_judgment_reason", "render": "paragraph"},
        {
            "semantic": "recommended_option",
            "section_key": "recommended_option",
            "render": "list",
            "source_keys": ("recommended_option", "recommended_directions"),
        },
        {"semantic": "execution_plan", "section_key": "execution_plan", "render": "list"},
    ),
}
_DIAGNOSIS_MARKDOWN_SECTION_TITLES: dict[str, str] = {
    "report_purpose": "현행 요약",
    "executive_summary_v2": "문제 정의",
    "primary_judgment_reason": "영향 분석",
    "risks": "리스크",
}
_CONSULTING_DECK_SLOT_FALLBACKS: dict[str, dict[str, tuple[tuple[str, str], ...]]] = {
    "operational_source": {
        "analysis_summary": (("overview", "as_is"),),
        "primary_judgment_reason": (("approach", "gap"), ("design", "rules")),
        "execution_plan": (("implementation", "process_flow"), ("design", "process_flow")),
        "risks": (("approach", "risks"),),
        "recommended_option": (("implementation", "actions"), ("vision", "actions")),
    }
}
_GENERIC_CONSULTING_DECK_SECTION_OVERLAYS: dict[tuple[str, str], tuple[str, ...]] = {
    ("overview", "as_is"): ("report_purpose", "executive_summary_v2", "one_line_conclusion"),
    ("approach", "gap"): ("primary_judgment_reason",),
    ("approach", "risks"): ("risks",),
    ("implementation", "process_flow"): ("execution_plan",),
    ("implementation", "actions"): ("recommended_directions",),
    ("design", "rules"): ("recommended_option",),
}


def _static_file(name: str) -> str:
    path = os.path.join(app_state.static_dir or ".", name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return path


def _wants_html(request: Request, explicit_format: str | None = None) -> bool:
    if explicit_format:
        return explicit_format.lower() == "html"
    accept = (request.headers.get("accept") or "").lower()
    return "text/html" in accept and "application/json" not in accept


def _parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    return value if isinstance(value, list) else []


def _project_attr(project: Any, attr: str, default: Any = None) -> Any:
    value = getattr(project, attr, default)
    return default if value is None else value


def _project_text(project: Any, attr: str, default: str = "") -> str:
    return str(_project_attr(project, attr, default) or default).strip()


def _project_json_list(project: Any, attr: str) -> list[Any]:
    raw = _project_attr(project, attr, None)
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, tuple):
        return list(raw)
    return _parse_json_list(raw if isinstance(raw, str) else None)


def _project_isoformat(project: Any, attr: str) -> str | None:
    value = _project_attr(project, attr, None)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return _normalize_utc_iso(value)


def _empty_family_classification_payload() -> dict[str, Any]:
    return {
        "family": "",
        "confidence": 0.0,
        "decision_basis": [],
        "secondary_signals": [],
        "display_strategy": "",
        "internal_strategy": "",
    }


def _serialize_asset_manifest(asset_manifest: list[Any]) -> str:
    return json.dumps(asset_manifest, ensure_ascii=False)


def _safe_download_name(project_name: str, suffix: str) -> str:
    base = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in project_name).strip("_") or "project"
    normalized_suffix = str(suffix or "").lstrip("._") or "result.bin"
    return f"{base}_{normalized_suffix}"


def _download_disposition(download_name: str, fallback_name: str) -> str:
    return f'attachment; filename="{fallback_name}"; filename*=UTF-8\'\'{quote(download_name)}'


def _surface_filtered_result_package(result_package: dict[str, Any], *, surface_mode: str) -> dict[str, Any]:
    filtered = deepcopy(result_package)
    normalized_surface_mode = normalize_surface_mode(surface_mode)
    policy = policy_for_surface_mode(normalized_surface_mode)
    extensions = filtered.get("extensions")
    review_diff_field_visibility = {
        "review_diff": "absent",
        "code_diff": "absent",
        "blocked_decisions": "absent",
        "block_reasons": "absent",
        "synthetic_signal_detected": "absent",
        "detector_locator": "absent",
        "fingerprint_alias": "absent",
    }
    decision_governance_state = "absent"
    review_diff_surface_policy = "absent"
    if isinstance(extensions, dict):
        decision_governance, decision_governance_state = filter_decision_governance_for_access(
            extensions.get("decision_governance"),
            access_profile=policy.access_profile,
        )
        review_diff_artifact = filter_review_diff_for_access(
            extensions.get("review_diff"),
            access_profile=policy.access_profile,
        )
        review_diff_field_visibility = dict(review_diff_artifact.field_visibility)
        review_diff_surface_policy = review_diff_artifact.review_diff_surface_policy
        if decision_governance is None:
            extensions.pop("decision_governance", None)
        else:
            extensions["decision_governance"] = decision_governance
        if review_diff_artifact.filtered is None:
            extensions.pop("review_diff", None)
        else:
            extensions["review_diff"] = review_diff_artifact.filtered
    review_diff_field_visibility, review_diff_surface_policy = _apply_specialized_family_surface_overrides(
        filtered,
        review_diff_field_visibility=review_diff_field_visibility,
        review_diff_surface_policy=review_diff_surface_policy,
    )
    provenance = filtered.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}
        filtered["provenance"] = provenance
    provenance["surface_access"] = {
        "surface_mode": normalized_surface_mode,
        "access_profile": policy.access_profile,
        "surface_variant": policy.surface_variant,
        "capabilities": capabilities_dict(policy.access_profile),
        "field_visibility": {
            **review_diff_field_visibility,
            "decision_governance": decision_governance_state,
        },
        "review_diff_surface_policy": review_diff_surface_policy,
        "decision_governance_surface_policy": decision_governance_state,
    }
    executive_summary = filtered.get("executive_summary")
    if isinstance(executive_summary, dict):
        executive_summary.pop("title", None)
        executive_summary.pop("state", None)
    diagnosis = filtered.get("diagnosis")
    if isinstance(diagnosis, dict):
        diagnosis.pop("state", None)
    design = filtered.get("design")
    if isinstance(design, dict):
        design.pop("state", None)
    transition_draft = filtered.get("transition_draft")
    if isinstance(transition_draft, dict):
        transition_draft.pop("state", None)
    contract_payload = filtered.get("consulting_min_contract")
    if isinstance(contract_payload, dict):
        try:
            contract = ConsultingMinContract.model_validate(contract_payload)
        except Exception:
            contract = None
        if contract is not None:
            project_payload = filtered.get("project") if isinstance(filtered.get("project"), dict) else {}
            filtered["consulting_deck"] = build_consulting_deck(
                contract,
                project_name=str(project_payload.get("project_name") or ""),
                client_name=str(project_payload.get("client_name") or ""),
                surface_mode=normalized_surface_mode,
                family=_effective_family_for_consulting_surface(filtered),
                question_axis=package_question_axis(filtered),
            )
            filtered["slide_schema"] = build_slide_schema(
                ConsultingDeck.model_validate(filtered["consulting_deck"])
            ).model_dump()
    return filtered


def _apply_specialized_family_surface_overrides(
    filtered: dict[str, Any],
    *,
    review_diff_field_visibility: dict[str, str],
    review_diff_surface_policy: str,
) -> tuple[dict[str, str], str]:
    extensions = filtered.get("extensions")
    if not isinstance(extensions, dict):
        return review_diff_field_visibility, review_diff_surface_policy
    analysis_first_surface = _uses_analysis_first_surface_extensions(extensions)
    surface_wording = _surface_wording_from_extensions(extensions)
    document_tone = str(surface_wording.get("document_tone") or "").strip()
    comparison_first_surface = _uses_comparison_first_surface_extensions(extensions)
    if not analysis_first_surface and not comparison_first_surface:
        return review_diff_field_visibility, review_diff_surface_policy
    filtered_extensions = dict(extensions)
    filtered_extensions.pop("review_diff", None)
    filtered["extensions"] = filtered_extensions
    filtered["structure_comparison"] = {"available": False, "items": []}
    updated_visibility = dict(review_diff_field_visibility)
    for key, value in list(updated_visibility.items()):
        updated_visibility[key] = "hidden_by_family" if value != "absent" or key == "review_diff" else value
    return updated_visibility, "hidden_by_family"


def _project_status_from_run(snapshot: dict[str, Any] | None) -> str:
    run_status = ((snapshot or {}).get("status") or "").strip().lower()
    if run_status == "completed":
        return "completed"
    if run_status == "failed":
        return "failed"
    if run_status in {"pending", "waiting", "queued"}:
        return "pending"
    return "running"


def _sync_project_status(project: ModernizationProject, snapshot: dict[str, Any] | None, db: Session) -> None:
    resolved = _project_status_from_run(snapshot)
    if project.status != resolved:
        project.status = resolved
        db.commit()
        db.refresh(project)


def _project_or_404(project_id: str, user: User, db: Session) -> ModernizationProject:
    project = db.query(ModernizationProject).filter(ModernizationProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id != user.id:
        raise HTTPException(status_code=403, detail="해당 프로젝트에 대한 권한이 없습니다.")
    return project


def _extract_structured_result(events: list[dict[str, Any]]) -> StructuredRebuildResult | None:
    for event in reversed(events):
        if event.get("type") != "run_finished":
            continue
        payload = event.get("payload") or {}
        structured = payload.get("structured_result")
        if not isinstance(structured, dict):
            return None
        try:
            return StructuredRebuildResult.model_validate(structured)
        except Exception:
            return None
    return None


def _extract_polish_bundle(
    events: list[dict[str, Any]],
    structured: StructuredRebuildResult | None = None,
) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("type") != "run_finished":
            continue
        payload = event.get("payload") or {}
        polish_bundle = payload.get("polish_bundle")
        if isinstance(polish_bundle, dict):
            return polish_bundle
        if isinstance(polish_bundle, str):
            try:
                decoded = json.loads(polish_bundle)
            except Exception:
                decoded = None
            if isinstance(decoded, dict):
                return decoded
        fallback_result = structured
        if fallback_result is None:
            structured_payload = payload.get("structured_result")
            if isinstance(structured_payload, dict):
                try:
                    fallback_result = StructuredRebuildResult.model_validate(structured_payload)
                except Exception:
                    fallback_result = None
        if fallback_result is None:
            return None
        from mellow_link.modules.rebuild_assistant.postprocess.service import StructuredResultPolishService

        return StructuredResultPolishService().polish_result(
            fallback_result,
            audience="manager",
            delivery_mode="client_report",
        ).model_dump()
    return None


def _extract_project_insights(events: list[dict[str, Any]], structured: StructuredRebuildResult | None) -> dict[str, Any]:
    feature_mode = "-"
    findings: list[str] = []
    rules: list[str] = []
    for event in events:
        if event.get("type") != "log":
            continue
        payload = event.get("payload") or {}
        message = payload.get("message") or ""
        if message == "legacy analysis complete" and not findings:
            findings = list(payload.get("findings") or [])
        if message == "rebuild design complete" and not rules:
            rules = list(payload.get("strategy") or [])
    finished_payload = next((ev.get("payload") or {} for ev in reversed(events) if ev.get("type") == "run_finished"), {})
    feature_mode = _feature_mode_label(finished_payload.get("primary_feature_mode") or "-")
    if structured:
        if not findings:
            findings = list(structured.analysis_summary[:3])
        if not findings and (structured.one_line_conclusion or "").strip():
            findings = [structured.one_line_conclusion.strip()]
        if not rules:
            if structured.extracted_rules.status_permissions.entities:
                rules = [f"권한/상태 규칙 엔티티: {', '.join(structured.extracted_rules.status_permissions.entities)}"]
            elif structured.extracted_rules.search_filters.entities:
                rules = [f"조회 규칙 엔티티: {', '.join(structured.extracted_rules.search_filters.entities)}"]
            elif structured.extracted_rules.save_validation.entities:
                rules = [f"저장 검증 엔티티: {', '.join(structured.extracted_rules.save_validation.entities)}"]
        if not rules:
            rules = list(_trim_items(list(structured.rebuild_strategy), limit=3))
        if not rules:
            rules = list(_trim_items(list(structured.recommended_directions), limit=3))
    return {
        "feature_mode": feature_mode,
        "findings": findings,
        "rules": rules,
    }


def _feature_mode_label(mode: str) -> str:
    mapping = {
        "status_permissions": "권한 및 상태 규칙",
        "search_filters": "조회 조건 규칙",
        "save_validation": "저장 검증 규칙",
    }
    return mapping.get(mode, mode)


def _missing_context_blocks(result: StructuredRebuildResult | None) -> list[dict[str, str]]:
    if not result:
        return []
    if result.missing_context_details:
        return [
            {"required_material": item.required_material, "reason": item.reason}
            for item in result.missing_context_details
        ]
    return [{"required_material": item, "reason": "추가 분석 근거가 필요합니다."} for item in result.missing_context]


def _has_layer_content(layer: dict[str, Any] | None) -> bool:
    if not isinstance(layer, dict):
        return False
    return any(bool(layer.get(key)) for key in ("database", "backend", "frontend"))


def _has_extracted_rules_content(rules: dict[str, Any] | None) -> bool:
    if not isinstance(rules, dict):
        return False
    for section in rules.values():
        if isinstance(section, dict) and any(bool(value) for value in section.values()):
            return True
    return False


def _project_assets_rows(project_id: str, db: Session) -> list[ProjectAsset]:
    return (
        db.query(ProjectAsset)
        .filter(ProjectAsset.project_id == project_id)
        .order_by(ProjectAsset.created_at.asc(), ProjectAsset.id.asc())
        .all()
    )


def _project_history_rows(project_id: str, db: Session) -> list[ProjectRunHistory]:
    return (
        db.query(ProjectRunHistory)
        .filter(ProjectRunHistory.project_id == project_id)
        .order_by(ProjectRunHistory.sequence_no.asc(), ProjectRunHistory.created_at.asc(), ProjectRunHistory.id.asc())
        .all()
    )


def _ordered_project_assets(
    project: ModernizationProject,
    db: Session,
    *,
    asset_manifest: list[Any] | None = None,
) -> list[ProjectAsset]:
    asset_rows = _project_assets_rows(project.id, db)
    if not asset_rows:
        return []

    manifest = asset_manifest if asset_manifest is not None else _parse_json_list(project.asset_manifest_json)
    manifest_order = {
        str(item.get("temp_file_id") or ""): index
        for index, item in enumerate(manifest)
        if str(item.get("temp_file_id") or "").strip()
    }
    if manifest_order:
        asset_rows = [asset for asset in asset_rows if (asset.source_temp_file_id or "").strip() in manifest_order]
    fallback_index_start = len(manifest_order)
    return sorted(
        asset_rows,
        key=lambda asset: (
            manifest_order.get(asset.source_temp_file_id or "", fallback_index_start),
            asset.created_at,
            asset.id,
        ),
    )


def _temp_resource_map_for_assets(asset_rows: list[ProjectAsset], db: Session) -> dict[str, TempResource]:
    temp_file_ids = [asset.source_temp_file_id for asset in asset_rows if (asset.source_temp_file_id or "").strip()]
    if not temp_file_ids:
        return {}
    rows = db.query(TempResource).filter(TempResource.temp_file_id.in_(temp_file_ids)).all()
    return {str(row.temp_file_id or ""): row for row in rows if (row.temp_file_id or "").strip()}


def _build_assets_payload(
    project: ModernizationProject,
    db: Session,
    *,
    asset_manifest: list[Any] | None = None,
) -> list[dict[str, Any]]:
    effective_manifest = asset_manifest if asset_manifest is not None else _parse_json_list(project.asset_manifest_json)
    asset_rows = _ordered_project_assets(project, db, asset_manifest=effective_manifest if asset_manifest is not None else None)
    if asset_rows:
        temp_map = _temp_resource_map_for_assets(asset_rows, db)
        enriched_assets = []
        for asset in asset_rows:
            temp_resource = temp_map.get(asset.source_temp_file_id or "")
            content_type = (asset.content_type or "").strip() or ((temp_resource.content_type or "").strip() if temp_resource else "")
            uploaded_at = temp_resource.created_at if temp_resource and temp_resource.created_at else asset.created_at
            stage_status = ((temp_resource.stage_status or "").strip() if temp_resource else "") or "promoted"
            download_url = f"/projects/{project.id}/assets/{asset.id}/download"
            enriched_assets.append(
                {
                    "project_asset_id": asset.id,
                    "name": asset.original_filename,
                    "temp_file_id": asset.source_temp_file_id,
                    "size": asset.file_size,
                    "category_hint": asset.category_hint,
                    "extracted_chars": asset.extracted_chars,
                    "download_url": download_url,
                    "content_type": content_type or None,
                    "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
                    "stage_status": stage_status,
                    "is_downloadable": bool(asset.id and download_url),
                }
            )
        if effective_manifest:
            included_temp_ids = {
                str(asset.get("temp_file_id") or "").strip()
                for asset in enriched_assets
                if str(asset.get("temp_file_id") or "").strip()
            }
            for item in effective_manifest:
                temp_file_id = str(item.get("temp_file_id") or "").strip()
                if temp_file_id and temp_file_id in included_temp_ids:
                    continue
                enriched_assets.append(
                    {
                        "project_asset_id": None,
                        "name": item.get("name") or "-",
                        "temp_file_id": temp_file_id,
                        "size": item.get("size") or 0,
                        "category_hint": item.get("category_hint") or "",
                        "extracted_chars": None,
                        "download_url": None,
                        "content_type": None,
                        "uploaded_at": None,
                        "stage_status": None,
                        "is_downloadable": False,
                    }
                )
        return enriched_assets

    fallback = []
    for item in effective_manifest:
        fallback.append(
            {
                "project_asset_id": None,
                "name": item.get("name") or "-",
                "temp_file_id": item.get("temp_file_id") or "",
                "size": item.get("size") or 0,
                "category_hint": item.get("category_hint") or "",
                "extracted_chars": None,
                "download_url": None,
                "content_type": None,
                "uploaded_at": None,
                "stage_status": None,
                "is_downloadable": False,
            }
        )
    return fallback


def _make_project_history_id() -> str:
    return f"prh_{uuid.uuid4().hex[:12]}"


def _domain_axis_signal_scores(text: str) -> dict[str, int]:
    normalized = (text or "").lower()
    order_terms = (
        "주문", "마감", "order", "close", "closure", "delivery_hold", "deliveryhold",
        "vip", "review_required", "agency", "channel_code", "orderclose", "sales_order",
    )
    claim_terms = (
        "청구", "조정", "claim", "adjust", "fraud", "claim_audit", "hq_reviewer",
        "branch_manager", "b99", "insurance_claim", "accident_type",
    )
    return {
        "주문 마감": sum(normalized.count(term.lower()) for term in order_terms),
        "청구 조정": sum(normalized.count(term.lower()) for term in claim_terms),
    }


def _asset_domain_warning_message(expected_domain: str, asset_domain: str) -> str:
    return (
        "프로젝트 목표와 업로드 자산의 도메인 축이 일치하지 않을 가능성이 있습니다. "
        f"현재 입력은 '{expected_domain}' 목표로 생성되었지만, 업로드 자산은 '{asset_domain}' 규칙 신호가 더 강합니다. "
        "입력 파일을 다시 확인해야 합니다."
    )


def _detect_domain_mismatch_warning(
    *,
    project_name: str,
    goal: str = "",
    constraints: list[str],
    asset_names: list[str],
    asset_texts: list[str],
) -> list[str]:
    input_text = " ".join(part for part in [goal, project_name, *constraints] if str(part or "").strip())
    asset_text = " ".join([*asset_names, *asset_texts])
    input_scores = _domain_axis_signal_scores(input_text)
    asset_scores = _domain_axis_signal_scores(asset_text)
    input_domain = max(input_scores, key=input_scores.get)
    asset_domain = max(asset_scores, key=asset_scores.get)
    input_strength = input_scores.get(input_domain, 0)
    asset_strength = asset_scores.get(asset_domain, 0)
    opposite_asset_strength = asset_scores.get(input_domain, 0)
    if input_strength < 2 or asset_strength < 2:
        return []
    if input_domain == asset_domain:
        return []
    if asset_strength <= opposite_asset_strength:
        return []
    return [_asset_domain_warning_message(input_domain, asset_domain)]


def _project_domain_warnings(project: ModernizationProject, db: Session) -> list[str]:
    ordered_assets = _ordered_project_assets(project, db)
    asset_names = [asset.original_filename for asset in ordered_assets]
    asset_texts = []
    for asset in ordered_assets:
        try:
            asset_texts.append(read_text(asset.extracted_relative_path, project_asset=True)[:1200])
        except FileNotFoundError:
            continue
    return _detect_domain_mismatch_warning(
        project_name=project.project_name,
        goal=_project_text(project, "goal_text"),
        constraints=_parse_json_list(project.constraints_json),
        asset_names=asset_names,
        asset_texts=asset_texts,
    )


def _resolved_project_goal(
    project: ModernizationProject,
    *,
    safe_bundle,
    db: Session,
) -> str:
    stored_goal = _project_text(project, "goal_text")
    if stored_goal:
        return stored_goal
    resolved_goal = resolve_project_goal(
        inline_goal="",
        safe_bundle=safe_bundle,
        project_name=_project_text(project, "project_name"),
        client_name=_project_text(project, "client_name"),
    )
    if resolved_goal and resolved_goal != stored_goal:
        project.goal_text = resolved_goal
        db.add(project)
        db.commit()
        db.refresh(project)
    return resolved_goal


def _history_sequence_next(project_id: str, db: Session) -> int:
    rows = _project_history_rows(project_id, db)
    if not rows:
        return 1
    return max(int(row.sequence_no or 0) for row in rows) + 1


def _project_workspace_url(project_id: str) -> str:
    return f"/projects/{quote(str(project_id))}"


def _project_result_url(project_id: str, run_id: str | None = None) -> str:
    base = f"{_project_workspace_url(project_id)}/result"
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return base
    return f"{base}?run_id={quote(normalized_run_id)}"


_HIDDEN_TEST_UPLOAD_SESSION_PREFIXES = (
    "phase1-",
    "upload_large_structured_",
    "upload_customer_intent_",
)

_HIDDEN_TEST_UPLOAD_SESSION_EXACT = {
    "fallback-session",
    "history-session",
    "anonymization-session",
}


def _is_hidden_test_project(project: ModernizationProject) -> bool:
    upload_session_id = str(getattr(project, "upload_session_id", "") or "").strip()
    if not upload_session_id:
        return False
    if upload_session_id in _HIDDEN_TEST_UPLOAD_SESSION_EXACT:
        return True
    return any(upload_session_id.startswith(prefix) for prefix in _HIDDEN_TEST_UPLOAD_SESSION_PREFIXES)


def _run_status_map(run_ids: list[str], db: Session) -> dict[str, str]:
    normalized_ids = [str(run_id or "").strip() for run_id in run_ids if str(run_id or "").strip()]
    if not normalized_ids:
        return {}
    rows = db.query(AgentRun).filter(AgentRun.run_id.in_(normalized_ids)).all()
    return {str(row.run_id): str(row.status or "") for row in rows if row.run_id}


def _build_run_history_payload(project: ModernizationProject, db: Session) -> list[dict[str, Any]]:
    rows = _project_history_rows(project.id, db)
    if not rows:
        return []
    status_map = _run_status_map([row.run_id for row in rows], db)
    latest_run_id = str(project.run_id or "")
    payload = []
    for row in rows:
        manifest = _parse_json_list(row.asset_manifest_json)
        payload.append(
            {
                "run_id": row.run_id,
                "sequence_no": row.sequence_no,
                "trigger_kind": row.trigger_kind,
                "status": status_map.get(row.run_id, ""),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "asset_count": len(manifest),
                "is_latest": str(row.run_id or "") == latest_run_id,
                "workspace_url": _project_workspace_url(project.id),
                "result_url": _project_result_url(project.id, row.run_id) if status_map.get(row.run_id, "").lower() == "completed" else None,
            }
        )
    return payload


def _status_bucket(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "running":
        return "running"
    if normalized in {"pending", "waiting", "queued"}:
        return "pending"
    if normalized == "completed":
        return "completed"
    if normalized == "failed":
        return "failed"
    return "other"


def _build_recent_project_entries(projects: list[ModernizationProject], db: Session) -> list[dict[str, Any]]:
    if not projects:
        return []

    project_ids = [str(project.id) for project in projects if str(project.id or "").strip()]
    history_rows = (
        db.query(ProjectRunHistory)
        .filter(ProjectRunHistory.project_id.in_(project_ids))
        .order_by(ProjectRunHistory.created_at.desc(), ProjectRunHistory.sequence_no.desc(), ProjectRunHistory.id.desc())
        .all()
    )
    history_by_project: dict[str, list[ProjectRunHistory]] = {}
    for row in history_rows:
        history_by_project.setdefault(str(row.project_id), []).append(row)

    all_run_ids = [str(project.run_id) for project in projects if str(project.run_id or "").strip()]
    all_run_ids.extend(str(row.run_id) for row in history_rows if str(row.run_id or "").strip())
    status_map = _run_status_map(all_run_ids, db)

    entries: list[dict[str, Any]] = []
    for project in projects:
        project_id = str(project.id)
        rows = history_by_project.get(project_id) or []
        if not rows:
            manifest = _parse_json_list(project.asset_manifest_json)
            status = status_map.get(str(project.run_id), project.status or "")
            entries.append(
                {
                    "project_id": project_id,
                    "run_id": project.run_id,
                    "project_name": project.project_name,
                    "client_name": project.client_name,
                    "status": status,
                    "status_bucket": _status_bucket(status),
                    "sequence_no": 1,
                    "trigger_kind": "initial",
                    "created_at": project.updated_at.isoformat() if project.updated_at else (project.created_at.isoformat() if project.created_at else None),
                    "asset_count": len(manifest),
                    "is_latest": True,
                    "workspace_url": _project_workspace_url(project_id),
                    "result_url": _project_result_url(project_id, project.run_id) if str(status).strip().lower() == "completed" else None,
                }
            )
            continue

        for row in rows:
            manifest = _parse_json_list(row.asset_manifest_json)
            status = status_map.get(str(row.run_id), "")
            entries.append(
                {
                    "project_id": project_id,
                    "run_id": row.run_id,
                    "project_name": project.project_name,
                    "client_name": project.client_name,
                    "status": status,
                    "status_bucket": _status_bucket(status),
                    "sequence_no": row.sequence_no,
                    "trigger_kind": row.trigger_kind,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "asset_count": len(manifest),
                    "is_latest": str(row.run_id or "") == str(project.run_id or ""),
                    "workspace_url": _project_workspace_url(project_id),
                    "result_url": _project_result_url(project_id, row.run_id) if str(status).strip().lower() == "completed" else None,
                }
            )

    bucket_order = {"running": 0, "pending": 1, "completed": 2, "failed": 3, "other": 4}
    return sorted(
        entries,
        key=lambda item: (
            bucket_order.get(str(item.get("status_bucket") or "other"), 3),
            -(datetime.fromisoformat(str(item.get("created_at") or "1970-01-01T00:00:00+00:00").replace("Z", "+00:00")).timestamp()),
            -int(item.get("sequence_no") or 0),
        ),
    )


def _create_history_row(
    *,
    project_id: str,
    run_id: str,
    sequence_no: int,
    trigger_kind: str,
    asset_manifest_json: str,
) -> ProjectRunHistory:
    return ProjectRunHistory(
        id=_make_project_history_id(),
        project_id=project_id,
        run_id=run_id,
        sequence_no=sequence_no,
        trigger_kind=trigger_kind,
        asset_manifest_json=asset_manifest_json,
    )


def _ensure_initial_history(project: ModernizationProject, db: Session) -> list[ProjectRunHistory]:
    rows = _project_history_rows(project.id, db)
    if rows:
        return rows
    initial = _create_history_row(
        project_id=project.id,
        run_id=project.run_id,
        sequence_no=1,
        trigger_kind="initial",
        asset_manifest_json=project.asset_manifest_json or "[]",
    )
    db.add(initial)
    db.commit()
    return _project_history_rows(project.id, db)


def _asset_manifest_from_models(items: list[ProjectAssetItem]) -> list[dict[str, Any]]:
    return [item.model_dump() for item in items]


def _asset_manifest_from_project_assets(project: ModernizationProject, db: Session) -> list[dict[str, Any]]:
    assets = _ordered_project_assets(project, db)
    if not assets:
        return _parse_json_list(project.asset_manifest_json)
    return [
        {
            "name": asset.original_filename,
            "temp_file_id": asset.source_temp_file_id,
            "size": asset.file_size,
            "category_hint": asset.category_hint,
        }
        for asset in assets
    ]


def _rebuild_project_temp_context(project: ModernizationProject, db: Session) -> None:
    ordered_assets = _ordered_project_assets(project, db)
    context_parts = [
        (asset.original_filename, read_text(asset.extracted_relative_path, project_asset=True))
        for asset in ordered_assets
    ]
    app_state.TEMP_CONTEXT_STORE[project.upload_session_id] = build_temp_context(context_parts)


def _build_safe_bundle_for_project(project: ModernizationProject, db: Session):
    assets: list[AnonymizationAsset] = []
    for asset in _ordered_project_assets(project, db):
        try:
            original_path = resolve_project_asset_path(asset.stored_relative_path)
            extracted_text = read_text(asset.extracted_relative_path, project_asset=True)
            original_bytes = original_path.read_bytes()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="프로젝트 자산 파일을 불러올 수 없습니다.") from exc
        assets.append(
            AnonymizationAsset(
                asset_id=asset.id,
                name=asset.original_filename,
                temp_file_id=asset.source_temp_file_id,
                size=asset.file_size or 0,
                kind_hint=asset.category_hint or "",
                content_text=extracted_text,
                original_bytes=original_bytes,
            )
        )
    request = AnonymizationRunRequest(
        project_id=project.id,
        upload_session_id=project.upload_session_id,
        masking_level=MaskingLevel.FULL,
        assets=assets,
    )
    # High-risk review remains advisory at project creation time. The project can
    # still start, but the safe bundle handed to downstream analysis must mask
    # label-less candidates so raw document entities do not reach the LLM path.
    anonymization_result = AnonymizationService().run_anonymization_pipeline(request)
    return anonymization_result.safe_bundle


def _constraint_strings(values: list[Any]) -> list[str]:
    return [str(item).strip() for item in values if str(item or "").strip()]


def _persist_analysis_context(context: AnalysisContextBundle, db: Session) -> AnalysisContext:
    payload_json = json.dumps(context.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    row = db.query(AnalysisContext).filter(AnalysisContext.run_id == context.run.run_id).first()
    if row is None:
        row = AnalysisContext(
            context_id=context.context_id,
            project_id=context.project.project_id,
            run_id=context.run.run_id,
            safe_bundle_id=context.trust.safe_bundle_id,
            input_fingerprint=context.run.input_fingerprint,
            schema_version=context.schema_version,
            payload_json=payload_json,
        )
        db.add(row)
    else:
        row.context_id = context.context_id
        row.project_id = context.project.project_id
        row.safe_bundle_id = context.trust.safe_bundle_id
        row.input_fingerprint = context.run.input_fingerprint
        row.schema_version = context.schema_version
        row.payload_json = payload_json
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _build_and_store_analysis_context(
    project: ModernizationProject,
    *,
    run_id: str,
    safe_bundle,
    goal: str,
    constraints: list[Any],
    db: Session,
) -> AnalysisContextBundle:
    context = AnalysisContextBuilder().build(
        project_id=project.id,
        run_id=run_id,
        safe_bundle=safe_bundle,
        goal=goal,
        constraints=_constraint_strings(constraints),
        project_name=project.project_name,
        client_name=project.client_name,
        template_key=project.template_key,
        warnings=_project_domain_warnings(project, db),
    )
    prepared = RebuildAssistantService().prepare_analysis_context_input(analysis_context=context)
    context.trust.missing_context = list(prepared.missing_context or [])
    question_guard_summary = getattr(prepared, "question_guard_summary", None)
    if question_guard_summary is not None:
        if getattr(question_guard_summary, "blocked_question_count", 0):
            context.trust.warnings.append("질문 중 일부가 소스 근거 부족으로 분석 입력에서 제외되었습니다.")
        if getattr(question_guard_summary, "needs_review", False):
            context.trust.warnings.append("소스 기반 질문 후보가 부족하거나 사용자 질문 일부가 재검토 상태입니다.")
    context.analysis_frame.concept_signals = list(prepared.signals.concepts or [])
    context.analysis_frame.primary_feature_mode = prepared.signals.primary_feature_mode
    context.analysis_frame.scope_limited = bool(prepared.scope_limited)
    _persist_analysis_context(context, db)
    return context


def _validate_reanalysis_assets(
    project: ModernizationProject,
    payload: ProjectReanalysisRequest,
    user: User,
    db: Session,
) -> list[tuple[ProjectAssetItem, TempResource]]:
    items = payload.new_asset_manifest or []
    if not items:
        return []

    temp_file_ids = [item.temp_file_id for item in items]
    if len(set(temp_file_ids)) != len(temp_file_ids):
        raise HTTPException(status_code=400, detail="Duplicate temp_file_id values are not allowed")

    existing_ids = {
        str(item.get("temp_file_id") or "").strip()
        for item in _parse_json_list(project.asset_manifest_json)
        if str(item.get("temp_file_id") or "").strip()
    }
    duplicate_existing = next((temp_file_id for temp_file_id in temp_file_ids if temp_file_id in existing_ids), None)
    if duplicate_existing:
        raise HTTPException(status_code=400, detail=f"temp_file_id already exists in project manifest: {duplicate_existing}")

    rows = db.query(TempResource).filter(TempResource.temp_file_id.in_(temp_file_ids)).all()
    row_map = {row.temp_file_id: row for row in rows if row.temp_file_id}
    missing = next((temp_file_id for temp_file_id in temp_file_ids if temp_file_id not in row_map), None)
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown temp_file_id: {missing}")

    ordered: list[tuple[ProjectAssetItem, TempResource]] = []
    for asset_item in items:
        row = row_map[asset_item.temp_file_id]
        if row.user_id != user.id:
            raise HTTPException(status_code=403, detail="다른 사용자의 업로드 자산은 프로젝트에 포함할 수 없습니다.")
        if row.temp_session_id != project.upload_session_id:
            raise HTTPException(status_code=400, detail="asset temp_file_id does not belong to project upload_session_id")
        if (row.stage_status or "staged") != "staged":
            raise HTTPException(status_code=400, detail="Only staged uploads can be promoted into a project")
        if not row.file_path or not row.extracted_relative_path:
            raise HTTPException(status_code=400, detail="Staged upload is incomplete")
        ordered.append((asset_item, row))
    return ordered


def _normalize_utc_iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _build_result_provenance(
    project: ModernizationProject,
    snapshot: dict[str, Any] | None,
    *,
    assets: list[dict[str, Any]],
    app_version: str | None,
) -> dict[str, Any]:
    snapshot = snapshot or {}
    generated_at = (
        _normalize_utc_iso(snapshot.get("updated_at"))
        or _normalize_utc_iso(snapshot.get("created_at"))
        or _normalize_utc_iso(_project_attr(project, "created_at", None))
    )
    return {
        "run_id": snapshot.get("run_id") or _project_text(project, "run_id"),
        "module_id": snapshot.get("module_id") or REBUILD_ASSISTANT_MANIFEST.module_id,
        "run_kind": snapshot.get("run_kind") or REBUILD_ASSISTANT_MANIFEST.run_kind,
        "generated_at": generated_at,
        "app_version": (app_version or "").strip() or "unknown",
        "module_version": MODULE_VERSION,
        "template_key": _project_text(project, "template_key"),
        "run_status": snapshot.get("status") or _project_text(project, "status"),
        "input_assets": [dict(item) for item in assets],
    }


def _trim_items(items: list[str] | None, *, limit: int = 3) -> list[str]:
    normalized = [str(item).strip() for item in (items or []) if str(item).strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in normalized:
        key = re.sub(r"\s+", " ", item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:limit]


def _dedupe_dict_items(items: list[dict[str, Any]], key_field: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        value = str(item.get(key_field) or "").strip()
        key = re.sub(r"\s+", " ", value).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _humanize_summary_state(state: str) -> str:
    mapping = {
        "ready": "준비 완료",
        "partial": "부분 준비",
        "pending": "생성 중",
    }
    return mapping.get((state or "").strip().lower(), state)


def _humanize_accounting_method(value: str) -> str:
    mapping = {
        "MOVING_AVERAGE": "이동평균법",
        "FIFO": "선입선출법",
        "SPECIFIC_ID": "개별식별법",
    }
    return mapping.get((value or "").strip().upper(), value)


def _humanize_accounting_status(value: str) -> str:
    mapping = {
        "completed": "완료",
        "failed": "실패",
        "skipped": "건너뜀",
        "input_missing": "입력 부족",
    }
    return mapping.get((value or "").strip().lower(), value)


def _humanize_accounting_reason(value: str) -> str:
    text = (value or "").strip()
    mapping = {
        "all required inputs present": "필수 입력이 모두 제공되었습니다.",
        "voucher_review requires vouchers and account_mappings": "전표 데이터와 계정 매핑이 없어 전표 검토를 수행할 수 없습니다.",
        "missing exchange_rates": "환율 데이터가 누락되었습니다.",
        "missing required inputs: transactions": "거래 데이터가 누락되었습니다.",
        "missing required inputs: exchange_rates": "환율 데이터가 누락되었습니다.",
        "missing required inputs: policies": "회계 정책 데이터가 누락되었습니다.",
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
        labels = {
            "transactions": "거래 데이터",
            "exchange_rates": "환율 데이터",
            "policies": "회계 정책 데이터",
            "vouchers": "전표 데이터",
            "account_mappings": "계정 매핑",
        }
        humanized = ", ".join(labels.get(item.strip(), item.strip()) for item in missing.split(",") if item.strip())
        return f"필수 입력이 누락되었습니다. ({humanized})"
    if "ambiguous exchange rate" in text.lower() or "multiple exchange rates" in text.lower():
        return "복수 환율이 감지되어 적용 환율을 확정할 수 없습니다."
    for raw, replacement in (
        ("MOVING_AVERAGE", "이동평균법"),
        ("FIFO", "선입선출법"),
        ("SPECIFIC_ID", "개별식별법"),
        ("input_missing", "입력 부족"),
        ("completed", "완료"),
        ("failed", "실패"),
    ):
        text = re.sub(rf"\b{re.escape(raw)}\b", replacement, text)
    text = text.replace("일치해", "일치하여")
    return text


def _accounting_reason_label(value: str) -> str:
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
    if "multiple exchange rates" in lowered or "ambiguous exchange rate" in lowered:
        return "복수 환율 충돌"
    if "policy" in lowered or "version" in lowered:
        return "회계 정책 경고"
    if "voucher" in lowered or "전표" in lowered:
        return "전표 검토 입력 부족"
    humanized = _humanize_accounting_reason(text).rstrip(".")
    missing_match = re.search(r"(.+?)(?:이|가) 누락되었습니다$", humanized)
    if missing_match:
        return f"{missing_match.group(1).strip()} 누락"
    return humanized


def _humanize_accounting_message(value: str) -> str:
    text = _humanize_accounting_reason(value)
    text = re.sub(
        r"^([A-Za-z0-9_-]+)\s전표는\s차변/대변이 일치하지 않습니다\.$",
        r"\1 전표의 차변/대변이 일치하지 않습니다.",
        text,
    )
    text = re.sub(
        r"^([A-Za-z0-9_-]+)\s전표는\s차변/대변 균형이 맞습니다\.$",
        r"\1 전표의 차변/대변 균형이 맞습니다.",
        text,
    )
    return text


def _humanize_accounting_summary_sentence(value: str) -> str:
    text = (value or "").strip()
    prefix = "회계 계산을 수행할 수 없습니다."
    if text.startswith(prefix):
        detail = text[len(prefix):].strip()
        return f"{prefix} {_humanize_accounting_reason(detail)}".strip()
    return text


def _build_accounting_package_view(accounting: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(accounting, dict):
        return None
    output = deepcopy(accounting)
    if output.get("summary_sentence"):
        output["summary_sentence"] = _humanize_accounting_summary_sentence(str(output.get("summary_sentence") or ""))
    calc_status = output.get("calculation_status")
    if isinstance(calc_status, dict):
        if calc_status.get("reason"):
            calc_status["reason"] = _humanize_accounting_reason(str(calc_status.get("reason") or ""))
        if calc_status.get("blocking_issue"):
            calc_status["blocking_issue"] = _humanize_accounting_reason(str(calc_status.get("blocking_issue") or ""))
    analysis = output.get("accounting_analysis")
    if isinstance(analysis, dict):
        if isinstance(analysis.get("candidate_methods"), list):
            analysis["candidate_methods"] = [_humanize_accounting_method(str(item)) for item in analysis.get("candidate_methods") or []]
        if analysis.get("recommended_method"):
            analysis["recommended_method"] = _humanize_accounting_method(str(analysis.get("recommended_method") or ""))
        for item in analysis.get("reasons") or []:
            if isinstance(item, dict) and item.get("message"):
                item["message"] = _humanize_accounting_message(str(item.get("message") or ""))
    fx_calc = output.get("fx_calculation")
    if isinstance(fx_calc, dict):
        if fx_calc.get("status"):
            fx_calc["status"] = _humanize_accounting_status(str(fx_calc.get("status") or ""))
        if fx_calc.get("method"):
            fx_calc["method"] = _humanize_accounting_method(str(fx_calc.get("method") or ""))
        if fx_calc.get("failure_reason"):
            fx_calc["failure_reason"] = _humanize_accounting_reason(str(fx_calc.get("failure_reason") or ""))
        for item in fx_calc.get("detail_steps") or []:
            if isinstance(item, dict) and item.get("message"):
                item["message"] = _humanize_accounting_message(str(item.get("message") or ""))
    voucher_review = output.get("voucher_review")
    if isinstance(voucher_review, dict):
        if voucher_review.get("status"):
            voucher_review["status"] = _humanize_accounting_status(str(voucher_review.get("status") or ""))
        if voucher_review.get("failure_reason"):
            voucher_review["failure_reason"] = _humanize_accounting_reason(str(voucher_review.get("failure_reason") or ""))
        for item in voucher_review.get("review_points") or []:
            if isinstance(item, dict) and item.get("message"):
                item["message"] = _humanize_accounting_message(str(item.get("message") or ""))
        for item in voucher_review.get("mismatches") or []:
            if isinstance(item, dict) and item.get("message"):
                item["message"] = _humanize_accounting_message(str(item.get("message") or ""))
    return output


def _build_executive_next_steps(
    *,
    missing_context_details: list[dict[str, Any]],
    recommended_directions: list[str],
    accounting: dict[str, Any] | None = None,
) -> list[str]:
    if isinstance(accounting, dict):
        calc_status = accounting.get("calculation_status") or {}
        input_validation = accounting.get("input_validation") or {}
        fx_calc = accounting.get("fx_calculation") or {}
        voucher_review = accounting.get("voucher_review") or {}
        warnings: list[str] = []
        warnings.extend(str(item or "").strip() for item in (input_validation.get("warnings") or []))
        warnings.extend(str(item or "").strip() for item in (input_validation.get("ambiguous_inputs") or []))
        warnings.extend(str(item or "").strip() for item in (fx_calc.get("warnings") or []))
        warnings.extend(str(item or "").strip() for item in (voucher_review.get("warnings") or []))
        warning_text = _humanize_accounting_reason(next((item for item in warnings if item), ""))
        if not bool(calc_status.get("can_calculate")):
            issue = _accounting_reason_label(str(calc_status.get("blocking_issue") or calc_status.get("reason") or "필수 입력이 누락되었습니다."))
            return [
                f"{issue} 항목을 우선 보완하는 것이 필요합니다.",
                "환율, 정책, 거래일 기준을 다시 확인하는 것이 필요합니다.",
                "보완 후 재계산과 전표 재검토를 수행하는 것이 필요합니다.",
            ]
        if warning_text:
            warning_label = _accounting_reason_label(next((item for item in warnings if item), ""))
            return [
                f"{warning_label} 경고를 먼저 확인하는 것이 필요합니다.",
                "입력과 정책 기준을 보완하는 것이 필요합니다.",
                "재계산 후 최종 기준을 확정하는 것이 필요합니다.",
            ]
        if str(voucher_review.get("status") or "").strip().lower() == "input_missing":
            return [
                "계산 결과와 적용 회계 방식을 먼저 확정하는 것이 필요합니다.",
                "전표 데이터와 계정 매핑을 보완해 전표 정합성 검토를 완료하는 것이 필요합니다.",
                "후속 운영 기준과 재계산 조건을 정리하는 것이 필요합니다.",
            ]
        return [
            "계산 결과와 적용 회계 방식을 먼저 확정하는 것이 필요합니다.",
            "전표 정합성 검토 결과를 함께 확인하는 것이 필요합니다.",
            "후속 운영 기준과 재계산 조건을 정리하는 것이 필요합니다.",
        ]
    if missing_context_details:
        first_required = str(missing_context_details[0].get("required_material") or "").strip() or "-"
        first = f"{first_required} 자료를 확보해 확인 필요 항목을 확정하는 것이 필요합니다."
    else:
        first = "추천안을 기준으로 현대화 방향과 분리 우선순위를 확정하는 것이 필요합니다."
    return [
        first,
        "단일 기능·단일 화면 기준으로 파일럿 범위를 고정하는 것이 필요합니다.",
        "추천안 기준으로 상세 설계 착수 여부와 후속 자산 확보 범위를 확정하는 것이 필요합니다.",
    ]


def _build_executive_summary(
    *,
    run_state: str,
    core_conclusion: str,
    recommended_directions: list[str],
    executive_summary_v2: list[str],
    grounded_business_rules: list[dict[str, Any]],
    decision_items: list[dict[str, Any]],
    analysis_summary: list[str],
    diagnosis: dict[str, Any],
    execution_plan: list[dict[str, Any]],
    recommended_option: dict[str, Any] | None,
    accounting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing_context_details = list(diagnosis.get("missing_context_details") or [])
    key_risks = _trim_items(list(diagnosis.get("risks") or []))[:3]
    decision_lines = _trim_items(
        [str(item.get("statement") or "").strip() for item in (decision_items or []) if str(item.get("statement") or "").strip()]
    )[:3]
    fallback_actions = _build_executive_next_steps(
        missing_context_details=missing_context_details,
        recommended_directions=decision_lines,
        accounting=accounting,
    )
    brief = build_decision_brief(
        summary=core_conclusion,
        rationale_candidates=[
            *(str(item.get("description") or "").strip() for item in (grounded_business_rules or [])),
            *(str(item.get("rationale") or "").strip() for item in (decision_items or [])),
            *analysis_summary,
            *executive_summary_v2,
            *key_risks,
        ],
        action_candidates=[
            *decision_lines,
            *(str(item.get("goal") or "").strip() for item in (execution_plan or [])),
            *recommended_directions,
            *fallback_actions,
        ],
    )
    summary_lines = list(brief.get("rationale_lines") or [])
    action_lines = list(brief.get("action_lines") or [])
    recommended_name = str((recommended_option or {}).get("name") or "").strip()
    has_core = bool(core_conclusion) or bool(_trim_items(executive_summary_v2)[:4])
    has_direction = bool(decision_lines)

    if has_core or has_direction:
        state = "ready"
    elif missing_context_details:
        state = "partial"
    else:
        state = "pending"

    if core_conclusion:
        core_message = str(brief.get("decision_summary") or "").strip() or core_conclusion
    elif state == "partial":
        core_message = "현재까지의 분석 결과를 기반으로 한 초안입니다."
    elif state == "pending":
        core_message = "분석 결과를 생성 중입니다."
    else:
        core_message = "결과를 요약할 수 있는 데이터가 아직 충분하지 않습니다."
    modernization_direction = _trim_items(recommended_directions)[:3] if recommended_directions else (_trim_items(action_lines)[:3] if state != "pending" else [])

    return {
        "title": "Decision Brief",
        "state": state,
        "core_message": core_message,
        "summary_lines": summary_lines,
        "modernization_direction": modernization_direction,
        "decision_focus": action_lines,
        "recommended_option": recommended_name,
        "key_risks": key_risks[:3],
        "next_steps": action_lines,
    }


def _clean_display_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^\s*(문제|영향|조치|다음 단계)\s*:\s*", "", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _ensure_display_sentence(value: Any) -> str:
    cleaned = _clean_display_text(value)
    if not cleaned:
        return ""
    if cleaned.endswith((".", "!", "?")):
        return cleaned
    return f"{cleaned}."


def _decisionize_display_text(value: Any) -> str:
    text = _ensure_display_sentence(value)
    if not text:
        return ""
    replacements = (
        ("확인되었습니다.", "걸려 있어 유지하지 않으면 실제 동작이 달라집니다."),
        ("확인되었습니다", "걸려 있어 유지하지 않으면 실제 동작이 달라집니다"),
        ("확인됩니다.", "드러나 그대로 두면 변경 영향 범위가 커집니다."),
        ("확인됩니다", "드러나 그대로 두면 변경 영향 범위가 커집니다"),
        ("존재합니다.", "남아 있어 그대로 두면 유지보수 비용이 커집니다."),
        ("존재합니다", "남아 있어 그대로 두면 유지보수 비용이 커집니다"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _display_action_phrase(value: Any) -> str:
    text = _clean_display_text(value).rstrip(".")
    if not text:
        return ""
    for pattern in (
        r"\s*하는 것이 필요합니다$",
        r"\s*해야 합니다$",
        r"\s*할 필요가 있습니다$",
        r"\s*가 필요합니다$",
        r"\s*이 필요합니다$",
        r"\s*입니다$",
    ):
        text = re.sub(pattern, "", text)
    return text.strip()


def _first_display_line(items: list[str]) -> str:
    for item in items:
        normalized = _clean_display_text(item)
        if normalized:
            return normalized
    return ""


def _display_empty_message(
    section_key: str,
    *,
    run_state: str,
    missing_context_details: list[dict[str, Any]] | None = None,
) -> str:
    first_required = ""
    if missing_context_details:
        first_required = str((missing_context_details[0] or {}).get("required_material") or "").strip()
    if run_state == "running":
        running_messages = {
            "grounded_rules": "핵심 규칙 근거가 아직 모이지 않아 이 판단을 확정하면 안 됩니다.",
            "design_options": "개선 전략 비교 근거가 아직 부족해 옵션 우선순위를 확정하면 안 됩니다.",
            "execution_plan": "실행 단계 근거가 아직 부족해 착수 순서를 고정하면 안 됩니다.",
            "risks": "리스크 근거가 아직 정리되지 않아 승인 범위를 먼저 줄여야 합니다.",
            "missing_context": "추가 확인 항목이 아직 정리되지 않아 누락 자료 범위를 다시 확인해야 합니다.",
            "retained_contracts": "유지 계약이 아직 정리되지 않아 보호 범위를 먼저 확정해야 합니다.",
            "priority_split": "분리 우선순위 근거가 아직 부족해 선행 작업을 고정하면 안 됩니다.",
            "verification": "확인 필요 항목이 아직 정리되지 않아 후속 검증 범위를 다시 잡아야 합니다.",
            "rebuild_strategy": "구조 전략이 아직 정리되지 않아 레이어 경계를 고정하면 안 됩니다.",
            "transition_draft": "전환 초안이 아직 정리되지 않아 구현 순서를 확정하면 안 됩니다.",
            "report_scope": "분석 범위가 비어 있어 이 결과만으로 적용 범위를 넓히면 안 됩니다.",
            "report_questions": "검증 질문이 비어 있어 승인 전에 확인 범위를 다시 정해야 합니다.",
        }
        return running_messages.get(section_key, "판단 근거가 아직 부족해 지금 결정을 고정하면 안 됩니다.")
    if first_required and section_key in {"grounded_rules", "risks", "missing_context", "verification"}:
        return f"{first_required} 자료가 비어 있어 이 판단을 바로 확정하면 안 됩니다."
    messages = {
        "grounded_rules": "핵심 규칙 근거가 부족해 구조를 고정하면 회귀 위험이 커집니다.",
        "design_options": "비교 가능한 전략 근거가 부족해 우선안을 고르기 전에 추가 근거를 확보해야 합니다.",
        "execution_plan": "착수 순서를 정할 근거가 부족해 파일럿 범위를 먼저 줄여야 합니다.",
        "risks": "노출된 리스크가 없더라도 영향 범위를 다시 점검해야 합니다.",
        "missing_context": "추가로 확보할 자료가 드러나지 않았더라도 승인 전에 누락 여부를 다시 확인해야 합니다.",
        "retained_contracts": "보호할 계약이 아직 정리되지 않아 변경 범위를 먼저 줄여야 합니다.",
        "priority_split": "우선순위 근거가 비어 있어 작업 순서를 바로 확정하면 안 됩니다.",
        "verification": "검증 체크포인트가 비어 있어 승인 전에 확인 범위를 다시 정해야 합니다.",
        "rebuild_strategy": "구조 전략 근거가 부족해 레이어 경계를 먼저 재정의해야 합니다.",
        "transition_draft": "전환 초안이 비어 있어 구현보다 경계 확정이 먼저입니다.",
        "report_scope": "분석 범위가 비어 있어 이 결과를 전체 시스템 결정으로 확대하면 안 됩니다.",
        "report_questions": "검증 질문이 비어 있어 승인 전에 확인할 질문부터 다시 정해야 합니다.",
    }
    return messages.get(section_key, "판단 근거가 부족해 지금 결정을 고정하면 안 됩니다.")


def _compose_one_line_conclusion(*, summary: str, impact: str, priority_action: str) -> str:
    parts: list[str] = []
    summary_sentence = _decisionize_display_text(summary).rstrip(".")
    impact_sentence = _decisionize_display_text(impact).rstrip(".")
    action_phrase = _display_action_phrase(priority_action)
    if summary_sentence:
        parts.append(summary_sentence)
    if impact_sentence and impact_sentence.lower() != summary_sentence.lower():
        parts.append(impact_sentence)
    if action_phrase:
        parts.append(f"우선 조치는 {action_phrase}입니다")
    if not parts:
        return "핵심 구조 문제를 다시 확인한 뒤 우선 조치를 확정해야 합니다."
    return ". ".join(parts).strip() + "."


def _priority_badge(index: int) -> str:
    if index <= 0:
        return "P0"
    if index == 1:
        return "P1"
    return "P2"


def _build_rule_action(rule: dict[str, Any]) -> str:
    targets = _trim_items(list(rule.get("design_targets") or []), limit=2)
    if targets:
        return f"{', '.join(targets)} 경계에서 이 규칙을 먼저 분리해 보는 편이 안전합니다."
    return "이 규칙을 한 경계에서 먼저 분리해 보는 편이 안전합니다."


def _build_rule_impact(rule: dict[str, Any]) -> str:
    title = str(rule.get("title") or "이 규칙").strip() or "이 규칙"
    if bool(rule.get("needs_verification")):
        return f"{title} 규칙을 근거 없이 확정하면 실제 동작과 다른 보호 조건을 만들 수 있습니다."
    return f"{title} 규칙이 빠지면 처리 결과와 권한 범위가 달라질 수 있습니다."


def _build_rule_anti_pattern(rule: dict[str, Any]) -> str:
    return "같은 규칙을 화면, 서비스, SQL에 흩어 두지 말아야 합니다."


def _build_rule_unchanged_consequence(rule: dict[str, Any]) -> str:
    title = str(rule.get("title") or "").strip()
    targets = " ".join(str(item or "") for item in (rule.get("design_targets") or []))
    haystack = f"{title} {targets}".lower()
    if "검증" in haystack or "validator" in haystack:
        return "이 규칙 정리를 미루면 동일 검증 기준 수정이 여러 경로에 남습니다."
    if "정책" in haystack or "상태" in haystack:
        return "이 규칙 정리를 미루면 권한과 상태 변경이 화면과 서비스 양쪽에 계속 남습니다."
    if "sql" in haystack or "조회" in haystack:
        return "이 규칙 정리를 미루면 조회 조건 변경이 화면과 SQL 양쪽으로 번집니다."
    return "이 규칙 정리를 미루면 변경 시 파급 범위가 계속 넓게 남습니다."


def _build_rule_priority(index: int, rule: dict[str, Any]) -> str:
    confidence = str(rule.get("confidence") or "").strip()
    if confidence == "확정" and not bool(rule.get("needs_verification")):
        return "P0"
    return _priority_badge(index + 1)


def _build_rule_priority_reason(priority: str, rule: dict[str, Any]) -> str:
    if priority == "P0":
        return "직접 근거가 잡혀 있어 먼저 보호하지 않으면 실제 동작이 달라질 수 있습니다."
    if priority == "P1":
        return "핵심 흐름과 연결돼 있어 초기 설계 범위 안에서 함께 검토하는 편이 안전합니다."
    return "보조 규칙이지만 뒤로 미루면 후속 수정 지점이 늘어날 수 있습니다."


def _build_evidence_importance(rule: dict[str, Any]) -> str:
    title = str(rule.get("title") or "핵심 규칙").strip() or "핵심 규칙"
    return f"{title} 규칙이 이 자산에도 걸려 있어 누락하면 실제 동작이 달라집니다."


def _build_display_grounded_rules(
    items: list[dict[str, Any]],
    *,
    run_state: str,
    missing_context_details: list[dict[str, Any]],
) -> dict[str, Any]:
    rendered_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        priority = _build_rule_priority(index, item)
        evidence_cards = []
        for row in list(item.get("evidence_cards") or []):
            evidence_cards.append(
                {
                    "asset_name": row.get("asset_name") or "-",
                    "condition_summary": _decisionize_display_text(row.get("condition_summary") or ""),
                    "why_important": _build_evidence_importance(item),
                    "design_targets": list(row.get("design_targets") or []),
                    "confidence": row.get("confidence") or "-",
                }
            )
        rendered_items.append(
            {
                "title": item.get("title") or "",
                "decision": _decisionize_display_text(item.get("description") or ""),
                "impact": _build_rule_impact(item),
                "action": _build_rule_action(item),
                "priority": priority,
                "priority_reason": _build_rule_priority_reason(priority, item),
                "anti_pattern": _build_rule_anti_pattern(item),
                "unchanged_consequence": _build_rule_unchanged_consequence(item),
                "confidence": item.get("confidence") or "가정",
                "confidence_reason": _decisionize_display_text(item.get("confidence_reason") or ""),
                "needs_verification": bool(item.get("needs_verification")),
                "design_targets": list(item.get("design_targets") or []),
                "evidence_cards": evidence_cards,
            }
        )
    return {
        "empty_message": _display_empty_message(
            "grounded_rules",
            run_state=run_state,
            missing_context_details=missing_context_details,
        ),
        "items": rendered_items,
    }


def _option_haystack(item: dict[str, Any]) -> str:
    return " ".join(
        [
            str(item.get("name") or ""),
            str(item.get("structure_summary") or ""),
            " ".join(str(entry or "") for entry in (item.get("advantages") or [])),
            " ".join(str(entry or "") for entry in (item.get("risks") or [])),
            str(item.get("selection_reason") or ""),
        ]
    ).lower()


def _build_option_improvement_breadth(item: dict[str, Any]) -> str:
    haystack = _option_haystack(item)
    if "화면" in haystack and "후속" in haystack:
        return "표현 계층 중심으로 구조 개선 폭이 작습니다."
    if any(token in haystack for token in ("모듈형", "검증 규칙 중심", "service", "api", "서비스")):
        return "서비스와 검증 경계까지 손대므로 구조 개선 폭이 큽니다."
    return "기능 단위 경계를 다시 나누는 수준의 중간 폭 개선입니다."


def _build_option_apply_scope(item: dict[str, Any]) -> str:
    haystack = _option_haystack(item)
    if "화면" in haystack and "api" not in haystack and "서비스" not in haystack:
        return "주로 화면과 입력 흐름에 적용됩니다."
    if any(token in haystack for token in ("api", "서비스", "backend", "검증")):
        return "API, 서비스, 검증 경계까지 함께 다룹니다."
    return "단일 기능 범위 전체에 적용됩니다."


def _build_option_expected_effect(item: dict[str, Any]) -> str:
    advantages = _trim_items(list(item.get("advantages") or []), limit=2)
    if advantages:
        return _decisionize_display_text(advantages[0])
    return _decisionize_display_text(item.get("selection_reason") or "구조 변경 범위를 더 선명하게 정리할 수 있습니다.")


def _build_option_prerequisite(item: dict[str, Any], missing_context_details: list[dict[str, Any]]) -> str:
    if missing_context_details:
        required = str((missing_context_details[0] or {}).get("required_material") or "").strip() or "추가 근거"
        return f"{required} 기준을 먼저 확인해야 적용 범위를 안정적으로 줄일 수 있습니다."
    haystack = _option_haystack(item)
    if any(token in haystack for token in ("검증", "정책", "규칙")):
        return "핵심 규칙과 유지 계약을 먼저 묶어 두는 편이 안전합니다."
    return "파일럿 범위와 회귀 확인 기준을 먼저 고정하는 편이 안전합니다."


def _build_option_unchanged_consequence(item: dict[str, Any]) -> str:
    haystack = _option_haystack(item)
    if "화면" in haystack and "후속" in haystack:
        return "이 수준의 구조 조정을 미루면 화면과 처리 경계가 계속 함께 움직입니다."
    if any(token in haystack for token in ("검증", "정규", "validator")):
        return "이 수준의 구조 조정을 미루면 검증 기준 수정이 여러 위치에 계속 남습니다."
    if any(token in haystack for token in ("service", "서비스", "api")):
        return "이 수준의 구조 조정을 미루면 UI와 서비스 결합이 계속 남습니다."
    return "이 수준의 구조 조정을 미루면 변경 시 파급 범위가 계속 넓게 남습니다."


def _build_option_priority(index: int, item: dict[str, Any]) -> str:
    if bool(item.get("recommended")):
        return "P0"
    return _priority_badge(index)


def _build_option_priority_reason(priority: str, item: dict[str, Any]) -> str:
    if priority == "P0":
        return "현재 결합을 가장 많이 줄이는 선택지라 먼저 비교해 볼 가치가 큽니다."
    if priority == "P1":
        return "대안으로 유지할 가치가 있지만 적용 범위와 비용을 함께 봐야 합니다."
    return "후순위 선택지라면 화면 효과보다 구조 효과를 먼저 비교하는 편이 안전합니다."


def _build_option_comparison_points(item: dict[str, Any], *, missing_context_details: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"label": "구조 개선 폭", "value": _build_option_improvement_breadth(item)},
        {"label": "적용 범위", "value": _build_option_apply_scope(item)},
        {"label": "구현 난이도", "value": str(item.get("difficulty") or "-")},
        {"label": "예상 효과", "value": _build_option_expected_effect(item)},
        {"label": "선행 조건", "value": _build_option_prerequisite(item, missing_context_details)},
        {"label": "미조치 시 영향", "value": _build_option_unchanged_consequence(item)},
    ]


def _build_display_design_options(
    items: list[dict[str, Any]],
    *,
    run_state: str,
    missing_context_details: list[dict[str, Any]],
) -> dict[str, Any]:
    rendered_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        advantages = _trim_items(list(item.get("advantages") or []), limit=3)
        risks = _trim_items(list(item.get("risks") or []), limit=3)
        priority = _build_option_priority(index, item)
        rendered_items.append(
            {
                "name": item.get("name") or "",
                "decision": _decisionize_display_text(item.get("structure_summary") or ""),
                "action": _decisionize_display_text(_first_display_line(advantages) or item.get("selection_reason") or ""),
                "anti_pattern": _decisionize_display_text(_first_display_line(risks) or "핵심 규칙 분리를 뒤로 미루지 말아야 합니다."),
                "priority": priority,
                "priority_reason": _build_option_priority_reason(priority, item),
                "difficulty": item.get("difficulty") or "-",
                "duration_weeks": item.get("duration_weeks") or 0,
                "advantages": advantages,
                "risks": risks,
                "selection_reason": _decisionize_display_text(item.get("selection_reason") or ""),
                "unchanged_consequence": _build_option_unchanged_consequence(item),
                "comparison_points": _build_option_comparison_points(item, missing_context_details=missing_context_details),
                "recommended": bool(item.get("recommended")),
            }
        )
    return {
        "empty_message": _display_empty_message("design_options", run_state=run_state, missing_context_details=[]),
        "items": rendered_items,
    }


def _build_display_execution_plan(
    items: list[dict[str, Any]],
    *,
    run_state: str,
    analysis_first_surface: bool = False,
) -> dict[str, Any]:
    rendered_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        tasks = _trim_items(list(item.get("tasks") or []), limit=4)
        priority = _priority_badge(index)
        decision_text = (
            _ensure_display_sentence(item.get("goal") or "")
            if analysis_first_surface
            else _decisionize_display_text(item.get("goal") or "")
        )
        action_text = (
            _ensure_display_sentence(_first_display_line(tasks) or item.get("goal") or "")
            if analysis_first_surface
            else _decisionize_display_text(_first_display_line(tasks) or item.get("goal") or "")
        )
        rendered_items.append(
            {
                "week_label": item.get("week_label") or "",
                "decision": decision_text,
                "action": action_text,
                "priority": priority,
                "priority_reason": (
                    "현행 처리 순서를 먼저 맞춰야 다음 검토가 같은 흐름을 기준으로 이어집니다."
                    if analysis_first_surface and priority == "P0"
                    else (
                        "계산 기준과 연계 조건을 같은 흐름 기준으로 확인하는 중간 단계입니다."
                        if analysis_first_surface and priority == "P1"
                        else (
                            "운영 리스크와 후속 확인 항목을 정리하는 마무리 단계입니다."
                            if analysis_first_surface
                            else (
                                "후속 설계 기준을 먼저 고정해야 해 앞 단계 우선순위가 높습니다."
                                if priority == "P0"
                                else ("선행 기준 위에서 진행되는 중간 단계입니다." if priority == "P1" else "마무리 검증에 가까운 후속 단계입니다.")
                            )
                        )
                    )
                ),
                "unchanged_consequence": (
                    "이 단계를 미루면 후속 검토가 같은 처리 순서를 기준으로 이어지지 못합니다."
                    if analysis_first_surface and priority == "P0"
                    else (
                        "이 단계를 미루면 계산 기준과 연계 조건 점검이 다시 흩어질 수 있습니다."
                        if analysis_first_surface and priority == "P1"
                        else (
                            "이 단계를 미루면 운영 리스크와 후속 확인 항목이 불완전하게 남습니다."
                            if analysis_first_surface
                            else ("이 단계를 미루면 다음 단계가 같은 근거를 공유하지 못합니다."
                                if priority == "P0"
                                else ("이 단계를 미루면 구현과 검증 시점이 다시 벌어질 수 있습니다." if priority == "P1" else "이 단계를 미루면 최종 확인과 승인 일정이 뒤로 밀립니다."))
                        )
                    )
                ),
                "duration_weeks": item.get("duration_weeks") or 0,
                "tasks": tasks,
                "roles": list(item.get("roles") or []),
                "deliverables": list(item.get("deliverables") or []),
                "related_rules": list(item.get("related_rules") or []),
                "related_contracts": list(item.get("related_contracts") or []),
            }
        )
    return {
        "empty_message": _display_empty_message("execution_plan", run_state=run_state, missing_context_details=[]),
        "items": rendered_items,
    }


def _build_display_risks(
    *,
    risks: list[str],
    missing_context_details: list[dict[str, Any]],
    run_state: str,
) -> dict[str, Any]:
    return {
        "empty_message": _display_empty_message("risks", run_state=run_state, missing_context_details=missing_context_details),
        "missing_context_empty_message": _display_empty_message(
            "missing_context",
            run_state=run_state,
            missing_context_details=missing_context_details,
        ),
        "items": [_decisionize_display_text(item) for item in _trim_items(risks, limit=6)],
        "missing_context_details": [
            {
                "required_material": item.get("required_material") or "-",
                "reason": _decisionize_display_text(item.get("reason") or ""),
                "priority": "승인 전 확보",
            }
            for item in missing_context_details
        ],
    }


def _preferred_display_option(design_options: list[dict[str, Any]]) -> dict[str, Any]:
    for item in design_options:
        if isinstance(item, dict) and bool(item.get("recommended")):
            return item
    for item in design_options:
        if isinstance(item, dict):
            return item
    return {}


def _build_display_package(
    *,
    run_state: str,
    core_conclusion: str,
    executive_summary: dict[str, Any],
    grounded_business_rules: list[dict[str, Any]],
    design_options: list[dict[str, Any]],
    execution_plan: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing_context_details = list(diagnosis.get("missing_context_details") or [])
    key_risks = _trim_items(list(diagnosis.get("risks") or []), limit=6)
    executive_actions = _trim_items(list(executive_summary.get("next_steps") or []), limit=3)
    executive_rationales = _trim_items(list(executive_summary.get("summary_lines") or []), limit=3)
    summary_text = str(executive_summary.get("core_message") or core_conclusion or "").strip()
    impact_text = _first_display_line(key_risks) or _first_display_line(executive_rationales) or summary_text
    analysis_first_surface = _uses_analysis_first_surface_extensions(extensions)
    surface_wording = _surface_wording_from_extensions(extensions)
    document_tone = str(surface_wording.get("document_tone") or "").strip()
    operational_execution_actions = _trim_items(
        [str(item.get("goal") or "").strip() for item in execution_plan if isinstance(item, dict) and str(item.get("goal") or "").strip()],
        limit=3,
    )
    priority_action = _first_display_line(operational_execution_actions if analysis_first_surface else executive_actions)
    comparison_first_surface = _uses_comparison_first_surface_extensions(extensions)
    if comparison_first_surface:
        preferred_option = _preferred_display_option(design_options)
        option_name = str(preferred_option.get("name") or "").strip()
        option_reason = str(preferred_option.get("selection_reason") or preferred_option.get("structure_summary") or "").strip()
        option_action = next(
            (str(item.get("goal") or "").strip() for item in execution_plan if isinstance(item, dict) and str(item.get("goal") or "").strip()),
            "",
        )
        if option_name:
            summary_text = f"우선 검토안은 {option_name}입니다."
        if option_reason:
            impact_text = option_reason
        if option_action:
            priority_action = option_action
    if analysis_first_surface:
        hero_headline = _ensure_display_sentence(core_conclusion or summary_text)
    else:
        hero_headline = _compose_one_line_conclusion(
            summary=summary_text,
            impact=impact_text,
            priority_action=priority_action,
        )
    section_states = {
        "retained_contracts": _display_empty_message("retained_contracts", run_state=run_state, missing_context_details=missing_context_details),
        "priority_split": _display_empty_message("priority_split", run_state=run_state, missing_context_details=missing_context_details),
        "verification": _display_empty_message("verification", run_state=run_state, missing_context_details=missing_context_details),
        "rebuild_strategy": _display_empty_message("rebuild_strategy", run_state=run_state, missing_context_details=missing_context_details),
        "transition_draft": _display_empty_message("transition_draft", run_state=run_state, missing_context_details=missing_context_details),
        "report_scope": _display_empty_message("report_scope", run_state=run_state, missing_context_details=missing_context_details),
        "report_questions": _display_empty_message("report_questions", run_state=run_state, missing_context_details=missing_context_details),
    }
    return {
        "hero": {
            "label": _surface_section_title_from_extensions(extensions, "one_line_conclusion", "한 줄 결론"),
            "headline": hero_headline,
            "impact": _ensure_display_sentence(impact_text) if analysis_first_surface else _decisionize_display_text(impact_text),
            "priority_action": priority_action,
        },
        "sections": {
            "executive": {
                "headline": hero_headline,
                "reason_label": (
                    "전표/GL 진단 요약"
                    if document_tone == "diagnosis_first"
                    else "선택지 요약"
                    if document_tone == "decision_first"
                    else
                    "현행 분석 요약"
                    if analysis_first_surface
                    else "비교 근거"
                    if comparison_first_surface
                    else "판단 근거"
                ),
                "action_label": (
                    "진단 순서"
                    if document_tone == "diagnosis_first"
                    else "적용 검증 기준"
                    if document_tone == "decision_first"
                    else
                    "검토 순서"
                    if analysis_first_surface
                    else "도입 단계"
                    if comparison_first_surface
                    else "실행 조치"
                ),
                "impact_lines": [(_ensure_display_sentence(item) if analysis_first_surface else _decisionize_display_text(item)) for item in executive_rationales],
                "action_lines": [
                    (_ensure_display_sentence(item) if analysis_first_surface else _decisionize_display_text(item))
                    for item in (operational_execution_actions if analysis_first_surface else executive_actions)
                ],
            },
            "grounded_rules": _build_display_grounded_rules(
                grounded_business_rules,
                run_state=run_state,
                missing_context_details=missing_context_details,
            ),
            "design_options": _build_display_design_options(
                design_options,
                run_state=run_state,
                missing_context_details=missing_context_details,
            ),
            "execution_plan": _build_display_execution_plan(
                execution_plan,
                run_state=run_state,
                analysis_first_surface=analysis_first_surface,
            ),
            "risks": _build_display_risks(
                risks=key_risks,
                missing_context_details=missing_context_details,
                run_state=run_state,
            ),
        },
        "section_states": section_states,
    }


def _sanitize_user_value(value: Any, *, key_path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, str):
        if key_path and key_path[-1] in {"observed", "expected_pattern", "current_structure", "recommended_structure", "markdown"}:
            sanitized = value.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
            sanitized = sanitized.replace("REDACTED_PATH", "[PATH]")
            sanitized = re.sub(r"\[SAFE (?:STRUCTURE|SOURCE):[^\]]+\]", "", sanitized, flags=re.IGNORECASE)
            sanitized = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", sanitized)
            sanitized = re.sub(r"\b(?:sk_(?:live|test)_[A-Za-z0-9]+|ghp_[A-Za-z0-9]+|xox[baprs]-[A-Za-z0-9-]+)\b", "[SECRET]", sanitized)
            sanitized = re.sub(r"\b(?:\+?82[- ]?)?0\d{1,2}[- ]?\d{3,4}[- ]?\d{4}\b", "[PHONE]", sanitized)
            sanitized = re.sub(r"(https?://[^\s\"']+|[A-Za-z]:\\[^\s\"']+|/(?:[A-Za-z0-9_.-]+/?)+)", "[PATH]", sanitized)
            sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
            return sanitized.strip()
        sanitized = value.strip()
        replacements = {
            "REDACTED_PATH": "",
            "status_permissions": "권한 및 상태 규칙",
            "search_filters": "조회 조건 규칙",
            "save_validation": "저장 검증 규칙",
            "role/...": "역할 기준",
            "command/...": "실행 규칙",
            "controller/...": "API 경계",
            "controller/service/repository": "API, 서비스, 데이터 접근 경계",
            "query parameters": "조회 파라미터 규칙",
            "SQL parameterization": "SQL 조건 매핑",
            "policy service": "정책 서비스",
            "validator": "검증 계층",
            "DTO": "입력 모델",
            "repository": "데이터 접근 계층",
        }
        for raw, replacement in replacements.items():
            sanitized = sanitized.replace(raw, replacement)
        sanitized = sanitized.replace("SAFE STRUCTURE", "")
        sanitized = sanitized.replace("[SAFE STRUCTURE:", "")
        sanitized = sanitized.replace(".../", "")
        sanitized = sanitized.replace("/...", "")
        sanitized = sanitized.replace("[]", "")
        return " ".join(sanitized.split())
    if isinstance(value, list):
        return [_sanitize_user_value(item, key_path=key_path) for item in value]
    if isinstance(value, dict):
        return {
            key: _sanitize_user_value(item, key_path=(*key_path, str(key)))
            for key, item in value.items()
        }
    return value


def _resolved_primary_judgment(result: StructuredRebuildResult | None) -> str:
    return str(result.primary_judgment if result else "").strip()


def _resolved_template_judgment(result: StructuredRebuildResult | None, primary_judgment: str) -> str:
    explicit = str(result.template_judgment if result else "").strip()
    return explicit or primary_judgment


def _resolved_structural_judgment(
    result: StructuredRebuildResult | None,
    decision_summary_payload: dict[str, Any],
) -> str:
    explicit = str(result.structural_judgment if result else "").strip()
    if explicit:
        return explicit

    decisions = decision_summary_payload.get("decisions") or []
    top_decision = decisions[0] if isinstance(decisions, list) and decisions else {}
    top_decision_type = str(top_decision.get("decision_type") or "").strip()
    recommended_strategy = str(decision_summary_payload.get("recommended_strategy") or "").strip()

    if not decisions:
        return "observation_only"
    if recommended_strategy == "마이그레이션 고려" or top_decision_type == "migration_consideration":
        return "migration_consideration"
    if recommended_strategy == "재설계 우선" or top_decision_type == "redesign":
        return "redesign"
    return "refactor"


def _resolved_narrative_axis(
    result: StructuredRebuildResult | None,
    *,
    primary_judgment: str,
    template_judgment: str,
) -> str:
    explicit = str(result.narrative_axis if result else "").strip()
    if explicit:
        return explicit
    return template_judgment or primary_judgment


_CUSTOMER_INTENT_PREFIXES = (
    "고객 요청:",
    "선호 방향:",
    "원하는 방식:",
)


def _build_customer_intent(project: ModernizationProject) -> dict[str, Any]:
    seen: set[str] = set()
    items: list[str] = []
    for raw_item in _project_json_list(project, "constraints_json"):
        text = str(raw_item or "").strip()
        if not text:
            continue
        normalized = text
        for prefix in _CUSTOMER_INTENT_PREFIXES:
            if text.lower().startswith(prefix.lower()):
                normalized = text[len(prefix):].strip(" -")
                break
        else:
            continue
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return {
        "available": bool(items),
        "items": items,
    }


def _build_consulting_source(
    *,
    family: str,
    question_axis: str = "",
    report_purpose: str = "",
    report_scope: list[str],
    report_questions: list[str],
    customer_intent: dict[str, Any] | None = None,
    assumptions: list[dict[str, Any]],
    analysis_summary: list[str],
    core_conclusion: str,
    primary_judgment_reason: str,
    grounded_business_rules: list[dict[str, Any]],
    retained_contracts: list[dict[str, Any]],
    decision_items: list[dict[str, Any]],
    priority_split_items: list[dict[str, Any]],
    design_options: list[dict[str, Any]],
    recommended_option: dict[str, Any] | None = None,
    execution_plan: list[dict[str, Any]],
    recommended_directions: list[str],
    risks: list[str],
    missing_context_details: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "family": str(family or "").strip(),
        "question_axis": str(question_axis or "").strip(),
        "report_purpose": str(report_purpose or "").strip(),
        "report_scope": list(report_scope or []),
        "report_questions": list(report_questions or []),
        "customer_intent": dict(customer_intent or {}) if isinstance(customer_intent, dict) else {},
        "assumptions": [dict(item) for item in assumptions or [] if isinstance(item, dict)],
        "analysis_summary": list(analysis_summary or []),
        "core_conclusion": str(core_conclusion or "").strip(),
        "primary_judgment_reason": str(primary_judgment_reason or "").strip(),
        "grounded_business_rules": [dict(item) for item in grounded_business_rules or [] if isinstance(item, dict)],
        "retained_contracts": [dict(item) for item in retained_contracts or [] if isinstance(item, dict)],
        "decision_items": [dict(item) for item in decision_items or [] if isinstance(item, dict)],
        "priority_split_items": [dict(item) for item in priority_split_items or [] if isinstance(item, dict)],
        "design_options": [dict(item) for item in design_options or [] if isinstance(item, dict)],
        "recommended_option": dict(recommended_option or {}) if isinstance(recommended_option, dict) else {},
        "execution_plan": [dict(item) for item in execution_plan or [] if isinstance(item, dict)],
        "recommended_directions": list(recommended_directions or []),
        "risks": list(risks or []),
        "missing_context_details": [dict(item) for item in missing_context_details or [] if isinstance(item, dict)],
    }


def build_result_package(
    project: ModernizationProject,
    snapshot: dict[str, Any] | None,
    result: StructuredRebuildResult | None,
    *,
    assets: list[dict[str, Any]],
    polish_bundle: dict[str, Any] | None = None,
    app_version: str | None = None,
) -> dict[str, Any]:
    result = _refresh_result_review_diff(result)
    narrative_service = NarrativeAugmentationService()
    run_state = _project_status_from_run(snapshot)
    project_id = _project_text(project, "id")
    project_name = _project_text(project, "project_name")
    client_name = _project_text(project, "client_name")
    project_goal = _project_text(project, "goal_text")
    template_key = _project_text(project, "template_key")
    project_status = _project_text(project, "status")
    created_at_iso = _project_isoformat(project, "created_at")
    core_conclusion = (result.one_line_conclusion if result else "").strip()
    recommended_directions = _trim_items(list(result.recommended_directions) if result else [], limit=3)
    layer_dump = result.layer_reconstruction.model_dump() if result else {}
    recomposition_dump = result.recomposition_draft.model_dump() if result else {}
    diagnosis_state = "ready" if result and (result.analysis_summary or result.core_business_rules or result.risks or result.missing_context_details or result.grounded_business_rules) else ("결과 생성 중" if run_state == "running" else "데이터 없음")
    design_state = "ready" if result and (result.rebuild_strategy or _has_layer_content(layer_dump) or result.design_options) else ("결과 생성 중" if run_state == "running" else "데이터 없음")
    draft_state = "ready" if result and _has_layer_content(recomposition_dump) else ("결과 생성 중" if run_state == "running" else "데이터 없음")
    diagnosis = {
        "core_business_rules": list(result.core_business_rules) if result else [],
        "analysis_summary": list(result.analysis_summary) if result else [],
        "risks": list(result.risks) if result else [],
        "missing_context_details": _missing_context_blocks(result),
        "state": diagnosis_state,
    }
    design = {
        "rebuild_strategy": list(result.rebuild_strategy) if result else [],
        "layer_reconstruction": layer_dump,
        "design_options": [item.model_dump() for item in (result.design_options if result else [])],
        "recommended_option": result.recommended_option.model_dump() if result and result.recommended_option else None,
        "state": design_state,
    }
    transition_draft = {
        "recomposition_draft": recomposition_dump,
        "state": draft_state,
    }
    appendix = {
        "asset_manifest": assets,
        "project_name": project_name,
        "client_name": client_name,
        "goal": project_goal,
        "template_key": template_key,
        "created_at": created_at_iso,
        "run_status": (snapshot or {}).get("status") or project_status,
    }
    provenance = _build_result_provenance(project, snapshot, assets=assets, app_version=app_version)
    scope_notice = deepcopy(PROJECT_SCOPE_NOTICE)
    executive_summary_v2 = _trim_items(list(result.executive_summary_v2) if result else [], limit=6)
    grounded_business_rules = [_build_grounded_rule_view(item.model_dump()) for item in (result.grounded_business_rules if result else [])]
    decision_items = _dedupe_dict_items(
        [{"statement": item.statement, "rationale": item.rationale} for item in (result.decision_items if result else [])],
        "statement",
    )
    retained_contracts = _dedupe_dict_items(
        [{"item": item.item, "basis": item.basis} for item in (result.retained_contracts if result else [])],
        "item",
    )
    priority_split_items = [item.model_dump() for item in (result.priority_split_items if result else [])]
    verification_checkpoints = [{"item": item.item, "reason": item.reason} for item in (result.verification_checkpoints if result else [])]
    design_options = [item.model_dump() for item in (result.design_options if result else [])]
    recommended_option = result.recommended_option.model_dump() if result and result.recommended_option else None
    execution_plan = [item.model_dump() for item in (result.execution_plan if result else [])]
    assumptions = [item.model_dump() for item in (result.assumptions if result else [])]
    accounting = None
    if result and isinstance(result.extensions, dict):
        accounting_block = result.extensions.get("accounting")
        if isinstance(accounting_block, dict):
            accounting = _build_accounting_package_view(accounting_block)
    customer_intent = _build_customer_intent(project)
    structure_comparison = _build_structure_comparison_preview(result)
    surface_extensions = _surface_extensions(result)
    result_question_axis = (
        str(getattr(result, "question_axis", "") or "").strip()
        if result
        else ""
    )
    consulting_source = _build_consulting_source(
        family=(result.family_classification.family if result and result.family_classification else ""),
        question_axis=result_question_axis,
        report_purpose=(result.report_purpose if result else ""),
        report_scope=list(result.report_scope) if result else [],
        report_questions=list(result.report_questions) if result else [],
        customer_intent=customer_intent,
        assumptions=assumptions,
        analysis_summary=diagnosis["analysis_summary"],
        core_conclusion=core_conclusion,
        primary_judgment_reason=(result.primary_judgment_reason if result else ""),
        grounded_business_rules=grounded_business_rules,
        retained_contracts=retained_contracts,
        decision_items=decision_items,
        priority_split_items=priority_split_items,
        design_options=design_options,
        recommended_option=recommended_option,
        execution_plan=execution_plan,
        recommended_directions=recommended_directions,
        risks=diagnosis["risks"],
        missing_context_details=diagnosis["missing_context_details"],
    )
    consulting_min_contract = build_consulting_min_contract(consulting_source)
    consulting_deck = build_consulting_deck(
        consulting_min_contract,
        project_name=project_name,
        client_name=client_name,
        surface_mode="internal",
        family=(result.family_classification.family if result and result.family_classification else ""),
        question_axis=result_question_axis,
    )
    slide_schema = build_slide_schema(ConsultingDeck.model_validate(consulting_deck))
    canonical_payload = (
        result.canonical_payload.model_dump()
        if result and result.canonical_payload is not None
        else (
            narrative_service.freeze_canonical_payload_from_result(result).model_dump()
            if result
            else None
        )
    )
    validated_narrative_layer = (
        result.narrative_layer.model_dump()
        if result and result.narrative_layer is not None
        else None
    )
    validated_explanation_blocks = (
        [item.model_dump() for item in (result.validated_explanation_blocks or [])]
        if result
        else []
    )
    fallback_narrative_metadata = (
        result.narrative_metadata.model_dump()
        if result and result.narrative_metadata is not None
        else (
            {
                "source": "deterministic_fallback",
                "match_mode": "failed",
                "fields_rewritten": [],
                "model": "",
                "prompt_version": ResultPackager.NARRATIVE_PROMPT_VERSION,
                "validation_passed": False,
                "failure_reason": "llm_not_invoked" if result else "result_unavailable",
                "axis": (result.narrative_axis if result else ""),
                "llm_invoked": False,
                "llm_call_count": 0,
                "fallback_used": True,
                "slim_payload_hash": "",
                "block_match_modes": {},
            }
        )
    )
    narrative_guard_metadata = (
        result.narrative_guard_metadata.model_dump()
        if result and result.narrative_guard_metadata is not None
        else deepcopy(fallback_narrative_metadata)
    )
    family_payload = (
        result.family_classification.model_dump()
        if result and result.family_classification is not None
        else _empty_family_classification_payload()
    )
    authoritative_payload = {
        "family_classification": family_payload,
        "structure_snapshot": deepcopy(result.structure_snapshot) if result else {},
        "diagnosis_report": deepcopy(result.diagnosis_report) if result else {},
        "decision_summary": deepcopy(result.decision_summary) if result else {},
        "improvement_plan_bundle": deepcopy(result.improvement_plan_bundle) if result else {},
        "judgment_canvas": deepcopy(result.judgment_canvas) if result else {},
        "stage_control": deepcopy(result.stage_control) if result else {},
        "validation_result": deepcopy(result.validation_result) if result else {},
        "appendix": deepcopy(result.appendix) if result else {},
    }
    primary_judgment = _resolved_primary_judgment(result)
    template_judgment = _resolved_template_judgment(result, primary_judgment)
    structural_judgment = _resolved_structural_judgment(result, authoritative_payload["decision_summary"])
    narrative_axis = _resolved_narrative_axis(
        result,
        primary_judgment=primary_judgment,
        template_judgment=template_judgment,
    )
    executive_summary = _build_executive_summary(
        run_state=run_state,
        core_conclusion=core_conclusion,
        recommended_directions=recommended_directions,
        executive_summary_v2=executive_summary_v2,
        grounded_business_rules=grounded_business_rules,
        decision_items=decision_items,
        analysis_summary=diagnosis["analysis_summary"],
        diagnosis=diagnosis,
        execution_plan=execution_plan,
        recommended_option=recommended_option,
        accounting=accounting,
    )
    display = _build_display_package(
        run_state=run_state,
        core_conclusion=core_conclusion,
        executive_summary=executive_summary,
        grounded_business_rules=grounded_business_rules,
        design_options=design_options,
        execution_plan=execution_plan,
        diagnosis=diagnosis,
        extensions=surface_extensions,
    )
    return _sanitize_user_value({
        "project": {
            "id": project_id,
            "project_name": project_name,
            "client_name": client_name,
            "goal": project_goal,
            "template_key": template_key,
            "status": project_status,
        },
        "assets": assets,
        "provenance": provenance,
        "executive_summary": executive_summary,
        "primary_judgment": primary_judgment,
        "template_judgment": template_judgment,
        "structural_judgment": structural_judgment,
        "narrative_axis": narrative_axis,
        "question_axis": (
            result_question_axis
            if result
            else str((((canonical_payload or {}).get("request_context") or {}).get("question_axis") or "")).strip()
        ),
        "family_classification": family_payload,
        "feature_signal_mode": (result.feature_signal_mode if result else "").strip(),
        "confidence": float(result.confidence) if result else 0.0,
        "report_purpose": (result.report_purpose if result else "").strip(),
        "primary_judgment_reason": (result.primary_judgment_reason if result else "").strip(),
        "report_scope": list(result.report_scope) if result else [],
        "report_questions": list(result.report_questions) if result else [],
        "assumptions": assumptions,
        "executive_summary_v2": executive_summary_v2,
        "scope_notice": scope_notice,
        "core_conclusion": core_conclusion,
        "analysis_summary": diagnosis["analysis_summary"],
        "core_business_rules": list(result.core_business_rules) if result else [],
        "grounded_business_rules": grounded_business_rules,
        "decision_items": decision_items,
        "retained_contracts": retained_contracts,
        "priority_split_items": priority_split_items,
        "verification_checkpoints": verification_checkpoints,
        "design_options": design_options,
        "recommended_option": recommended_option,
        "execution_plan": execution_plan,
        "judgment_canvas": deepcopy(result.judgment_canvas) if result else {},
        "stage_control": deepcopy(result.stage_control) if result else {},
        "validation_result": deepcopy(result.validation_result) if result else {},
        "recommended_directions": recommended_directions,
        "accounting": accounting,
        "customer_intent": customer_intent,
        "canonical_payload": deepcopy(canonical_payload) if isinstance(canonical_payload, dict) else canonical_payload,
        "validated_narrative_layer": deepcopy(validated_narrative_layer) if isinstance(validated_narrative_layer, dict) else validated_narrative_layer,
        "validated_explanation_blocks": deepcopy(validated_explanation_blocks),
        "fallback_narrative_metadata": deepcopy(fallback_narrative_metadata) if isinstance(fallback_narrative_metadata, dict) else fallback_narrative_metadata,
        "narrative_guard_metadata": deepcopy(narrative_guard_metadata) if isinstance(narrative_guard_metadata, dict) else narrative_guard_metadata,
        "guard_match_mode": (
            str(narrative_guard_metadata.get("match_mode") or "failed")
            if isinstance(narrative_guard_metadata, dict)
            else "failed"
        ),
        "guard_block_match_modes": (
            deepcopy(narrative_guard_metadata.get("block_match_modes") or {})
            if isinstance(narrative_guard_metadata, dict)
            else {}
        ),
        "consulting_min_contract": consulting_min_contract.model_dump(),
        "consulting_deck": consulting_deck,
        "slide_schema": slide_schema.model_dump(),
        "structure_comparison": structure_comparison,
        "extensions": surface_extensions,
        "authoritative_payload": authoritative_payload,
        "display": display,
        "polish_bundle": deepcopy(polish_bundle) if isinstance(polish_bundle, dict) else None,
        "diagnosis": diagnosis,
        "design": design,
        "transition_draft": transition_draft,
        "appendix": appendix,
    }) 


def _surface_extensions(result: StructuredRebuildResult | None) -> dict[str, Any]:
    if not result or not isinstance(result.extensions, dict):
        return {}
    output: dict[str, Any] = {}
    for key in ("narrative", "decision_governance", "review_diff"):
        value = result.extensions.get(key)
        if isinstance(value, dict):
            output[key] = deepcopy(value)
    return output


def _surface_wording_from_extensions(extensions: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(extensions, dict):
        return {}
    governance = extensions.get("decision_governance")
    governance = governance if isinstance(governance, dict) else {}
    wording = governance.get("surface_wording")
    return wording if isinstance(wording, dict) else {}


def _surface_mode_from_extensions(extensions: dict[str, Any] | None) -> str:
    wording = _surface_wording_from_extensions(extensions)
    return str(wording.get("mode") or "").strip()


def _uses_analysis_first_surface_extensions(extensions: dict[str, Any] | None) -> bool:
    return _surface_mode_from_extensions(extensions) == "analysis_first_operational_source"


def _uses_comparison_first_surface_extensions(extensions: dict[str, Any] | None) -> bool:
    return _surface_mode_from_extensions(extensions) == "comparison_first_option"


def _surface_section_title_from_extensions(extensions: dict[str, Any] | None, section_key: str, fallback: str) -> str:
    wording = _surface_wording_from_extensions(extensions)
    titles = wording.get("section_titles") if isinstance(wording, dict) else {}
    if isinstance(titles, dict):
        title = str(titles.get(section_key) or "").strip()
        if title:
            return title
    return fallback


def _surface_section_title_from_pkg(pkg: dict[str, Any], section_key: str, fallback: str) -> str:
    if _effective_package_information_role(pkg) == "diagnosis":
        title = _DIAGNOSIS_MARKDOWN_SECTION_TITLES.get(section_key)
        if title:
            return title
    extensions = pkg.get("extensions") if isinstance(pkg, dict) else {}
    return _surface_section_title_from_extensions(extensions if isinstance(extensions, dict) else None, section_key, fallback)


def _refresh_result_review_diff(result: StructuredRebuildResult | None) -> StructuredRebuildResult | None:
    if not result or not isinstance(result.extensions, dict):
        return result
    review_diff = result.extensions.get("review_diff")
    if not isinstance(review_diff, dict):
        return result
    refreshed_review_diff = _refresh_review_diff_payload(review_diff)
    if refreshed_review_diff == review_diff:
        return result
    refreshed_extensions = dict(result.extensions)
    refreshed_extensions["review_diff"] = refreshed_review_diff
    return result.model_copy(update={"extensions": refreshed_extensions})


def _refresh_review_diff_payload(review_diff: dict[str, Any]) -> dict[str, Any]:
    refreshed = deepcopy(review_diff)
    code_diff = refreshed.get("code_diff")
    if not isinstance(code_diff, dict):
        return refreshed
    snippets = code_diff.get("snippets")
    if not isinstance(snippets, list) or not snippets:
        return refreshed

    packager = ResultPackager()
    changed = False
    refreshed_snippets: list[dict[str, Any]] = []
    for raw_snippet in snippets:
        if not isinstance(raw_snippet, dict):
            refreshed_snippets.append(raw_snippet)
            continue
        snippet = deepcopy(raw_snippet)
        detector_id = str(snippet.get("detector_id") or "").strip()
        observed = str(snippet.get("observed") or "").strip()
        inferred_asset_type = _infer_review_diff_asset_type(
            str(snippet.get("file") or "").strip(),
            observed,
        )
        if detector_id and observed:
            refreshed_expected_pattern = packager._build_grounded_expected_pattern(
                detector_id=detector_id,
                asset_type=inferred_asset_type,
                observed=observed,
            ).strip()
            if refreshed_expected_pattern and refreshed_expected_pattern != str(snippet.get("expected_pattern") or "").strip():
                snippet["expected_pattern"] = refreshed_expected_pattern
                changed = True
        refreshed_snippets.append(snippet)

    if not changed:
        return refreshed

    code_diff["snippets"] = refreshed_snippets
    code_diff["available"] = bool(refreshed_snippets)
    refreshed["code_diff"] = code_diff
    refreshed["markdown"] = packager._render_review_diff_markdown(
        structural_diff=refreshed.get("structural_diff") if isinstance(refreshed.get("structural_diff"), dict) else {},
        evidence_diff=refreshed.get("evidence_diff") if isinstance(refreshed.get("evidence_diff"), dict) else {},
        decision_diff=refreshed.get("decision_diff") if isinstance(refreshed.get("decision_diff"), dict) else {},
        code_diff=code_diff,
    )
    return refreshed


def _infer_review_diff_asset_type(file_name: str, observed: str) -> str:
    normalized_name = str(file_name or "").strip().lower()
    if normalized_name.endswith(".sql"):
        return "sql"
    observed_head = "\n".join(str(observed or "").splitlines()[:3]).lower()
    if re.search(r"^\s*(select|with|from|where|join)\b", observed_head, flags=re.IGNORECASE | re.MULTILINE):
        return "sql"
    return "source"


def _build_structure_comparison_preview(result: StructuredRebuildResult | None) -> dict[str, Any]:
    review_diff = (
        result.extensions.get("review_diff")
        if result and isinstance(result.extensions, dict)
        else None
    )
    if not isinstance(review_diff, dict):
        return {"available": False, "items": []}
    code_diff = review_diff.get("code_diff")
    if not isinstance(code_diff, dict):
        return {"available": False, "items": []}
    snippets = code_diff.get("snippets")
    if not isinstance(snippets, list):
        return {"available": False, "items": []}
    items: list[dict[str, Any]] = []
    for snippet in snippets[:3]:
        if not isinstance(snippet, dict):
            continue
        observed = str(snippet.get("observed") or "").strip()
        expected_pattern = str(snippet.get("expected_pattern") or "").strip()
        if not observed or not expected_pattern:
            continue
        difference_summary = _trim_items(snippet.get("difference_summary") or [], limit=3)
        items.append(
            {
                "file": str(snippet.get("file") or "-"),
                "issue_summary": str(snippet.get("issue_summary") or "").strip(),
                "current_structure": observed,
                "recommended_structure": expected_pattern,
                "difference_summary": difference_summary,
            }
        )
    return {
        "available": bool(items),
        "items": items,
        "display_policy": "anonymized_only",
    }


def _demote_markdown_headings(markdown: str, *, levels: int = 1) -> str:
    if levels <= 0:
        return markdown
    normalized = re.sub(r"\s+(#{2,6}\s)", r"\n\1", markdown.strip())

    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}{'#' * levels} "

    return re.sub(r"(^|\n)(#{1,6})\s+", _replace, normalized)


def _resolve_project_result_run(
    project: ModernizationProject,
    *,
    requested_run_id: str | None,
    db: Session,
) -> tuple[str, ProjectRunHistory | None]:
    normalized_run_id = str(requested_run_id or "").strip()
    if not normalized_run_id or normalized_run_id == str(project.run_id or ""):
        return str(project.run_id), None
    history_row = (
        db.query(ProjectRunHistory)
        .filter(
            ProjectRunHistory.project_id == project.id,
            ProjectRunHistory.run_id == normalized_run_id,
        )
        .order_by(ProjectRunHistory.created_at.desc(), ProjectRunHistory.id.desc())
        .first()
    )
    if history_row is None:
        raise HTTPException(status_code=404, detail="Project run not found")
    return normalized_run_id, history_row


def _load_project_result_context(
    project: ModernizationProject,
    *,
    db: Session,
    app_version: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    target_run_id, history_row = _resolve_project_result_run(project, requested_run_id=run_id, db=db)
    snapshot = get_run_snapshot(target_run_id, db=db)
    if target_run_id == str(project.run_id or ""):
        _sync_project_status(project, snapshot, db)
    events = get_run_events(target_run_id, db=db)
    structured = _extract_structured_result(events)
    polish_bundle = _extract_polish_bundle(events, structured)
    target_manifest = _parse_json_list(history_row.asset_manifest_json) if history_row else _parse_json_list(project.asset_manifest_json)
    assets = _build_assets_payload(project, db, asset_manifest=target_manifest)
    result_package = build_result_package(
        project,
        snapshot,
        structured,
        assets=assets,
        polish_bundle=polish_bundle,
        app_version=app_version,
    )
    return {
        "snapshot": snapshot,
        "events": events,
        "structured": structured,
        "polish_bundle": polish_bundle,
        "assets": assets,
        "result_package": result_package,
        "run_id": target_run_id,
        "history_row": history_row,
    }


def _build_grounded_rule_view(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": rule.get("title") or "",
        "description": rule.get("description") or "",
        "design_targets": list(rule.get("design_targets") or []),
        "confidence": rule.get("confidence") or "가정",
        "confidence_reason": rule.get("confidence_reason") or "",
        "needs_verification": bool(rule.get("needs_verification")),
        "evidence_cards": _build_user_evidence_cards(rule),
    }


def _build_user_evidence_cards(rule: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    title = str(rule.get("title") or "").strip() or "핵심 규칙"
    design_targets = list(rule.get("design_targets") or [])
    confidence = str(rule.get("confidence") or "가정")
    for evidence in rule.get("evidence") or []:
        asset_name = str(evidence.get("asset_name") or "-").strip() or "-"
        evidence_kind = str(evidence.get("evidence_kind") or evidence.get("asset_type") or "").strip().lower()
        key = (asset_name, evidence_kind)
        if key in seen:
            continue
        seen.add(key)
        cards.append(
            {
                "asset_name": asset_name,
                "condition_summary": _condition_summary_for_evidence(title, evidence),
                "design_targets": design_targets,
                "confidence": confidence,
            }
        )
    return cards


def _condition_summary_for_evidence(rule_title: str, evidence: dict[str, Any]) -> str:
    evidence_kind = str(evidence.get("evidence_kind") or evidence.get("asset_type") or "").strip().lower()
    excerpt = str(evidence.get("excerpt") or "").strip()
    translated = _translate_condition_excerpt(rule_title, excerpt)
    if translated:
        return translated
    mapping = {
        "source": f"코드 분기와 검증 로직에서 '{rule_title}' 조건이 직접 확인되었습니다.",
        "ui": f"화면 분기와 액션 노출 조건에서 '{rule_title}' 신호가 확인되었습니다.",
        "sql": f"SQL 조건과 상태 필터에서 '{rule_title}' 기준이 확인되었습니다.",
        "schema": f"스키마 컬럼과 상태 계약에서 '{rule_title}' 관련 구조가 확인되었습니다.",
        "constraint": f"제약조건 문서에서 '{rule_title}' 유지 조건이 확인되었습니다.",
        "goal": f"목표 정의에서 '{rule_title}' 범위가 확인되었습니다.",
    }
    return _decisionize_display_text(
        mapping.get(evidence_kind, f"제공 자산에서 '{rule_title}' 관련 근거가 확인되었습니다.")
    )


def _translate_condition_excerpt(rule_title: str, excerpt: str) -> str:
    text = (excerpt or "").strip()
    lowered = text.lower()
    if not text:
        return ""
    impact = _decisionize_display_text

    if "지점장 300만원 한도" in rule_title and ("3000000" in lowered or "branch_manager" in lowered or "지점장" in lowered):
        return impact("청구 금액이 300만원 이상이면 지점장 권한으로는 처리할 수 없도록 제한하는 조건이 확인되었습니다.")
    if "대리점 고액 주문 본사 전용" in rule_title and any(token in lowered for token in ("agency", "hq", "5000000", "대리점", "본사")):
        return impact("대리점 채널의 고액 주문은 본사 승인 조건을 충족해야 처리되도록 제한하는 조건이 확인되었습니다.")
    if "수출 주문 고액건 REVIEW_REQUIRED" in rule_title and any(token in lowered for token in ("export", "7000000", "수출")):
        return impact("수출 주문은 고액 조건에 해당하면 REVIEW_REQUIRED 상태로 전이되도록 설정한 조건이 확인되었습니다.")
    if "fraud" in lowered and "hq_reviewer" in lowered:
        return impact("사고 유형이 FRAUD이면 HQ_REVIEWER 권한에서만 처리되도록 제한하는 조건이 확인되었습니다.")
    if "dept_code" in lowered and "claim_audit" in lowered and "!=" in lowered:
        return impact("CLAIM_AUDIT 부서가 아니면 고액 청구를 처리할 수 없도록 제한하는 조건이 확인되었습니다.")
    if ("3000000" in lowered or "300만원" in lowered) and ("branch_manager" in lowered or "지점장" in lowered):
        return impact("청구 금액이 300만원 이상이면 지점장 권한으로는 처리할 수 없도록 제한하는 조건이 확인되었습니다.")
    if ("10000000" in lowered or "1천만원" in lowered) and "claim_audit" in lowered:
        return impact("청구 금액이 1천만원 이상이면 CLAIM_AUDIT 부서만 처리하도록 제한하는 조건이 확인되었습니다.")
    if "b99" in lowered and ("urgent" in lowered or "긴급" in lowered):
        return impact("B99 지점의 긴급 건은 본사 선승인 조건이 충족되어야 처리되도록 제한하는 조건이 확인되었습니다.")
    if ("closed" in lowered or "cancelled" in lowered) and ("조정" in lowered or "adjust" in lowered):
        return impact("상태가 CLOSED 또는 CANCELLED이면 조정을 차단하는 조건이 확인되었습니다.")
    if "vip" in lowered and any(token in lowered for token in ("22", "23", "00", "night", "야간")):
        return impact("VIP 고객은 야간 시간대에 주문 마감을 할 수 없도록 제한하는 조건이 확인되었습니다.")
    if ("deliveryholdflag" in lowered or "delivery_hold" in lowered or "배송보류" in lowered) and any(token in lowered for token in ('"y"', "=y", "해제", "release")):
        return impact("delivery_hold_flag 가 Y인 경우 주문 마감을 차단하는 선행 검증 조건이 확인되었습니다.")
    if ("agency" in lowered or "대리점" in lowered) and ("hq" in lowered or "본사" in lowered):
        return impact("대리점 채널의 고액 주문은 본사 승인 조건을 충족해야 처리되도록 제한하는 조건이 확인되었습니다.")
    if ("export" in lowered or "수출" in lowered) and "review_required" in lowered:
        return impact("수출 주문은 고액 조건에 해당하면 REVIEW_REQUIRED 상태로 전이되도록 설정한 조건이 확인되었습니다.")
    status_in_match = re.search(r"status\s+in\s*\(([^)]+)\)", text, flags=re.IGNORECASE)
    if status_in_match:
        raw_values = status_in_match.group(1)
        values = [item.strip(" '\"") for item in raw_values.split(",") if item.strip()]
        if values:
            return impact(f"상태값이 {', '.join(values)}인 경우에만 처리 대상으로 포함하는 조건이 확인되었습니다.")
    if "user_role" in lowered and "hq_reviewer" in lowered and "!=" in lowered:
        return impact("HQ_REVIEWER 권한이 아니면 특수 사고 청구를 처리할 수 없도록 제한하는 조건이 확인되었습니다.")
    if "status eq" in lowered or "status ==" in lowered:
        status_context = re.search(r"status\s*(?:eq|==)\s*(?:\"|')([A-Z_]+)(?:\"|')", text, flags=re.IGNORECASE)
        if status_context:
            return impact(f"상태값이 {status_context.group(1)}일 때만 화면 액션 또는 처리 흐름이 열리도록 제한하는 조건이 확인되었습니다.")
    if "status in" in lowered:
        quoted = re.findall(r"(?:\"|')([A-Z_]+)(?:\"|')", text)
        filtered = [item for item in quoted if item in {"PAID", "READY", "REVIEW_REQUIRED", "REVIEW", "CLOSED", "CANCELLED", "APPROVED", "PENDING", "REJECTED"}]
        if filtered:
            return impact(f"상태값이 {', '.join(filtered)}일 때만 화면 액션 또는 처리 흐름이 열리도록 제한하는 조건이 확인되었습니다.")
    quoted_value = re.findall(r"(?:\"|')([A-Z0-9_]+)(?:\"|')", text)
    if ("branch_code" in lowered or "channel_code" in lowered) and quoted_value:
        if "hq" in lowered:
            return impact(f"{quoted_value[0]} 조건에서는 본사 승인 또는 본사 조직 조건이 필요하도록 제한하는 규칙이 확인되었습니다.")

    state_list_match = re.search(r"\[(?:\"|')([A-Z_]+)(?:\"|')(?:\s*,\s*(?:\"|')([A-Z_]+)(?:\"|'))+\]", text)
    if state_list_match and any(token in lowered for token in ("closed", "cancelled", "ready", "paid", "review_required")):
        values = re.findall(r"(?:\"|')([A-Z_]+)(?:\"|')", text)
        if values:
            return impact(f"상태값이 {', '.join(values)}로 제한되는 조건이 확인되었습니다.")

    amount_match = re.search(r">=\s*([0-9]{6,})", text)
    if amount_match:
        amount = amount_match.group(1)
        return impact(f"처리 금액이 {amount} 이상일 때 별도 제한을 적용하는 조건이 확인되었습니다.")
    if ".equals(" in text or "==" in text:
        quoted = re.findall(r"(?:\"|')([^\"']+)(?:\"|')", text)
        if quoted:
            return impact(f"{', '.join(quoted[:2])} 값 비교를 기준으로 처리 가능 여부를 분기하는 조건이 확인되었습니다.")

    if "지점장 300만원 한도" in rule_title:
        return impact("청구 금액이 300만원 이상이면 지점장 권한으로는 처리할 수 없도록 제한하는 조건이 확인되었습니다.")
    if "대리점 고액 주문 본사 전용" in rule_title:
        return impact("대리점 채널의 고액 주문은 본사 승인 조건을 충족해야 처리되도록 제한하는 조건이 확인되었습니다.")
    if "수출 주문 고액건 REVIEW_REQUIRED" in rule_title:
        return impact("수출 주문은 고액 조건에 해당하면 REVIEW_REQUIRED 상태로 전이되도록 설정한 조건이 확인되었습니다.")
    if "FRAUD 본사 심사 전용" in rule_title:
        return impact("사고 유형이 FRAUD이면 HQ_REVIEWER 권한에서만 처리되도록 제한하는 조건이 확인되었습니다.")
    if "B99 긴급건 본사 선승인" in rule_title:
        return impact("B99 지점의 긴급 건은 본사 선승인 조건이 충족되어야 처리되도록 제한하는 조건이 확인되었습니다.")
    if "마감 상태 조정 금지" in rule_title or "마감/취소 상태 조정 금지" in rule_title or "상태 조정 금지" in rule_title:
        return impact("상태가 CLOSED 또는 CANCELLED이면 조정을 차단하는 조건이 확인되었습니다.")
    if rule_title:
        return impact(f"제공 자산에서 '{rule_title}'와 직접 연결되는 조건이 확인되었습니다.")
    return ""


def _surface_mode_from_pkg(pkg: dict[str, Any]) -> str:
    extensions = pkg.get("extensions") if isinstance(pkg, dict) else {}
    return _surface_mode_from_extensions(extensions if isinstance(extensions, dict) else None)


def _family_classification_from_pkg(pkg: dict[str, Any]) -> dict[str, Any]:
    family = pkg.get("family_classification") if isinstance(pkg, dict) else {}
    if isinstance(family, dict) and family:
        return family
    authoritative = pkg.get("authoritative_payload") if isinstance(pkg, dict) else {}
    authoritative = authoritative if isinstance(authoritative, dict) else {}
    fallback = authoritative.get("family_classification")
    return fallback if isinstance(fallback, dict) else {}


def _secondary_family_signals_from_pkg(pkg: dict[str, Any]) -> set[str]:
    family_payload = _family_classification_from_pkg(pkg)
    signals = family_payload.get("secondary_signals") if isinstance(family_payload, dict) else []
    if not isinstance(signals, list):
        return set()
    return {str(item or "").strip() for item in signals if str(item or "").strip()}


def _effective_package_information_role(pkg: dict[str, Any]) -> str:
    role = package_information_role(pkg)
    if role:
        return role
    # Older/current runs may persist a document_consulting primary family while
    # the request axis and secondary signal clearly identify a GL diagnosis
    # document. Keep this correction in the surface layer so Structure and
    # Decision primary-family paths are not changed.
    if package_question_axis(pkg) == "journal_linkage" and "operational_source" in _secondary_family_signals_from_pkg(pkg):
        return "diagnosis"
    return ""


def _effective_family_for_consulting_surface(pkg: dict[str, Any]) -> str:
    family = str(_family_classification_from_pkg(pkg).get("family") or "").strip()
    if _effective_package_information_role(pkg) == "diagnosis" and family != "operational_source":
        return "operational_source"
    return family


def _render_operational_export_lines(
    pkg: dict[str, Any],
    *,
    section_key: str,
    lines: list[str],
    fallback_lines: list[str] | None = None,
) -> list[str]:
    family = str(_family_classification_from_pkg(pkg).get("family") or "").strip()
    information_role = _effective_package_information_role(pkg)
    if family != "operational_source" and information_role != "diagnosis":
        return lines
    rendered = _TEMPLATE_SUPPORT.render_operational_section_lines(
        section_key=section_key,
        lines=lines,
        domain_override=str(pkg.get("narrative_axis") or "").strip(),
        fallback_lines=fallback_lines or lines,
    )
    if information_role == "diagnosis":
        return purify_diagnosis_lines(section_key, rendered)
    return rendered


def _operational_consulting_section_key(
    pkg: dict[str, Any],
    *,
    chapter_key: str,
    section_key: str,
) -> str:
    family = str(_family_classification_from_pkg(pkg).get("family") or "").strip()
    if family != "operational_source":
        return ""
    mapping = {
        ("overview", "as_is"): "analysis_summary",
        ("approach", "gap"): "primary_judgment_reason",
        ("approach", "risks"): "risks",
        ("implementation", "process_flow"): "execution_plan",
        ("implementation", "actions"): "recommended_directions",
        ("design", "process_flow"): "execution_plan",
        ("vision", "actions"): "recommended_directions",
    }
    return mapping.get((str(chapter_key or "").strip(), str(section_key or "").strip()), "")


def _display_option_name(name: str) -> str:
    return re.sub(r"^옵션\s+[A-Z]\.\s*", "", str(name or "").strip()).strip() or str(name or "").strip()


def _attach_object_particle(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return stripped
    code = ord(stripped[-1])
    if 0xAC00 <= code <= 0xD7A3:
        has_batchim = (code - 0xAC00) % 28 != 0
        return stripped + ("을" if has_batchim else "를")
    return stripped + "을"


def _preferred_option_from_pkg(pkg: dict[str, Any]) -> dict[str, Any]:
    option = pkg.get("recommended_option") if isinstance(pkg, dict) else {}
    if isinstance(option, dict) and any(str(option.get(key) or "").strip() for key in ("name", "structure_summary", "selection_reason")):
        return option
    design = pkg.get("design") if isinstance(pkg, dict) else {}
    design = design if isinstance(design, dict) else {}
    options = design.get("design_options")
    if not isinstance(options, list):
        return {}
    for item in options:
        if isinstance(item, dict) and bool(item.get("recommended")):
            return item
    for item in options:
        if isinstance(item, dict):
            return item
    return {}


def _comparison_first_lines(pkg: dict[str, Any], *, section_key: str) -> list[str]:
    if _surface_mode_from_pkg(pkg) != "comparison_first_option":
        return []
    information_role = package_information_role(pkg)
    decision_lines = _calculation_rule_decision_lines(pkg, section_key=section_key, information_role=information_role)
    if decision_lines:
        return decision_lines
    option = _preferred_option_from_pkg(pkg)
    option_name = str(option.get("name") or "").strip()
    option_label = _display_option_name(option_name)
    structure_summary = str(option.get("structure_summary") or "").strip()
    selection_reason = str(option.get("selection_reason") or "").strip()
    option_risks = [str(item).strip() for item in option.get("risks") or [] if str(item).strip()]
    option_advantages = [str(item).strip() for item in option.get("expected_outcomes") or option.get("advantages") or [] if str(item).strip()]
    design = pkg.get("design") if isinstance(pkg, dict) else {}
    design = design if isinstance(design, dict) else {}
    design_options = [item for item in (design.get("design_options") or []) if isinstance(item, dict)]
    display_strategy = str(_family_classification_from_pkg(pkg).get("display_strategy") or "").strip() or "비교 기준 우선"
    if section_key == "report_purpose":
        if option_label:
            return [f"복수 선택지를 {display_strategy} 원칙으로 검토해 {_attach_object_particle(option_label)} 우선 검토안으로 정리하기 위한 보고서입니다."]
        return [f"복수 선택지를 {display_strategy} 원칙으로 검토해 추천안을 정리하기 위한 보고서입니다."]
    if section_key == "executive_summary_v2":
        lines = [f"비교 관점: {display_strategy} 기준으로 {max(len(design_options), 1)}개 선택지를 나란히 검토했습니다."]
        if information_role == "decision":
            if option_label:
                lines.append(f"우선 검토안: {option_label}")
            if selection_reason:
                lines.append(f"선택 이유: {selection_reason}")
            return lines
        if option_label and structure_summary:
            lines.append(f"우선 검토안: {option_label} - {structure_summary}")
        elif option_label:
            lines.append(f"우선 검토안: {option_label}")
        if selection_reason:
            lines.append(f"선택 이유: {selection_reason}")
        if option_risks and information_role != "decision":
            lines.append(f"유의점: {option_risks[0]}")
        return lines
    if section_key == "one_line_conclusion":
        if information_role == "decision":
            return [f"우선 검토안은 {option_label}입니다."] if option_label else []
        if option_label and structure_summary and selection_reason:
            return [f"우선 검토안은 {option_label}입니다. {structure_summary}를 기준으로 {selection_reason}"]
        if option_label and structure_summary:
            return [f"우선 검토안은 {option_label}입니다. {structure_summary}"]
        if option_label:
            return [f"우선 검토안은 {option_label}입니다."]
        return []
    if section_key == "primary_judgment_reason":
        if information_role == "decision":
            if selection_reason:
                return [f"비교 기준은 {selection_reason}입니다."]
            if structure_summary:
                return [f"비교 기준은 {structure_summary}입니다."]
            return []
        if selection_reason and structure_summary:
            return [f"비교 기준은 {selection_reason}이며, 핵심 판단 축은 {structure_summary}입니다."]
        if selection_reason:
            return [f"비교 기준은 {selection_reason}입니다."]
        if structure_summary:
            return [f"비교 기준은 {structure_summary}입니다."]
        return []
    if section_key == "recommended_option":
        lines: list[str] = []
        if information_role == "decision":
            if option_label:
                lines.append(f"추천안은 {option_label}입니다.")
            if selection_reason:
                lines.append(f"추천 근거는 {selection_reason}입니다.")
            for item in option_advantages[:2]:
                lines.append(f"기대 효과: {item}")
            return lines
        if option_label and structure_summary:
            lines.append(f"추천안은 {option_label}이며, {structure_summary}를 중심으로 비교 우위를 확보합니다.")
        elif option_label:
            lines.append(f"추천안은 {option_label}입니다.")
        if selection_reason:
            lines.append(f"추천 근거는 {selection_reason}입니다.")
        for item in option_advantages[:2]:
            lines.append(f"기대 효과: {item}")
        return lines
    if section_key == "execution_plan" and information_role == "decision":
        return [
            "선택지 확인: 후보안을 동일 기준으로 비교합니다.",
            "근거 보강: 직접 확인된 기준과 제약을 보강합니다.",
            "적용 판단: 추천안의 선행 조건이 충족될 때 실행 후보로 둡니다.",
        ]
    if section_key == "risks":
        if information_role == "decision":
            return []
        if option_risks:
            return option_risks[:2]
    return []


def _calculation_rule_decision_lines(
    pkg: dict[str, Any],
    *,
    section_key: str,
    information_role: str,
) -> list[str]:
    if information_role != "decision" or package_question_axis(pkg) != "calculation_rule":
        return []
    if not _is_fx_fifo_package(pkg):
        return []
    if section_key == "report_purpose":
        return ["계산 규칙 선택지를 비교해 우선 적용할 기준과 검증 조건을 정리하기 위한 문서입니다."]
    if section_key == "executive_summary_v2":
        return [
            "선택지: 현행 FIFO 기준 유지, 평균 기준 단순화, 거래별 지정 기준을 비교합니다.",
            "비교 기준: 계산 재현성, 환율 기준 일관성, 회계 연결 검증 가능성을 우선합니다.",
            "추천안: 현행 FIFO 기준을 유지하고 예외 검증을 보강합니다.",
            "참조: 처리 흐름 상세는 Structure 문서, 전표/GL 영향은 Diagnosis 문서에서만 다룹니다.",
        ]
    if section_key == "one_line_conclusion":
        return ["우선 선택은 현행 FIFO 계산 기준 유지와 예외 검증 보강입니다."]
    if section_key == "primary_judgment_reason":
        return ["비교 기준은 계산 재현성, 환율 기준 일관성, 회계 연결 검증 가능성입니다."]
    if section_key == "recommended_option":
        return [
            "추천안: 현행 FIFO 기준을 유지하고 환율 비교와 회계 연결 검증을 함께 둡니다.",
            "선택 이유: 기존 lot 추적성을 유지하면서 계산 결과를 재현할 수 있습니다.",
            "대안 한계: 평균 기준은 단순하지만 lot 추적성이 약해지고, 거래별 지정 기준은 운영 입력 부담이 큽니다.",
        ]
    if section_key == "execution_plan":
        return [
            "선택지 확정: 세 계산 기준을 같은 비교 기준으로 다시 대조합니다.",
            "검증 조건 정의: 예외와 취소 처리에서도 같은 계산 기준이 유지되는지 확인합니다.",
            "적용 판단: 계산 결과와 회계 연결 검증이 동시에 통과한 기준만 적용 후보로 둡니다.",
        ]
    return []


def _is_fx_fifo_package(pkg: dict[str, Any]) -> bool:
    if not isinstance(pkg, dict):
        return False
    text_parts: list[str] = []
    for key in (
        "report_purpose",
        "core_conclusion",
        "primary_judgment_reason",
        "analysis_summary",
        "executive_summary_v2",
        "core_business_rules",
        "recommended_directions",
        "risks",
    ):
        value = pkg.get(key)
        if isinstance(value, str):
            text_parts.append(value)
        elif isinstance(value, list):
            text_parts.extend(str(item) for item in value if str(item).strip())
    text = " ".join(text_parts).lower()
    return sum(1 for keyword in ("fifo", "lot", "환차", "전표", "gl", "외화") if keyword in text) >= 2


def _export_validated_block_lines(pkg: dict[str, Any], *, section_key: str) -> list[str]:
    for item in pkg.get("validated_explanation_blocks") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("block_id") or "").strip() != section_key:
            continue
        lines = item.get("resolved_lines")
        if not isinstance(lines, list) or not lines:
            lines = item.get("deterministic_lines")
        if not isinstance(lines, list):
            return []
        return [str(line or "").strip() for line in lines if str(line or "").strip()]
    return []


def _export_validated_narrative_lines(pkg: dict[str, Any], *, section_key: str) -> list[str]:
    narrative_layer = pkg.get("validated_narrative_layer")
    if not isinstance(narrative_layer, dict):
        return []
    value = narrative_layer.get(section_key)
    if isinstance(value, list):
        return [str(line or "").strip() for line in value if str(line or "").strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _export_polish_lines(pkg: dict[str, Any], *, section_key: str, audience: str) -> list[str]:
    polish_bundle = pkg.get("polish_bundle")
    if not isinstance(polish_bundle, dict):
        return []
    for section in polish_bundle.get("polished_sections") or []:
        if not isinstance(section, dict):
            continue
        if str(section.get("section_key") or "").strip() != section_key:
            continue
        audience_variants = section.get("audience_variants") or {}
        if not isinstance(audience_variants, dict):
            return []
        text = str(audience_variants.get(audience) or "").strip()
        if not text:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]
    return []


def _export_deterministic_lines(pkg: dict[str, Any], *, section_key: str) -> list[str]:
    comparison_lines = _comparison_first_lines(pkg, section_key=section_key)
    if comparison_lines:
        return comparison_lines
    family = str(_family_classification_from_pkg(pkg).get("family") or "").strip()
    question_axis = package_question_axis(pkg)
    if family == "operational_source" and question_axis == "calculation_rule" and section_key == "recommended_option":
        return [
            "추천안: 현행 FIFO 기준을 유지하고 환율 비교와 회계 연결 검증을 함께 둡니다.",
            "비교 기준: 계산 재현성, 환율 기준 일관성, 회계 연결 가능성을 우선합니다.",
            "참조: 흐름 상세와 리스크 상세는 Structure, Diagnosis 문서에서만 다룹니다.",
        ]
    if section_key == "report_purpose":
        text = str(pkg.get("report_purpose") or "").strip()
        return [text] if text else []
    if section_key == "executive_summary_v2":
        return [str(line or "").strip() for line in (pkg.get("executive_summary_v2") or []) if str(line or "").strip()]
    if section_key == "one_line_conclusion":
        text = str(pkg.get("core_conclusion") or "").strip()
        return [text] if text else []
    if section_key == "analysis_summary":
        return [str(line or "").strip() for line in (pkg.get("analysis_summary") or []) if str(line or "").strip()]
    if section_key == "primary_judgment_reason":
        text = str(pkg.get("primary_judgment_reason") or "").strip()
        if text:
            return [text]
        authoritative = pkg.get("authoritative_payload") if isinstance(pkg, dict) else {}
        authoritative = authoritative if isinstance(authoritative, dict) else {}
        decision_summary = authoritative.get("decision_summary") if isinstance(authoritative.get("decision_summary"), dict) else {}
        decisions = decision_summary.get("decisions") or []
        if isinstance(decisions, list) and decisions and isinstance(decisions[0], dict):
            rationale = str(decisions[0].get("rationale") or "").strip()
            return [rationale] if rationale else []
        return []
    if section_key == "recommended_option":
        option = pkg.get("recommended_option") if isinstance(pkg, dict) else {}
        if not isinstance(option, dict):
            return []
        name = str(option.get("name") or "").strip()
        structure_summary = str(option.get("structure_summary") or "").strip()
        selection_reason = str(option.get("selection_reason") or "").strip()
        if name and structure_summary and selection_reason:
            return [f"추천안은 {name}이며, {structure_summary}를 기준으로 {selection_reason}"]
        if name and selection_reason:
            return [f"추천안은 {name}이며, {selection_reason}"]
        if structure_summary and selection_reason:
            return [f"{structure_summary}를 기준으로 {selection_reason}"]
        text = name or structure_summary or selection_reason
        return [text] if text else []
    if section_key == "recommended_directions":
        return [str(line or "").strip() for line in (pkg.get("recommended_directions") or []) if str(line or "").strip()]
    if section_key == "execution_plan":
        plan = pkg.get("execution_plan") if isinstance(pkg, dict) else []
        if not isinstance(plan, list):
            return []
        lines: list[str] = []
        for item in plan:
            if not isinstance(item, dict):
                continue
            week_label = str(item.get("week_label") or "").strip()
            goal = str(item.get("goal") or "").strip()
            tasks = item.get("tasks") if isinstance(item.get("tasks"), list) else []
            first_task = next((str(task or "").strip() for task in tasks if str(task or "").strip()), "")
            base = f"{week_label}: {goal}" if week_label and goal else (goal or week_label)
            if not base:
                continue
            if first_task:
                lines.append(f"{base}. 주요 작업은 {first_task}입니다.")
            else:
                lines.append(base)
        return lines
    if section_key == "risks":
        diagnosis = pkg.get("diagnosis") if isinstance(pkg, dict) else {}
        diagnosis = diagnosis if isinstance(diagnosis, dict) else {}
        return [str(item or "").strip() for item in (diagnosis.get("risks") or []) if str(item or "").strip()]
    return []


def _externalize_export_line(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return ""
    replacements = (
        ("해야 합니다", ""),
        ("해야합니다", ""),
        ("해야 한다", ""),
        ("검토하는 것이 필요합니다", ""),
        ("확정하는 것이 필요합니다", ""),
        ("정리하는 것이 필요합니다", ""),
        ("확인하는 것이 필요합니다", ""),
        ("필요합니다", ""),
    )
    for old, new in replacements:
        normalized = normalized.replace(old, new)
    return normalized.strip(" ,.")


def _export_preferred_lines(
    pkg: dict[str, Any],
    *,
    section_key: str,
    audience: str = "manager",
    surface_mode: str = "internal",
) -> list[str]:
    comparison_first_surface = _surface_mode_from_pkg(pkg) == "comparison_first_option"
    lines: list[str] = []
    deterministic_lines = _export_deterministic_lines(pkg, section_key=section_key)
    if comparison_first_surface:
        lines = list(deterministic_lines)
    if not lines:
        lines = _export_validated_block_lines(pkg, section_key=section_key)
    if not lines:
        lines = _export_validated_narrative_lines(pkg, section_key=section_key)
    if not lines:
        lines = _export_polish_lines(pkg, section_key=section_key, audience=audience)
    if not lines:
        lines = list(deterministic_lines)
    lines = _render_operational_export_lines(
        pkg,
        section_key=section_key,
        lines=lines,
        fallback_lines=deterministic_lines,
    )
    if normalize_surface_mode(surface_mode) == "external":
        return [item for item in (_externalize_export_line(line) for line in lines) if item]
    return lines


def _truncate_export_text(text: str, limit: int) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(limit - 3, 1)].rstrip() + "..."


def _apply_slide_schema_explanation_overlay(
    pkg: dict[str, Any],
    slide_schema: dict[str, Any],
    *,
    surface_mode: str,
) -> dict[str, Any]:
    slides = slide_schema.get("slides")
    if not isinstance(slides, list) or not slides:
        return slide_schema
    updated = deepcopy(slide_schema)
    updated_slides = updated.get("slides") or []
    if not isinstance(updated_slides, list) or not updated_slides:
        return updated

    report_purpose_lines = _export_preferred_lines(pkg, section_key="report_purpose", surface_mode=surface_mode)
    executive_summary_lines = _export_preferred_lines(pkg, section_key="executive_summary_v2", surface_mode=surface_mode)
    one_line_conclusion_lines = _export_preferred_lines(pkg, section_key="one_line_conclusion", surface_mode=surface_mode)
    primary_judgment_reason_lines = _export_preferred_lines(pkg, section_key="primary_judgment_reason", surface_mode=surface_mode)
    recommended_option_lines = _export_preferred_lines(pkg, section_key="recommended_option", surface_mode=surface_mode)
    execution_plan_lines = _export_preferred_lines(pkg, section_key="execution_plan", surface_mode=surface_mode)
    risks_lines = _export_preferred_lines(pkg, section_key="risks", surface_mode=surface_mode)

    first_slide = updated_slides[0] if isinstance(updated_slides[0], dict) else None
    if first_slide is not None:
        if one_line_conclusion_lines:
            first_slide["headline"] = _truncate_export_text(one_line_conclusion_lines[0], 72)
        if report_purpose_lines:
            first_slide["tagline"] = _truncate_export_text(report_purpose_lines[0], 96)
        if executive_summary_lines:
            first_slide["absorbed_summary_text"] = _truncate_export_text(" / ".join(executive_summary_lines[:2]), 120)

    if primary_judgment_reason_lines:
        target_slide = None
        for slide in updated_slides:
            if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() in {"as_is_gap", "flow", "design"}:
                target_slide = slide
                break
        if target_slide is None and first_slide is not None:
            target_slide = first_slide
        if target_slide is not None:
            target_slide["decision_message"] = _truncate_export_text(primary_judgment_reason_lines[0], 110)
    if recommended_option_lines:
        design_slide = None
        for slide in updated_slides:
            if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() == "design":
                design_slide = slide
                break
        if design_slide is not None:
            existing_note = str(design_slide.get("absorbed_summary_text") or "").strip()
            guard_note = _truncate_export_text(recommended_option_lines[0], 120)
            if existing_note and guard_note and existing_note != guard_note:
                design_slide["absorbed_summary_text"] = _truncate_export_text(f"{guard_note} / {existing_note}", 120)
            elif guard_note:
                design_slide["absorbed_summary_text"] = guard_note
    if execution_plan_lines:
        flow_slide = None
        for slide in updated_slides:
            if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() == "flow":
                flow_slide = slide
                break
        if flow_slide is not None:
            existing_note = str(flow_slide.get("footer_note") or "").strip()
            guard_note = _truncate_export_text(" / ".join(execution_plan_lines[:2]), 120)
            if existing_note and guard_note and existing_note != guard_note:
                flow_slide["footer_note"] = _truncate_export_text(f"{guard_note} / {existing_note}", 120)
            elif guard_note:
                flow_slide["footer_note"] = guard_note
    if risks_lines:
        as_is_gap_slide = None
        for slide in updated_slides:
            if isinstance(slide, dict) and str(slide.get("slide_type") or "").strip() == "as_is_gap":
                as_is_gap_slide = slide
                break
        if as_is_gap_slide is not None:
            existing_note = str(as_is_gap_slide.get("absorbed_summary_text") or "").strip()
            guard_note = _truncate_export_text(" / ".join(risks_lines[:2]), 120)
            if existing_note and guard_note and existing_note != guard_note:
                as_is_gap_slide["absorbed_summary_text"] = _truncate_export_text(f"{guard_note} / {existing_note}", 120)
            elif guard_note:
                as_is_gap_slide["absorbed_summary_text"] = guard_note
    return updated


def _resolve_consulting_deck(pkg: dict[str, Any], *, surface_mode: str) -> dict[str, Any] | None:
    existing = pkg.get("consulting_deck")
    if isinstance(existing, dict) and isinstance(existing.get("chapters"), list):
        if str(existing.get("surface_mode") or "").strip() == surface_mode:
            return existing
    contract_payload = pkg.get("consulting_min_contract")
    if not isinstance(contract_payload, dict):
        return existing if isinstance(existing, dict) else None
    try:
        contract = ConsultingMinContract.model_validate(contract_payload)
    except Exception:
        return existing if isinstance(existing, dict) else None
    project_payload = pkg.get("project") if isinstance(pkg.get("project"), dict) else {}
    return build_consulting_deck(
        contract,
        project_name=str(project_payload.get("project_name") or ""),
        client_name=str(project_payload.get("client_name") or ""),
        surface_mode=surface_mode,
        family=_effective_family_for_consulting_surface(pkg),
        question_axis=package_question_axis(pkg),
    )


def _resolve_slide_schema(pkg: dict[str, Any], *, surface_mode: str) -> dict[str, Any] | None:
    existing = pkg.get("slide_schema")
    if isinstance(existing, dict) and isinstance(existing.get("slides"), list):
        if str(existing.get("surface_mode") or "").strip() == surface_mode:
            return _apply_slide_schema_explanation_overlay(pkg, existing, surface_mode=surface_mode)
    consulting_deck = _resolve_consulting_deck(pkg, surface_mode=surface_mode)
    if not isinstance(consulting_deck, dict):
        return existing if isinstance(existing, dict) else None
    try:
        deck_model = ConsultingDeck.model_validate(consulting_deck)
    except Exception:
        return existing if isinstance(existing, dict) else None
    return _apply_slide_schema_explanation_overlay(
        pkg,
        build_slide_schema(deck_model).model_dump(),
        surface_mode=surface_mode,
    )


def _markdown_section_registry(pkg: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    family = str(_family_classification_from_pkg(pkg).get("family") or "").strip()
    role = _effective_package_information_role(pkg)
    if family in {"operational_source", "option_comparison"} or role == "diagnosis":
        role_registry = _OPERATIONAL_ROLE_MARKDOWN_SECTION_REGISTRY.get(role)
        if role_registry:
            return role_registry
    return _MARKDOWN_SECTION_REGISTRY.get(family, _MARKDOWN_SECTION_REGISTRY["default"])


def _uses_family_markdown_registry(pkg: dict[str, Any]) -> bool:
    family = str(_family_classification_from_pkg(pkg).get("family") or "").strip()
    return family in {"operational_source", "option_comparison"} or _effective_package_information_role(pkg) == "diagnosis"


def _split_markdown_line_fragments(text: str) -> list[str]:
    prepared: list[str] = []
    for raw_line in str(text or "").splitlines():
        normalized = str(raw_line or "").strip()
        if not normalized:
            continue
        if re.search(r":\s+-\s+", normalized):
            prefix, remainder = normalized.split(":", 1)
            prefix = prefix.strip()
            fragments = [part.strip(" -") for part in re.split(r"\s+-\s+", remainder.strip()) if part.strip(" -")]
            if fragments and prefix in {"보조 판단", "운영 판단"}:
                prepared.extend(fragments)
                continue
        prepared.append(normalized)
    return prepared


def _normalize_markdown_sentence(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return ""
    normalized = re.sub(r"^\s*(?:[-*•]\s*)+", "", normalized)
    normalized = re.sub(r"\.{2,}", ".", normalized)
    normalized = re.sub(r"(합니다|입니다)\.\s*입니다\.", r"\1.", normalized)
    normalized = re.sub(r"(합니다|입니다)\.\s*합니다\.", r"\1.", normalized)
    normalized = re.sub(r"([.?!])\s*([.?!])+", r"\1", normalized)
    normalized = re.sub(r"\s+([,.;:])", r"\1", normalized)
    return normalized.strip()


def _markdown_sentence_key(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or "").strip()).lower()


def _normalize_markdown_section_lines(lines: list[str]) -> list[str]:
    normalized_lines: list[str] = []
    seen: set[str] = set()
    for raw_line in lines:
        for fragment in _split_markdown_line_fragments(raw_line):
            sentence = _normalize_markdown_sentence(fragment)
            if not sentence:
                continue
            key = _markdown_sentence_key(sentence)
            if not key or key in seen:
                continue
            seen.add(key)
            normalized_lines.append(sentence)
    return normalized_lines


def _strip_specialized_intro_prefix(pkg: dict[str, Any], *, section_key: str, lines: list[str]) -> list[str]:
    family = str(_family_classification_from_pkg(pkg).get("family") or "").strip()
    if section_key != "report_purpose" or family not in {"operational_source", "option_comparison"}:
        return lines
    if not lines:
        return lines
    updated = list(lines)
    updated[0] = re.sub(r"^\s*보조\s*판단\s*:\s*", "", str(updated[0] or "").strip())
    return [line for line in updated if str(line or "").strip()]


def _normalize_markdown_output_lines(pkg: dict[str, Any], *, section_key: str, lines: list[str]) -> list[str]:
    normalized = _normalize_markdown_section_lines(lines)
    return _strip_specialized_intro_prefix(pkg, section_key=section_key, lines=normalized)


def _normalize_markdown_document(markdown: str) -> str:
    normalized_lines: list[str] = []
    previous_semantic_key = ""
    previous_was_bullet = False
    for raw_line in str(markdown or "").splitlines():
        line = str(raw_line or "").rstrip()
        if not line.strip():
            if not normalized_lines or normalized_lines[-1] == "":
                continue
            if re.match(r"^#{1,6}\s+\S", normalized_lines[-1]):
                continue
            normalized_lines.append("")
            previous_semantic_key = ""
            previous_was_bullet = False
            continue
        if re.match(r"^\s*```", line) or re.match(r"^\s*[>|]", line):
            normalized_lines.append(line)
            previous_semantic_key = ""
            previous_was_bullet = False
            continue
        line = re.sub(r"^\s*([#]{1,6})\s+", r"\1 ", line)
        line = re.sub(r"^\s*([-*•])\s*(?:[-*•]\s*)+", r"\1 ", line)
        line = re.sub(r"[ \t]{2,}", " ", line)
        is_bullet = bool(re.match(r"^\s*[-*•]\s+", line))
        semantic_key = _markdown_sentence_key(re.sub(r"^\s*[-*•]\s+", "", line))
        if normalized_lines and normalized_lines[-1] == "" and re.match(r"^#{1,6}\s+\S", line):
            pass
        if is_bullet and previous_was_bullet and semantic_key and semantic_key == previous_semantic_key:
            continue
        normalized_lines.append(line.rstrip())
        previous_semantic_key = semantic_key
        previous_was_bullet = is_bullet
    return "\n".join(normalized_lines).strip() + "\n"


def _consulting_deck_fallback_lines(
    pkg: dict[str, Any],
    consulting_deck: dict[str, Any],
    *,
    section_key: str,
) -> list[str]:
    family = str(_family_classification_from_pkg(pkg).get("family") or "").strip()
    section_sources = (_CONSULTING_DECK_SLOT_FALLBACKS.get(family) or {}).get(section_key) or ()
    if not section_sources:
        return []
    collected: list[str] = []
    source_keys = {(str(chapter_key).strip(), str(deck_section_key).strip()) for chapter_key, deck_section_key in section_sources}
    for chapter in consulting_deck.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter_key = str(chapter.get("chapter_key") or "").strip()
        for section in chapter.get("sections") or []:
            if not isinstance(section, dict):
                continue
            deck_section_key = str(section.get("section_key") or "").strip()
            if (chapter_key, deck_section_key) not in source_keys:
                continue
            items = [str(item).strip() for item in section.get("items") or [] if str(item).strip()]
            if not items:
                continue
            collected.extend(
                _render_operational_export_lines(
                    pkg,
                    section_key=section_key,
                    lines=items,
                    fallback_lines=items,
                )
            )
    return _normalize_markdown_output_lines(pkg, section_key=section_key, lines=collected)


def _markdown_section_lines(
    pkg: dict[str, Any],
    consulting_deck: dict[str, Any],
    *,
    section_key: str,
    source_keys: tuple[str, ...] | None = None,
    surface_mode: str,
) -> list[str]:
    for candidate_key in source_keys or (section_key,):
        preferred_lines = _export_preferred_lines(
            pkg,
            section_key=candidate_key,
            surface_mode=surface_mode,
        )
        normalized = _normalize_markdown_output_lines(pkg, section_key=section_key, lines=preferred_lines)
        if normalized:
            return normalized
    return _consulting_deck_fallback_lines(pkg, consulting_deck, section_key=section_key)


def _generic_consulting_deck_overlay_lines(
    pkg: dict[str, Any],
    *,
    chapter_key: str,
    section_key: str,
    surface_mode: str,
) -> list[str]:
    source_keys = _GENERIC_CONSULTING_DECK_SECTION_OVERLAYS.get((str(chapter_key).strip(), str(section_key).strip())) or ()
    collected: list[str] = []
    for candidate_key in source_keys:
        collected.extend(
            _export_preferred_lines(
                pkg,
                section_key=candidate_key,
                surface_mode=surface_mode,
            )
        )
    return _normalize_markdown_section_lines(collected)


def _render_consulting_deck_markdown(
    pkg: dict[str, Any],
    consulting_deck: dict[str, Any],
    *,
    include_internal_appendix: bool,
    appendix_markdown: str = "",
) -> str:
    project_payload = pkg.get("project") if isinstance(pkg.get("project"), dict) else {}
    title = (
        f"# 결과 패키지 - {project_payload.get('project_name') or '-'}"
        if include_internal_appendix
        else f"# 컨설팅 결과 - {project_payload.get('project_name') or project_payload.get('id') or '-'}"
    )
    lines = [title]
    surface_mode = consulting_deck.get("surface_mode") or "internal"
    header = str(consulting_deck.get("role_header") or "").strip() or role_header(
        family=_effective_family_for_consulting_surface(pkg),
        question_axis=package_question_axis(pkg),
    )
    if header:
        lines.extend(["", header])
    if _uses_family_markdown_registry(pkg):
        for entry in _markdown_section_registry(pkg):
            section_key = str(entry.get("section_key") or "").strip()
            if not section_key:
                continue
            section_lines = _markdown_section_lines(
                pkg,
                consulting_deck,
                section_key=section_key,
                source_keys=tuple(str(item).strip() for item in entry.get("source_keys") or () if str(item).strip()) or None,
                surface_mode=surface_mode,
            )
            if not section_lines:
                continue
            heading = _surface_section_title_from_pkg(pkg, section_key, section_key)
            lines.extend(["", f"## {heading}"])
            if str(entry.get("render") or "paragraph").strip() == "list":
                lines.extend(f"- {item}" for item in section_lines)
            else:
                lines.extend(section_lines)
    else:
        narrative_layer = pkg.get("validated_narrative_layer") if isinstance(pkg.get("validated_narrative_layer"), dict) else {}
        chapter_outline = {
            str(item.get("chapter_key") or "").strip(): str(item.get("headline") or "").strip()
            for item in narrative_layer.get("consulting_deck_outline", [])
            if isinstance(item, dict)
            and str(item.get("chapter_key") or "").strip()
            and str(item.get("headline") or "").strip()
        }
        for chapter in consulting_deck.get("chapters") or []:
            if not isinstance(chapter, dict):
                continue
            chapter_key = str(chapter.get("chapter_key") or "").strip()
            chapter_title = str(chapter.get("title") or "").strip()
            if chapter_title:
                lines.extend(["", f"## {chapter_title}"])
            chapter_headline = _normalize_markdown_sentence(chapter_outline.get(chapter_key) or "")
            if chapter_headline:
                lines.append(chapter_headline)
            for section in chapter.get("sections") or []:
                if not isinstance(section, dict):
                    continue
                deck_section_key = str(section.get("section_key") or "").strip()
                section_title = str(section.get("title") or "").strip()
                if section_title:
                    lines.append(f"### {section_title}")
                items = [str(item).strip() for item in section.get("items") or [] if str(item).strip()]
                uses_placeholder = bool(section.get("uses_placeholder"))
                overlay_lines = (
                    _generic_consulting_deck_overlay_lines(
                        pkg,
                        chapter_key=chapter_key,
                        section_key=deck_section_key,
                        surface_mode=surface_mode,
                    )
                    if uses_placeholder
                    else []
                )
                if not items and not overlay_lines:
                    lines.append("- 해당 없음")
                    continue
                normalized_items = _normalize_markdown_section_lines(overlay_lines or items)
                if not normalized_items:
                    lines.append("- 해당 없음")
                    continue
                lines.extend(f"- {item}" for item in normalized_items)
    markdown = "\n".join(lines).strip() + "\n"
    if appendix_markdown.strip():
        markdown = markdown.rstrip() + "\n\n" + appendix_markdown.strip() + "\n"
    return markdown


def _extract_markdown_tail(markdown: str, heading: str) -> str:
    normalized_markdown = str(markdown or "")
    marker = normalized_markdown.find(heading)
    if marker < 0:
        return ""
    return normalized_markdown[marker:].strip()


def _normalize_internal_export_mode(mode: str | None) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized == "full":
        return "full"
    return "deck-only"


def _result_package_markdown(
    pkg: dict[str, Any],
    *,
    surface_mode: str = "internal",
    internal_export_mode: str = "deck-only",
) -> str:
    normalized_surface_mode = normalize_surface_mode(surface_mode)
    export_review_artifacts = can_export_review_artifacts(policy_for_surface_mode(normalized_surface_mode).access_profile)
    consulting_deck = _resolve_consulting_deck(pkg, surface_mode=normalized_surface_mode)
    if consulting_deck:
        appendix_markdown = ""
        include_internal_appendix = export_review_artifacts and _normalize_internal_export_mode(internal_export_mode) == "full"
        legacy_internal_markdown = ""
        if include_internal_appendix:
            legacy_internal_markdown = _legacy_result_package_markdown(pkg, surface_mode="internal")
            appendix_markdown = _extract_markdown_tail(legacy_internal_markdown, "## 참고 구조 비교")
        elif normalized_surface_mode == "internal" and isinstance(pkg.get("accounting"), dict):
            legacy_internal_markdown = _legacy_result_package_markdown(pkg, surface_mode="internal")
            appendix_markdown = _extract_markdown_tail(legacy_internal_markdown, "### 문서 맥락")
        return _normalize_markdown_document(
            _render_consulting_deck_markdown(
                pkg,
                consulting_deck,
                include_internal_appendix=include_internal_appendix,
                appendix_markdown=appendix_markdown,
            )
        )
    return _normalize_markdown_document(_legacy_result_package_markdown(pkg, surface_mode=normalized_surface_mode))


def _legacy_result_package_markdown(pkg: dict[str, Any], *, surface_mode: str = "internal") -> str:
    normalized_surface_mode = normalize_surface_mode(surface_mode)
    export_review_artifacts = can_export_review_artifacts(policy_for_surface_mode(normalized_surface_mode).access_profile)
    if not export_review_artifacts:
        explanation = _present_project_result_impl(
            project_id=str((pkg.get("project") or {}).get("id") or ""),
            result_package=pkg,
            audience="manager",
            surface_mode=normalized_surface_mode,
        )
        return _result_explanation_markdown(explanation)
    executive_summary = pkg.get("executive_summary") or {}
    display = pkg.get("display") or {}
    display_sections = display.get("sections") or {}
    display_states = display.get("section_states") or {}
    hero = display.get("hero") or {}
    provenance = pkg.get("provenance") or {}
    scope_notice = pkg.get("scope_notice") or {}
    report_purpose = str(pkg.get("report_purpose") or "").strip()
    report_scope = _trim_items(pkg.get("report_scope") or [], limit=6)
    report_questions = _trim_items(pkg.get("report_questions") or [], limit=6)
    report_purpose_lines = _export_preferred_lines(pkg, section_key="report_purpose", surface_mode=normalized_surface_mode)
    executive_summary_lines = _export_preferred_lines(pkg, section_key="executive_summary_v2", surface_mode=normalized_surface_mode)
    core_conclusion_lines = _export_preferred_lines(pkg, section_key="one_line_conclusion", surface_mode=normalized_surface_mode)
    analysis_summary_lines = _export_preferred_lines(pkg, section_key="analysis_summary", surface_mode=normalized_surface_mode)
    judgment_reason_lines = _export_preferred_lines(pkg, section_key="primary_judgment_reason", surface_mode=normalized_surface_mode)
    recommended_option_lines = _export_preferred_lines(pkg, section_key="recommended_option", surface_mode=normalized_surface_mode)
    execution_plan_lines = _export_preferred_lines(pkg, section_key="execution_plan", surface_mode=normalized_surface_mode)
    risk_explanation_lines = _export_preferred_lines(pkg, section_key="risks", surface_mode=normalized_surface_mode)
    grounded_rules = ((display_sections.get("grounded_rules") or {}).get("items") or [])
    retained = pkg.get("retained_contracts") or []
    priority_items = pkg.get("priority_split_items") or []
    verification = pkg.get("verification_checkpoints") or []
    design_options = ((display_sections.get("design_options") or {}).get("items") or [])
    execution_plan = ((display_sections.get("execution_plan") or {}).get("items") or [])
    risks = ((display_sections.get("risks") or {}).get("items") or [])
    missing_context_details = ((display_sections.get("risks") or {}).get("missing_context_details") or [])
    design = pkg.get("design") or {}
    layer = design.get("layer_reconstruction") or {}
    draft = ((pkg.get("transition_draft") or {}).get("recomposition_draft") or {})
    review_diff = (((pkg.get("extensions") or {}) if isinstance(pkg, dict) else {}) or {}).get("review_diff") or {}
    review_diff_markdown = str(review_diff.get("markdown") or "").strip()
    lines = [
        f"# 결과 패키지 - {pkg['project']['project_name']}",
        "",
        f"## {_surface_section_title_from_pkg(pkg, 'report_purpose', '보고 목적')}",
        report_purpose_lines[0] if report_purpose_lines else (report_purpose or "이 실행의 목적을 다시 정해야 합니다."),
        "",
        f"## {_surface_section_title_from_pkg(pkg, 'executive_summary_v2', '핵심 요약')}",
    ]
    if executive_summary_lines:
        lines.extend(f"- {item}" for item in executive_summary_lines)
    else:
        lines.append(f"- {hero.get('impact') or executive_summary.get('core_message') or '-'}")
    lines.extend(
        [
            "",
            f"## {_surface_section_title_from_pkg(pkg, 'one_line_conclusion', '핵심 결론')}",
            core_conclusion_lines[0] if core_conclusion_lines else str(hero.get("headline") or executive_summary.get("core_message") or "-"),
        ]
    )
    if analysis_summary_lines:
        lines.extend(
            [
                "",
                f"## {_surface_section_title_from_pkg(pkg, 'analysis_summary', '핵심 객체')}",
            ]
        )
        lines.extend(f"- {item}" for item in analysis_summary_lines)
    lines.extend(
        [
            "",
            f"## {_surface_section_title_from_pkg(pkg, 'primary_judgment_reason', '판단 이유')}",
        ]
    )
    if judgment_reason_lines:
        lines.extend(judgment_reason_lines)
    else:
        lines.append(str(hero.get("priority_action") or "-"))
    if recommended_option_lines:
        lines.extend(
            [
                "",
                f"## {_surface_section_title_from_pkg(pkg, 'recommended_option', '추천안 설명')}",
                recommended_option_lines[0],
            ]
        )
    if execution_plan_lines:
        lines.extend(
            [
                "",
                f"## {_surface_section_title_from_pkg(pkg, 'execution_plan', '실행 단계 설명')}",
            ]
        )
        lines.extend(f"- {item}" for item in execution_plan_lines)
    if risk_explanation_lines:
        lines.extend(
            [
                "",
                f"## {_surface_section_title_from_pkg(pkg, 'risks', '리스크 설명')}",
            ]
        )
        lines.extend(f"- {item}" for item in risk_explanation_lines)
    lines.extend(
        [
            "",
            "## 결정 요약",
        f"- 영향: {hero.get('impact') or '-'}",
        f"- 우선 조치: {hero.get('priority_action') or '-'}",
        "",
        "## 판단 근거",
        ]
    )
    if grounded_rules:
        for rule in grounded_rules:
            lines.extend(
                [
                    f"### {rule.get('title') or '-'}",
                    f"- 판단: {rule.get('decision') or '-'}",
                    f"- 미조치 시 영향: {rule.get('unchanged_consequence') or rule.get('impact') or '-'}",
                    f"- 우선 검토 포인트: {rule.get('action') or '-'}",
                    f"- 피해야 할 방식: {rule.get('anti_pattern') or '-'}",
                    f"- 우선순위: {rule.get('priority') or '-'}",
                    f"- 우선순위 판단: {rule.get('priority_reason') or '-'}",
                    f"- 신뢰도: {rule.get('confidence') or '-'}",
                    f"- 신뢰도 근거: {rule.get('confidence_reason') or '-'}",
                    f"- 설계 반영 위치: {', '.join(rule.get('design_targets') or []) or '-'}",
                    f"- 추가 검증 필요: {'예' if rule.get('needs_verification') else '아니오'}",
                ]
            )
            evidence_rows = rule.get("evidence_cards") or []
            if evidence_rows:
                lines.append("- 근거 자산")
                for evidence in evidence_rows:
                    lines.append(f"  - {evidence.get('asset_name') or '-'}")
                    lines.append(f"    - 근거 요약: {evidence.get('condition_summary') or '-'}")
                    lines.append(f"    - 왜 중요한가: {evidence.get('why_important') or '-'}")
                    lines.append(f"    - 설계 반영 위치: {', '.join(evidence.get('design_targets') or []) or '-'}")
                    lines.append(f"    - 신뢰도: {evidence.get('confidence') or '-'}")
    else:
        fallback_core_rules = _trim_items(pkg.get("core_business_rules") or [], limit=4)
        if fallback_core_rules:
            lines.extend(f"- {item}" for item in fallback_core_rules)
        else:
            lines.append(f"- {(display_sections.get('grounded_rules') or {}).get('empty_message') or '핵심 규칙 근거를 먼저 확보해야 합니다.'}")
    lines.extend(["", "## 개선 전략"])
    if design_options:
        for option in design_options:
            lines.extend(
                [
                    f"### {option.get('name') or '-'}",
                    f"- 판단: {option.get('decision') or '-'}",
                    f"- 미조치 시 영향: {option.get('unchanged_consequence') or '-'}",
                    f"- 우선 검토 포인트: {option.get('action') or '-'}",
                    f"- 우선순위: {option.get('priority') or '-'}",
                    f"- 우선순위 판단: {option.get('priority_reason') or '-'}",
                    f"- 장점: {' / '.join(option.get('advantages') or []) or '-'}",
                    f"- 리스크: {' / '.join(option.get('risks') or []) or '-'}",
                    f"- 추천 여부: {'예' if option.get('recommended') else '아니오'}",
                    f"- 선택 근거: {option.get('selection_reason') or '-'}",
                    "",
                ]
            )
            for point in option.get("comparison_points") or []:
                lines.append(f"- 비교 포인트 / {point.get('label') or '-'}: {point.get('value') or '-'}")
            lines.append("")
        if lines[-1] == "":
            lines.pop()
    else:
        lines.append(f"- {(display_sections.get('design_options') or {}).get('empty_message') or '전략 우선순위를 다시 정해야 합니다.'}")
    lines.extend(["", "## 실행 단계"])
    if execution_plan:
        for week in execution_plan:
            lines.extend(
                [
                    f"### {week.get('week_label') or '-'}",
                    f"- 판단: {week.get('decision') or '-'}",
                    f"- 미조치 시 영향: {week.get('unchanged_consequence') or '-'}",
                    f"- 우선 검토 포인트: {week.get('action') or '-'}",
                    f"- 우선순위: {week.get('priority') or '-'}",
                    f"- 우선순위 판단: {week.get('priority_reason') or '-'}",
                    f"- 작업: {' / '.join(week.get('tasks') or []) or '해당 없음'}",
                    f"- 관련 규칙: {', '.join(week.get('related_rules') or []) or '해당 없음'}",
                    f"- 관련 계약: {', '.join(week.get('related_contracts') or []) or '해당 없음'}",
                    f"- 인력: {' / '.join(week.get('roles') or []) or '해당 없음'}",
                    f"- 기간: {week.get('duration_weeks') or 0}주",
                    f"- 산출물: {' / '.join(week.get('deliverables') or []) or '해당 없음'}",
                ]
            )
    else:
        lines.append(f"- {(display_sections.get('execution_plan') or {}).get('empty_message') or '실행 순서를 다시 정해야 합니다.'}")
    lines.extend(["", "## 리스크"])
    if risks:
        lines.extend(f"- {item}" for item in risks)
    else:
        lines.append(f"- {(display_sections.get('risks') or {}).get('empty_message') or '리스크 범위를 다시 확인해야 합니다.'}")
    if missing_context_details:
        lines.extend(["", "### 확인 필요 자료"])
        for item in missing_context_details:
            lines.append(f"- {item.get('required_material') or '-'}: {item.get('reason') or '-'}")
            lines.append(f"  - 우선순위: {item.get('priority') or '-'}")
    lines.extend(["", "## 참고 구조 비교"])
    if review_diff_markdown:
        lines.extend(
            [
                "- 이 섹션은 실제 코드 패치가 아니라 변경 전, 변경 후, 근거를 비교해 의사결정을 보강하는 자료입니다.",
                "- diff와 expected_pattern은 승인 판단을 돕는 비교 근거로만 사용합니다.",
                "",
                _demote_markdown_headings(review_diff_markdown, levels=1),
            ]
        )
    else:
        lines.append("- 참고 구조 비교 데이터가 부족해 변경 근거를 다시 모아야 합니다.")
    lines.extend(["", "## 부록"])
    lines.extend(
        [
            "### 문서 맥락",
            f"- 목적: {(report_purpose_lines[0] if report_purpose_lines else report_purpose) or '이 실행의 목적을 다시 정해야 합니다.'}",
            "- 분석 범위",
            *([f"  - {item}" for item in report_scope] if report_scope else [f"  - {display_states.get('report_scope') or '분석 범위를 다시 확인해야 합니다.'}"]),
            "- 검증 질문",
            *([f"  - {item}" for item in report_questions] if report_questions else [f"  - {display_states.get('report_questions') or '검증 질문을 다시 정해야 합니다.'}"]),
            "",
            "### 유지 계약",
        ]
    )
    if retained:
        for item in retained:
            lines.append(f"- {item.get('item') or '-'}")
            lines.append(f"  - 근거: {item.get('basis') or '-'}")
    else:
        lines.append(f"- {display_states.get('retained_contracts') or '유지 계약을 다시 정해야 합니다.'}")
    lines.extend(["", "### 분리 우선순위"])
    if priority_items:
        for item in priority_items:
            lines.extend(
                [
                    f"- {item.get('priority')}순위 {item.get('item') or item.get('title') or '-'}",
                    f"  - 이유: {item.get('reason') or '-'}",
                    f"  - 영향 범위: {item.get('impact_scope') or '-'}",
                    f"  - 선행 조건: {item.get('prerequisite') or '-'}",
                ]
            )
            if item.get("linked_rules"):
                lines.append(f"  - 관련 규칙: {', '.join(item.get('linked_rules') or [])}")
            if item.get("linked_contracts"):
                lines.append(f"  - 관련 계약: {', '.join(item.get('linked_contracts') or [])}")
    else:
        lines.append(f"- {display_states.get('priority_split') or '우선순위를 다시 정해야 합니다.'}")
    lines.extend(["", "### 확인 필요 항목"])
    if verification:
        for item in verification:
            lines.append(f"- {item.get('item') or '-'}")
            lines.append(f"  - 사유: {item.get('reason') or '-'}")
    else:
        lines.append(f"- {display_states.get('verification') or '확인 항목을 다시 정해야 합니다.'}")
    lines.extend(["", "### 설계 메모"])
    if design.get("rebuild_strategy"):
        lines.extend(f"- {item}" for item in (design.get("rebuild_strategy") or []))
    else:
        lines.append(f"- {display_states.get('rebuild_strategy') or '구조 전략을 다시 정해야 합니다.'}")
    for key, label in (("database", "데이터 계약"), ("backend", "API 및 정책"), ("frontend", "화면 구조")):
        values = layer.get(key) or []
        lines.append(f"#### {label}")
        lines.extend(f"- {item}" for item in values)
        if not values:
            lines.append("- 이 레이어 경계를 바로 고정하면 안 되므로 추가 근거가 먼저입니다.")
    lines.extend(["", "### 전환 초안"])
    draft_has_content = False
    for key in ("database", "backend", "frontend"):
        values = draft.get(key) or []
        if values:
            draft_has_content = True
            lines.append(f"#### {key}")
            lines.extend(f"- {item}" for item in values)
    if not draft_has_content:
        lines.append(f"- {display_states.get('transition_draft') or '전환 초안을 다시 정해야 합니다.'}")
    accounting = pkg.get("accounting") or {}
    if accounting:
        calc_status = accounting.get("calculation_status") or {}
        input_validation = accounting.get("input_validation") or {}
        analysis = accounting.get("accounting_analysis") or {}
        fx_calc = accounting.get("fx_calculation") or {}
        voucher_review = accounting.get("voucher_review") or {}
        blocking_issue = str(calc_status.get("blocking_issue") or calc_status.get("reason") or fx_calc.get("failure_reason") or "").strip()
        blocking_label = _accounting_reason_label(blocking_issue)
        lines.extend(
            [
                "",
                "### 회계 참고",
                f"- 요약: {accounting.get('summary_sentence') or '-'}",
                f"- 계산 가능: {'예' if calc_status.get('can_calculate') else '아니오'}",
                f"- 사유: {calc_status.get('reason') or calc_status.get('blocking_issue') or '-'}",
            ]
        )
        if blocking_issue:
            lines.append(f"- 차단 라벨: {blocking_label}입니다.")
        if input_validation.get("missing_required_inputs"):
            lines.append(f"- 누락 입력: {', '.join(input_validation.get('missing_required_inputs') or [])}")
        if analysis.get("candidate_methods"):
            lines.append(f"- 후보 방식: {', '.join(analysis.get('candidate_methods') or [])}")
        if analysis.get("recommended_method"):
            lines.append(f"- 추천 방식: {analysis.get('recommended_method')}")
        for item in analysis.get("reasons") or []:
            lines.append(f"- {item.get('message') or '-'}")
        if fx_calc.get("status"):
            lines.append(f"- 외화 계산 상태: {fx_calc.get('status')}")
        if fx_calc.get("failure_reason"):
            lines.append(f"- 외화 계산 실패 사유: {fx_calc.get('failure_reason')}")
        if fx_calc.get("realized_gain_loss_krw") is not None:
            lines.append(f"- 환차손익: {fx_calc.get('realized_gain_loss_krw'):,}원")
        for step in fx_calc.get("detail_steps") or []:
            lines.append(f"- {step.get('message') or '-'}")
        if voucher_review.get("status"):
            lines.append(f"- 전표 검토 상태: {voucher_review.get('status')}")
        if voucher_review.get("status") == "입력 부족":
            lines.append("- 차변/대변 균형: 검토 불가")
            lines.append("- 정책 일치: 검토 불가")
        else:
            if voucher_review.get("balance_ok") is not None:
                lines.append(f"- 차변/대변 균형: {'예' if voucher_review.get('balance_ok') else '아니오'}")
            if voucher_review.get("policy_consistent") is not None:
                lines.append(f"- 정책 일치: {'예' if voucher_review.get('policy_consistent') else '아니오'}")
        if voucher_review.get("failure_reason"):
            lines.append(f"- 전표 검토 실패 사유: {voucher_review.get('failure_reason')}")
        for item in voucher_review.get("review_points") or []:
            lines.append(f"- {item.get('message') or '-'}")
        for item in voucher_review.get("mismatches") or []:
            lines.append(f"- {item.get('message') or '-'}")
    lines.extend(
        [
            "",
            "### Provenance 및 입력 자산",
            f"- Run ID: {provenance.get('run_id') or '-'}",
            f"- 생성 기준 시각 (UTC): {provenance.get('generated_at') or '-'}",
            f"- Run 상태: {provenance.get('run_status') or '-'}",
            f"- 앱 버전: {provenance.get('app_version') or '-'}",
            f"- 모듈 버전: {provenance.get('module_version') or '-'}",
            f"- 템플릿 키: {provenance.get('template_key') or '-'}",
            f"- 범위 안내: {scope_notice.get('summary') or '-'}",
        ]
    )
    for item in pkg["appendix"].get("asset_manifest") or []:
        filename = item.get("name") or "-"
        size = item.get("size") or 0
        lines.append(f"- {filename} ({size} bytes)")
    return "\n".join(lines).strip() + "\n"


def _result_explanation_markdown(explanation: ResultExplanationResponse) -> str:
    return _render_result_explanation_markdown_impl(explanation)


async def _result_package_docx_response(
    project: ModernizationProject,
    pkg: dict[str, Any],
    *,
    surface_mode: str = "internal",
    internal_export_mode: str = "deck-only",
) -> FileResponse:
    output_path, download_name = await _generate_result_package_docx(
        project,
        pkg,
        surface_mode=surface_mode,
        internal_export_mode=internal_export_mode,
    )
    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name,
        headers={"Content-Disposition": _download_disposition(download_name, "project_result.docx")},
    )


async def _generate_result_package_docx(
    project: ModernizationProject,
    pkg: dict[str, Any],
    *,
    surface_mode: str = "internal",
    internal_export_mode: str = "deck-only",
) -> tuple[Path, str]:
    if not app_state.doc_service or not app_state.doc_service.is_available():
        raise HTTPException(status_code=503, detail="Document Service unavailable")

    normalized_surface_mode = normalize_surface_mode(surface_mode)
    export_review_artifacts = can_export_review_artifacts(policy_for_surface_mode(normalized_surface_mode).access_profile)
    suffix_name = "result.docx" if export_review_artifacts else "external_result.docx"
    download_name = _safe_download_name(project.project_name, suffix_name)
    title = f"{'결과 패키지' if export_review_artifacts else '구조 판단'} - {project.project_name}"
    markdown_content = _result_package_markdown(
        pkg,
        surface_mode=normalized_surface_mode,
        internal_export_mode=internal_export_mode,
    )
    result = await app_state.doc_service.generate(
        DocumentRequest(
            content=markdown_content,
            output_type=DocumentType.DOCX,
            title=title,
            filename=download_name,
            style_options={
                "font_name": "Malgun Gothic",
                "font_size": 11,
            },
        )
    )
    return Path(result.output_path).resolve(), download_name


async def _result_package_pptx_response(
    project: ModernizationProject,
    pkg: dict[str, Any],
    *,
    surface_mode: str = "internal",
    internal_export_mode: str = "deck-only",
) -> FileResponse:
    if not app_state.doc_service or not app_state.doc_service.is_available():
        raise HTTPException(status_code=503, detail="Document Service unavailable")

    normalized_surface_mode = normalize_surface_mode(surface_mode)
    export_review_artifacts = can_export_review_artifacts(policy_for_surface_mode(normalized_surface_mode).access_profile)
    suffix_name = "result.pptx" if export_review_artifacts else "external_result.pptx"
    download_name = _safe_download_name(project.project_name, suffix_name)
    title = f"{'결과 패키지' if export_review_artifacts else '구조 판단'} - {project.project_name}"
    slide_schema = _resolve_slide_schema(pkg, surface_mode=normalized_surface_mode)
    if not slide_schema:
        raise HTTPException(status_code=500, detail="Slide schema unavailable")
    result = await app_state.doc_service.generate(
        DocumentRequest(
            content="",
            output_type=DocumentType.PPTX,
            title=title,
            filename=download_name,
            payload=slide_schema,
            style_options={
                "renderer": "slide_schema",
            },
        )
    )
    return FileResponse(
        path=result.output_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=download_name,
        headers={"Content-Disposition": _download_disposition(download_name, "project_result.pptx")},
    )


def _project_result_archive_paths(project_id: str, run_id: str) -> dict[str, Path]:
    return _build_project_result_archive_paths_impl(
        archive_root=_PROJECT_RESULT_ARCHIVE_ROOT,
        project_id=project_id,
        run_id=run_id,
    )


async def _persist_project_result_archive(
    project: ModernizationProject,
    *,
    run_id: str,
    db: Session,
    assets: list[dict[str, Any]] | None = None,
    app_version: str | None = None,
    result_package: dict[str, Any] | None = None,
    docx_source_path: Path | None = None,
) -> dict[str, str]:
    return await _persist_project_result_archive_impl(
        project,
        run_id=run_id,
        db=db,
        archive_root=_PROJECT_RESULT_ARCHIVE_ROOT,
        logger=logger,
        get_run_snapshot_fn=get_run_snapshot,
        get_run_events_fn=get_run_events,
        extract_structured_result_fn=_extract_structured_result,
        build_assets_payload_fn=_build_assets_payload,
        build_result_package_fn=build_result_package,
        extract_polish_bundle_fn=_extract_polish_bundle,
        result_package_markdown_fn=_result_package_markdown,
        generate_result_package_docx_fn=_generate_result_package_docx,
        assets=assets,
        app_version=app_version,
        result_package=result_package,
        docx_source_path=docx_source_path,
    )


def _mark_run_failed(run_id: str, message: str, db: Session) -> None:
    run = db.query(AgentRun).filter(AgentRun.run_id == run_id).first()
    if not run:
        return
    run.status = "failed"
    run.summary = (message or "")[:4000]
    db.commit()


def _validate_asset_manifest(payload: ProjectStartRequest) -> None:
    if not payload.asset_manifest:
        raise HTTPException(status_code=400, detail="asset_manifest must contain at least one asset")
    temp_file_ids = [item.temp_file_id for item in payload.asset_manifest]
    if len(set(temp_file_ids)) != len(temp_file_ids):
        raise HTTPException(status_code=400, detail="Duplicate temp_file_id values are not allowed")


def _resolve_staged_resources(
    payload: ProjectStartRequest,
    user: User,
    db: Session,
) -> list[tuple[Any, TempResource]]:
    temp_file_ids = [item.temp_file_id for item in payload.asset_manifest]
    rows = db.query(TempResource).filter(TempResource.temp_file_id.in_(temp_file_ids)).all()
    row_map = {row.temp_file_id: row for row in rows if row.temp_file_id}
    missing_ids = [temp_file_id for temp_file_id in temp_file_ids if temp_file_id not in row_map]
    if missing_ids:
        raise HTTPException(status_code=400, detail=f"Unknown temp_file_id: {missing_ids[0]}")

    ordered: list[tuple[Any, TempResource]] = []
    for asset_item in payload.asset_manifest:
        row = row_map[asset_item.temp_file_id]
        if row.user_id != user.id:
            raise HTTPException(status_code=403, detail="다른 사용자의 업로드 자산은 프로젝트에 포함할 수 없습니다.")
        if row.temp_session_id != payload.upload_session_id:
            raise HTTPException(status_code=400, detail="asset_manifest temp_file_id does not belong to upload_session_id")
        if (row.stage_status or "staged") != "staged":
            raise HTTPException(status_code=400, detail="Only staged uploads can be promoted into a project")
        if not row.file_path or not row.extracted_relative_path:
            raise HTTPException(status_code=400, detail="Staged upload is incomplete")
        ordered.append((asset_item, row))
    return ordered


def _resolve_preview_resources(
    *,
    upload_session_id: str,
    asset_manifest: list[ProjectAssetItem],
    user: User | None,
    db: Session,
) -> list[tuple[ProjectAssetItem, TempResource]]:
    if not asset_manifest:
        raise HTTPException(status_code=400, detail="asset_manifest must contain at least one asset")
    temp_file_ids = [item.temp_file_id for item in asset_manifest]
    if len(set(temp_file_ids)) != len(temp_file_ids):
        raise HTTPException(status_code=400, detail="Duplicate temp_file_id values are not allowed")

    rows = db.query(TempResource).filter(TempResource.temp_file_id.in_(temp_file_ids)).all()
    row_map = {row.temp_file_id: row for row in rows if row.temp_file_id}
    missing_ids = [temp_file_id for temp_file_id in temp_file_ids if temp_file_id not in row_map]
    if missing_ids:
        raise HTTPException(status_code=400, detail=f"Unknown temp_file_id: {missing_ids[0]}")

    ordered: list[tuple[ProjectAssetItem, TempResource]] = []
    for asset_item in asset_manifest:
        row = row_map[asset_item.temp_file_id]
        if row.temp_session_id != upload_session_id:
            raise HTTPException(status_code=400, detail="asset_manifest temp_file_id does not belong to upload_session_id")
        if row.user_id is not None and (user is None or row.user_id != user.id):
            raise HTTPException(status_code=403, detail="다른 사용자의 업로드 자산은 미리보기할 수 없습니다.")
        if (row.stage_status or "staged") not in {"staged", "promoted"}:
            raise HTTPException(status_code=400, detail="업로드 자산이 아직 미리보기 가능한 상태가 아닙니다.")
        if not row.file_path or not row.extracted_relative_path:
            raise HTTPException(status_code=400, detail="Staged upload is incomplete")
        ordered.append((asset_item, row))
    return ordered


def _build_preview_review_assets(
    *,
    upload_session_id: str,
    asset_manifest: list[ProjectAssetItem],
    user: User | None,
    db: Session,
) -> list[AnonymizationAsset]:
    assets: list[AnonymizationAsset] = []
    for asset_item, row in _resolve_preview_resources(
        upload_session_id=upload_session_id,
        asset_manifest=asset_manifest,
        user=user,
        db=db,
    ):
        try:
            original_path = resolve_temp_upload_path(row.file_path or "")
            extracted_text = read_text(row.extracted_relative_path or "", project_asset=False)
            original_bytes = original_path.read_bytes()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="업로드 자산 파일을 불러올 수 없습니다.") from exc
        assets.append(
            AnonymizationAsset(
                asset_id=row.temp_file_id or asset_item.temp_file_id,
                name=row.original_filename or asset_item.name,
                temp_file_id=row.temp_file_id or asset_item.temp_file_id,
                size=row.file_size or asset_item.size or 0,
                kind_hint=asset_item.category_hint or "",
                content_text=extracted_text,
                original_bytes=original_bytes,
            )
        )
    return assets


@router.get("/projects/create", include_in_schema=False)
async def project_create_view() -> FileResponse:
    return FileResponse(_static_file("projects_create.html"))


@router.post("/projects/anonymization-review", response_model=ProjectAnonymizationPreviewResponse)
async def project_anonymization_review_preview(
    payload: ProjectAnonymizationPreviewRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> ProjectAnonymizationPreviewResponse:
    assets = _build_preview_review_assets(
        upload_session_id=payload.upload_session_id,
        asset_manifest=payload.asset_manifest,
        user=user,
        db=db,
    )
    result = AnonymizationService().run_anonymization_pipeline(
        AnonymizationRunRequest(
            project_id=f"preview_{payload.upload_session_id}",
            upload_session_id=payload.upload_session_id,
            masking_level=MaskingLevel.FULL,
            assets=assets,
        )
    )
    review_report = result.review_report
    analysis_context = AnalysisContextBuilder().build(
        project_id=f"preview_{payload.upload_session_id}",
        run_id="preview",
        safe_bundle=result.safe_bundle,
        goal=str(payload.goal or "").strip(),
        constraints=list(payload.constraints or []),
    )
    question_guard = _SOURCE_QUESTION_GUARD.evaluate(
        analysis_context=analysis_context,
        raw_goal=str(payload.goal or "").strip(),
        raw_constraints=list(payload.constraints or []),
    )
    label_less_risk_count = len(review_report.label_less_risks) if review_report else 0
    label_less_warning_count = len(review_report.label_less_warnings) if review_report else 0
    structure_checks = review_report.structure_checks if review_report else []
    structure_issue_count = sum(1 for item in structure_checks if item.severity != "ok")
    structure_risk_detected = any(item.severity == "risk" for item in structure_checks)
    high_risk_detected = label_less_risk_count > 0 or structure_risk_detected
    return ProjectAnonymizationPreviewResponse(
        review_report=review_report,
        display_review_report=build_display_review_report(review_report),
        high_risk_detected=high_risk_detected,
        label_less_risk_count=label_less_risk_count,
        label_less_warning_count=label_less_warning_count,
        structure_issue_count=structure_issue_count,
        structure_risk_detected=structure_risk_detected,
        source_question_candidates=question_guard.source_question_candidates,
        blocked_user_questions=question_guard.blocked_user_questions,
        review_user_questions=question_guard.review_user_questions,
        question_guard_summary=question_guard.question_guard_summary,
    )


@router.get("/projects", include_in_schema=False)
async def projects_view_or_list(
    request: Request,
    format: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> Any:
    if _wants_html(request, format):
        return FileResponse(_static_file("projects_create.html"))
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    projects = (
        db.query(ModernizationProject)
        .filter(ModernizationProject.user_id == user.id)
        .order_by(ModernizationProject.updated_at.desc(), ModernizationProject.created_at.desc())
        .all()
    )
    if user.role == UserRole.ADMIN.value:
        visible_projects = projects
    else:
        visible_projects = [project for project in projects if not _is_hidden_test_project(project)]
    items = []
    for project in visible_projects:
        snapshot = get_run_snapshot(project.run_id, db=db)
        _sync_project_status(project, snapshot, db)
        items.append(
            {
                "id": project.id,
                "project_name": project.project_name,
                "client_name": project.client_name,
                "template_key": project.template_key,
                "status": project.status,
                "created_at": project.created_at.isoformat() if project.created_at else None,
                "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                "asset_manifest": _parse_json_list(project.asset_manifest_json),
            }
        )
    return {
        "projects": items,
        "recent_entries": _build_recent_project_entries(visible_projects, db),
    }


@router.post("/projects", response_model=ProjectStartResponse)
async def create_project(
    payload: ProjectStartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectStartResponse:
    _validate_asset_manifest(payload)
    staged_resources = _resolve_staged_resources(payload, user, db)
    create_warnings = _detect_domain_mismatch_warning(
        project_name=payload.project_name,
        goal=payload.goal,
        constraints=payload.constraints,
        asset_names=[item.name for item in payload.asset_manifest],
        asset_texts=[
            read_text(row.extracted_relative_path or "", project_asset=False)[:1200]
            for _, row in staged_resources
            if row.extracted_relative_path
        ],
    )
    run_id, session_id = create_project_wrapped_run(db=db, user=user)
    project_id = f"proj_{uuid.uuid4().hex[:12]}"
    copied_asset_ids: list[str] = []

    try:
        project = ModernizationProject(
            id=project_id,
            user_id=user.id,
            session_id=session_id,
            run_id=run_id,
            project_name=payload.project_name,
            client_name=payload.client_name,
            goal_text=payload.goal,
            template_key=payload.template_key,
            template_mode="recommended",
            constraints_json=json.dumps(payload.constraints, ensure_ascii=False),
            upload_session_id=payload.upload_session_id,
            asset_manifest_json=_serialize_asset_manifest([item.model_dump() for item in payload.asset_manifest]),
            status="pending",
        )
        db.add(project)

        promoted_assets: list[ProjectAsset] = []
        for asset_item, temp_resource in staged_resources:
            asset_id = make_project_asset_id()
            copied_paths = promote_staged_asset(
                project_id=project_id,
                asset_id=asset_id,
                staged_file_path=temp_resource.file_path or "",
                staged_extracted_path=temp_resource.extracted_relative_path or "",
            )
            copied_asset_ids.append(asset_id)
            extracted_text = read_text(copied_paths["extracted_relative_path"], project_asset=True)
            promoted_assets.append(
                ProjectAsset(
                    id=asset_id,
                    project_id=project_id,
                    source_temp_session_id=temp_resource.temp_session_id,
                    source_temp_file_id=temp_resource.temp_file_id or asset_item.temp_file_id,
                    original_filename=temp_resource.original_filename or asset_item.name,
                    stored_relative_path=copied_paths["stored_relative_path"],
                    extracted_relative_path=copied_paths["extracted_relative_path"],
                    file_size=temp_resource.file_size,
                    content_type=temp_resource.content_type or "",
                    category_hint=asset_item.category_hint or "",
                    extracted_chars=len(extracted_text),
                )
            )
            temp_resource.stage_status = "promoted"
            temp_resource.promoted_to_project_id = project_id
            temp_resource.status = "READY"

        for project_asset in promoted_assets:
            db.add(project_asset)
        db.add(
            _create_history_row(
                project_id=project_id,
                run_id=run_id,
                sequence_no=1,
                trigger_kind="initial",
                asset_manifest_json=_serialize_asset_manifest([item.model_dump() for item in payload.asset_manifest]),
            )
        )
        db.commit()
        db.refresh(project)
    except HTTPException:
        db.rollback()
        for asset_id in copied_asset_ids:
            cleanup_project_asset_dir(project_id, asset_id)
        _mark_run_failed(run_id, "Project asset promotion failed", db)
        raise
    except Exception as exc:
        db.rollback()
        for asset_id in copied_asset_ids:
            cleanup_project_asset_dir(project_id, asset_id)
        _mark_run_failed(run_id, f"Project asset promotion failed: {str(exc)[:300]}", db)
        raise HTTPException(status_code=500, detail="프로젝트 자산 승격에 실패했습니다.")

    status = "pending"
    try:
        project = db.query(ModernizationProject).filter(ModernizationProject.id == project_id).first()
        ordered_assets = _ordered_project_assets(project, db) if project else []
        context_parts = [
            (asset.original_filename, read_text(asset.extracted_relative_path, project_asset=True))
            for asset in ordered_assets
        ]
        app_state.TEMP_CONTEXT_STORE[payload.upload_session_id] = build_temp_context(context_parts)
        # Project creation stays permissive even when the preview reported high
        # risk; downstream analysis receives the marker-masked safe bundle.
        safe_bundle = _build_safe_bundle_for_project(project, db) if project else None
        resolved_goal = resolve_project_goal(
            inline_goal=payload.goal,
            safe_bundle=safe_bundle,
            project_name=payload.project_name,
            client_name=payload.client_name,
        )
        if project is not None:
            project.goal_text = resolved_goal
            db.add(project)
            db.commit()
            db.refresh(project)
        analysis_context = (
            _build_and_store_analysis_context(
                project,
                run_id=run_id,
                safe_bundle=safe_bundle,
                goal=resolved_goal,
                constraints=payload.constraints,
                db=db,
            )
            if project is not None and safe_bundle is not None
            else None
        )
        if analysis_context is not None:
            create_warnings = list(dict.fromkeys(create_warnings + list(analysis_context.trust.warnings or [])))
        start_project_wrapped_run(
            run_id=run_id,
            session_id=session_id,
            project_name=payload.project_name,
            client_name=payload.client_name,
            goal=resolved_goal,
            upload_session_id=payload.upload_session_id,
            constraints=payload.constraints,
            asset_manifest=payload.asset_manifest,
            safe_bundle=safe_bundle,
            analysis_context=analysis_context,
        )
    except Exception as exc:
        project = db.query(ModernizationProject).filter(ModernizationProject.id == project_id).first()
        if project:
            project.status = "failed"
            db.commit()
        _mark_run_failed(run_id, f"Project launch failed: {str(exc)[:300]}", db)
        status = "failed"

    return ProjectStartResponse(
        project_id=project_id,
        run_id=run_id,
        session_id=session_id,
        status=status,
        warnings=create_warnings,
    )


@router.post("/projects/{project_id}/reanalysis", response_model=ProjectReanalysisResponse)
async def reanalyze_project(
    project_id: str,
    payload: ProjectReanalysisRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectReanalysisResponse:
    project = _project_or_404(project_id, user, db)
    _ensure_initial_history(project, db)
    try:
        await _persist_project_result_archive(project, run_id=project.run_id, db=db)
    except Exception as exc:
        logger.warning(
            "[Projects] Failed to archive previous run before reanalysis for project=%s run=%s: %s",
            project.id,
            project.run_id,
            exc,
        )
    staged_resources = _validate_reanalysis_assets(project, payload, user, db)

    promoted_asset_ids: list[str] = []
    promoted_count = 0
    updated_manifest_json = project.asset_manifest_json or "[]"

    try:
        if staged_resources:
            current_manifest = _parse_json_list(project.asset_manifest_json)
            appended_manifest = current_manifest + _asset_manifest_from_models(payload.new_asset_manifest)
            for asset_item, temp_resource in staged_resources:
                asset_id = make_project_asset_id()
                copied_paths = promote_staged_asset(
                    project_id=project.id,
                    asset_id=asset_id,
                    staged_file_path=temp_resource.file_path or "",
                    staged_extracted_path=temp_resource.extracted_relative_path or "",
                )
                promoted_asset_ids.append(asset_id)
                extracted_text = read_text(copied_paths["extracted_relative_path"], project_asset=True)
                db.add(
                    ProjectAsset(
                        id=asset_id,
                        project_id=project.id,
                        source_temp_session_id=temp_resource.temp_session_id,
                        source_temp_file_id=temp_resource.temp_file_id or asset_item.temp_file_id,
                        original_filename=temp_resource.original_filename or asset_item.name,
                        stored_relative_path=copied_paths["stored_relative_path"],
                        extracted_relative_path=copied_paths["extracted_relative_path"],
                        file_size=temp_resource.file_size,
                        content_type=temp_resource.content_type or "",
                        category_hint=asset_item.category_hint or "",
                        extracted_chars=len(extracted_text),
                    )
                )
                temp_resource.stage_status = "promoted"
                temp_resource.promoted_to_project_id = project.id
                temp_resource.status = "READY"
                promoted_count += 1
            updated_manifest_json = _serialize_asset_manifest(appended_manifest)
            project.asset_manifest_json = updated_manifest_json
            db.commit()
            db.refresh(project)
    except HTTPException:
        db.rollback()
        for asset_id in promoted_asset_ids:
            cleanup_project_asset_dir(project.id, asset_id)
        raise
    except Exception as exc:
        db.rollback()
        for asset_id in promoted_asset_ids:
            cleanup_project_asset_dir(project.id, asset_id)
        raise HTTPException(status_code=500, detail=f"재분석 자산 준비에 실패했습니다: {str(exc)[:200]}")

    _rebuild_project_temp_context(project, db)

    try:
        new_run_id, new_session_id = create_project_wrapped_run(db=db, user=user)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"재분석 run 생성에 실패했습니다: {str(exc)[:200]}")

    sequence_no = _history_sequence_next(project.id, db)
    project.run_id = new_run_id
    project.session_id = new_session_id
    project.status = "pending"
    db.add(
        _create_history_row(
            project_id=project.id,
            run_id=new_run_id,
            sequence_no=sequence_no,
            trigger_kind="reanalysis",
            asset_manifest_json=project.asset_manifest_json or "[]",
        )
    )
    db.commit()
    db.refresh(project)

    status = "pending"
    try:
        safe_bundle = _build_safe_bundle_for_project(project, db)
        project_goal = _resolved_project_goal(project, safe_bundle=safe_bundle, db=db)
        project_constraints = _parse_json_list(project.constraints_json)
        analysis_context = _build_and_store_analysis_context(
            project,
            run_id=new_run_id,
            safe_bundle=safe_bundle,
            goal=project_goal,
            constraints=project_constraints,
            db=db,
        )
        start_project_wrapped_run(
            run_id=new_run_id,
            session_id=new_session_id,
            project_name=project.project_name,
            client_name=project.client_name,
            goal=project_goal,
            upload_session_id=project.upload_session_id,
            constraints=project_constraints,
            asset_manifest=[ProjectAssetItem.model_validate(item) for item in _parse_json_list(project.asset_manifest_json)],
            safe_bundle=safe_bundle,
            analysis_context=analysis_context,
        )
    except Exception as exc:
        project = db.query(ModernizationProject).filter(ModernizationProject.id == project.id).first()
        if project:
            project.status = "failed"
            db.commit()
        _mark_run_failed(new_run_id, f"Project reanalysis launch failed: {str(exc)[:300]}", db)
        status = "failed"

    latest_asset_count = len(_asset_manifest_from_project_assets(project, db))
    return ProjectReanalysisResponse(
        project_id=project.id,
        run_id=new_run_id,
        session_id=new_session_id,
        status=status,
        promoted_asset_count=promoted_count,
        latest_asset_count=latest_asset_count,
        warnings=_project_domain_warnings(project, db),
    )


@router.post("/projects/{project_id}/run", response_model=ProjectReanalysisResponse)
async def run_project_analysis(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectReanalysisResponse:
    project = _project_or_404(project_id, user, db)
    _ensure_initial_history(project, db)
    try:
        await _persist_project_result_archive(project, run_id=project.run_id, db=db)
    except Exception as exc:
        logger.warning(
            "[Projects] Failed to archive previous run before manual rerun for project=%s run=%s: %s",
            project.id,
            project.run_id,
            exc,
        )
    _rebuild_project_temp_context(project, db)

    new_run_id, new_session_id = create_project_wrapped_run(db=db, user=user)
    sequence_no = _history_sequence_next(project.id, db)
    project.run_id = new_run_id
    project.session_id = new_session_id
    project.status = "pending"
    db.add(
        _create_history_row(
            project_id=project.id,
            run_id=new_run_id,
            sequence_no=sequence_no,
            trigger_kind="manual_run",
            asset_manifest_json=project.asset_manifest_json or "[]",
        )
    )
    db.commit()
    db.refresh(project)

    status = "pending"
    try:
        safe_bundle = _build_safe_bundle_for_project(project, db)
        project_goal = _resolved_project_goal(project, safe_bundle=safe_bundle, db=db)
        project_constraints = _parse_json_list(project.constraints_json)
        analysis_context = _build_and_store_analysis_context(
            project,
            run_id=new_run_id,
            safe_bundle=safe_bundle,
            goal=project_goal,
            constraints=project_constraints,
            db=db,
        )
        start_project_wrapped_run(
            run_id=new_run_id,
            session_id=new_session_id,
            project_name=project.project_name,
            client_name=project.client_name,
            goal=project_goal,
            upload_session_id=project.upload_session_id,
            constraints=project_constraints,
            asset_manifest=[ProjectAssetItem.model_validate(item) for item in _parse_json_list(project.asset_manifest_json)],
            safe_bundle=safe_bundle,
            analysis_context=analysis_context,
        )
    except Exception as exc:
        project = db.query(ModernizationProject).filter(ModernizationProject.id == project.id).first()
        if project:
            project.status = "failed"
            db.commit()
        _mark_run_failed(new_run_id, f"Project run launch failed: {str(exc)[:300]}", db)
        status = "failed"

    latest_asset_count = len(_asset_manifest_from_project_assets(project, db))
    return ProjectReanalysisResponse(
        project_id=project.id,
        run_id=new_run_id,
        session_id=new_session_id,
        status=status,
        promoted_asset_count=0,
        latest_asset_count=latest_asset_count,
        warnings=_project_domain_warnings(project, db),
    )


@router.get("/projects/{project_id}", include_in_schema=False)
async def project_detail(
    project_id: str,
    request: Request,
    format: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> Any:
    if _wants_html(request, format):
        return FileResponse(_static_file("user_console.html"))
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    project = _project_or_404(project_id, user, db)
    _ensure_initial_history(project, db)
    snapshot = get_run_snapshot(project.run_id, db=db)
    _sync_project_status(project, snapshot, db)
    events = get_run_events(project.run_id, db=db)
    structured = _extract_structured_result(events)
    insights = _extract_project_insights(events, structured)
    assets = _build_assets_payload(project, db)
    return {
        "project": {
            "id": project.id,
            "run_id": project.run_id,
            "project_name": project.project_name,
            "client_name": project.client_name,
            "goal": _project_text(project, "goal_text"),
            "template_key": project.template_key,
            "constraints": _parse_json_list(project.constraints_json),
            "asset_manifest": _parse_json_list(project.asset_manifest_json),
            "status": project.status,
            "upload_session_id": project.upload_session_id,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        },
        "assets": assets,
        "run_history": _build_run_history_payload(project, db),
        "snapshot": snapshot,
        "insights": insights,
        "warnings": _project_domain_warnings(project, db),
        "missing_context_details": _missing_context_blocks(structured),
        "structured_result": structured.model_dump() if structured else None,
    }


@router.get("/projects/{project_id}/result", include_in_schema=False)
async def project_result(
    project_id: str,
    request: Request,
    format: str | None = Query(None),
    surface_mode: str = Query("internal", pattern="^(internal|external)$"),
    internal_export_mode: str = Query("deck-only", pattern="^(deck-only|full)$"),
    run_id: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> Any:
    if _wants_html(request, format):
        return FileResponse(_static_file("project_result.html"))
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    project = _project_or_404(project_id, user, db)
    app_version = getattr(request.app, "version", None)
    context = _load_project_result_context(project, db=db, app_version=app_version, run_id=run_id)
    full_result_package = context["result_package"]
    target_run_id = str(context["run_id"])
    normalized_surface_mode = normalize_surface_mode(surface_mode)
    result_package = _surface_filtered_result_package(full_result_package, surface_mode=normalized_surface_mode)
    if normalized_surface_mode == "internal":
        if format == "docx":
            output_path, download_name = await _generate_result_package_docx(
                project,
                result_package,
                surface_mode=normalized_surface_mode,
                internal_export_mode=internal_export_mode,
            )
            try:
                await _persist_project_result_archive(
                    project,
                    run_id=target_run_id,
                    db=db,
                    assets=context["assets"],
                    app_version=app_version,
                    result_package=full_result_package,
                    docx_source_path=output_path,
                )
            except Exception as exc:
                logger.warning(
                    "[Projects] Failed to archive current run during DOCX export for project=%s run=%s: %s",
                    project.id,
                    target_run_id,
                    exc,
                )
            return FileResponse(
                path=output_path,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=download_name,
                headers={"Content-Disposition": _download_disposition(download_name, "project_result.docx")},
            )
        try:
            await _persist_project_result_archive(
                project,
                run_id=target_run_id,
                db=db,
                assets=context["assets"],
                app_version=app_version,
                result_package=full_result_package,
            )
        except Exception as exc:
            logger.warning(
                "[Projects] Failed to archive current run on result view for project=%s run=%s: %s",
                project.id,
                target_run_id,
                exc,
            )
    if format == "md":
        download_name = _safe_download_name(project.project_name, "external_result.md" if normalized_surface_mode == "external" else "result.md")
        return Response(
            content=_result_package_markdown(
                result_package,
                surface_mode=normalized_surface_mode,
                internal_export_mode=internal_export_mode,
            ),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": _download_disposition(download_name, "project_result.md")
            },
        )
    if format == "docx":
        return await _result_package_docx_response(
            project,
            result_package,
            surface_mode=normalized_surface_mode,
            internal_export_mode=internal_export_mode,
        )
    if format == "pptx":
        return await _result_package_pptx_response(
            project,
            result_package,
            surface_mode=normalized_surface_mode,
            internal_export_mode=internal_export_mode,
        )
    if format == "json":
        return result_package
    return result_package


@router.get("/projects/{project_id}/result/explanation", response_model=ResultExplanationResponse)
async def project_result_explanation(
    project_id: str,
    request: Request,
    audience: str = Query("manager", pattern="^(developer|manager|client)$"),
    surface_mode: str = Query("internal", pattern="^(internal|external)$"),
    run_id: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> ResultExplanationResponse:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    project = _project_or_404(project_id, user, db)
    context = _load_project_result_context(project, db=db, app_version=getattr(request.app, "version", None), run_id=run_id)
    return _present_project_result_impl(
        project_id=project.id,
        result_package=context["result_package"],
        audience=audience,
        surface_mode=surface_mode,
    )


@router.post("/projects/{project_id}/result/qa", response_model=ResultQAResponse)
async def project_result_qa(
    project_id: str,
    payload: ResultQARequest,
    request: Request,
    run_id: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> ResultQAResponse:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    project = _project_or_404(project_id, user, db)
    context = _load_project_result_context(project, db=db, app_version=getattr(request.app, "version", None), run_id=run_id)
    return await _answer_project_result_question_impl(
        project_id=project.id,
        result_package=context["result_package"],
        question=payload.question,
        audience=payload.audience,
        llm_service=getattr(app_state, "llm_service", None),
    )


@router.get("/projects/{project_id}/assets/{asset_id}/download")
async def download_project_asset(
    project_id: str,
    asset_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    project = _project_or_404(project_id, user, db)
    asset = (
        db.query(ProjectAsset)
        .filter(ProjectAsset.project_id == project.id, ProjectAsset.id == asset_id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Project asset not found")
    try:
        file_path = resolve_project_asset_path(asset.stored_relative_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Project asset file not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Project asset file not found")
    media_type = (asset.content_type or "").strip() or "application/octet-stream"
    return FileResponse(str(file_path), media_type=media_type, filename=asset.original_filename)
