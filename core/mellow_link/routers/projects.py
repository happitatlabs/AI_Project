from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from mellow_link import app_state
from mellow_link.infra import (
    AgentRun,
    ModernizationProject,
    ProjectAsset,
    ProjectRunHistory,
    TempResource,
    User,
    get_current_user,
    get_current_user_optional,
    get_db,
)
from mellow_link.infra.run_events import get_run_events, get_run_snapshot
from mellow_link.modules.rebuild_assistant.api import create_project_wrapped_run, start_project_wrapped_run
from mellow_link.modules.rebuild_assistant.manifest import MANIFEST as REBUILD_ASSISTANT_MANIFEST, MODULE_VERSION
from mellow_link.modules.rebuild_assistant.schemas import (
    ProjectAssetItem,
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
from mellow_link.services.anonymization import AnonymizationAsset, AnonymizationRunRequest, AnonymizationService, MaskingLevel
from mellow_link.services.project_assets import (
    build_temp_context,
    cleanup_project_asset_dir,
    make_project_asset_id,
    promote_staged_asset,
    read_text,
    resolve_project_asset_path,
)
from mellow_link.services.refactoring_support_engine import ExplanationPresenter, ResultQuestionAnsweringService
from mellow_link.services.refactoring_support_engine.surface_access import (
    can_export_review_artifacts,
    capabilities_dict,
    filter_decision_governance_for_access,
    filter_review_diff_for_access,
    normalize_surface_mode,
    policy_for_surface_mode,
)
from mellow_link.services.scope_notice import PROJECT_SCOPE_NOTICE

router = APIRouter(tags=["Projects"])


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
    return filtered


def _project_status_from_run(snapshot: dict[str, Any] | None) -> str:
    run_status = ((snapshot or {}).get("status") or "").strip().lower()
    if run_status == "completed":
        return "completed"
    if run_status == "failed":
        return "failed"
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
        if not rules:
            if structured.extracted_rules.status_permissions.entities:
                rules = [f"권한/상태 규칙 엔티티: {', '.join(structured.extracted_rules.status_permissions.entities)}"]
            elif structured.extracted_rules.search_filters.entities:
                rules = [f"조회 규칙 엔티티: {', '.join(structured.extracted_rules.search_filters.entities)}"]
            elif structured.extracted_rules.save_validation.entities:
                rules = [f"저장 검증 엔티티: {', '.join(structured.extracted_rules.save_validation.entities)}"]
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


def _ordered_project_assets(project: ModernizationProject, db: Session) -> list[ProjectAsset]:
    asset_rows = _project_assets_rows(project.id, db)
    if not asset_rows:
        return []

    manifest = _parse_json_list(project.asset_manifest_json)
    manifest_order = {
        str(item.get("temp_file_id") or ""): index
        for index, item in enumerate(manifest)
        if str(item.get("temp_file_id") or "").strip()
    }
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


def _build_assets_payload(project: ModernizationProject, db: Session) -> list[dict[str, Any]]:
    asset_rows = _ordered_project_assets(project, db)
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
        return enriched_assets

    fallback = []
    for item in _parse_json_list(project.asset_manifest_json):
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
    constraints: list[str],
    asset_names: list[str],
    asset_texts: list[str],
) -> list[str]:
    input_text = " ".join([project_name, *constraints])
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
        constraints=_parse_json_list(project.constraints_json),
        asset_names=asset_names,
        asset_texts=asset_texts,
    )


def _history_sequence_next(project_id: str, db: Session) -> int:
    rows = _project_history_rows(project_id, db)
    if not rows:
        return 1
    return max(int(row.sequence_no or 0) for row in rows) + 1


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
            }
        )
    return payload


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
    return AnonymizationService().run_anonymization_pipeline(request).safe_bundle


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
        or _normalize_utc_iso(project.created_at)
    )
    return {
        "run_id": snapshot.get("run_id") or project.run_id,
        "module_id": snapshot.get("module_id") or REBUILD_ASSISTANT_MANIFEST.module_id,
        "run_kind": snapshot.get("run_kind") or REBUILD_ASSISTANT_MANIFEST.run_kind,
        "generated_at": generated_at,
        "app_version": (app_version or "").strip() or "unknown",
        "module_version": MODULE_VERSION,
        "template_key": project.template_key,
        "run_status": snapshot.get("status") or project.status,
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
    return _humanize_accounting_reason(text).rstrip(".")


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
    decision_items: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    recommended_option: dict[str, Any] | None,
    accounting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing_context_details = list(diagnosis.get("missing_context_details") or [])
    key_risks = _trim_items(list(diagnosis.get("risks") or []))[:3]
    summary_lines = _trim_items(executive_summary_v2)[:4]
    decision_lines = _trim_items(
        [str(item.get("statement") or "").strip() for item in (decision_items or []) if str(item.get("statement") or "").strip()]
    )[:3]
    modernization_direction = _trim_items(recommended_directions or summary_lines)[:3]
    recommended_name = str((recommended_option or {}).get("name") or "").strip()
    has_core = bool(core_conclusion) or bool(summary_lines)
    has_direction = bool(decision_lines)

    if has_core or has_direction:
        state = "ready"
    elif missing_context_details:
        state = "partial"
    else:
        state = "pending"

    if core_conclusion:
        core_message = core_conclusion
    elif state == "partial":
        core_message = "현재까지의 분석 결과를 기반으로 한 초안입니다."
    elif state == "pending":
        core_message = "분석 결과를 생성 중입니다."
    else:
        core_message = "결과를 요약할 수 있는 데이터가 아직 충분하지 않습니다."

    return {
        "title": "Executive Summary",
        "state": state,
        "core_message": core_message,
        "summary_lines": summary_lines,
        "modernization_direction": modernization_direction,
        "decision_focus": decision_lines,
        "recommended_option": recommended_name,
        "key_risks": key_risks[:3],
        "next_steps": _build_executive_next_steps(
            missing_context_details=missing_context_details,
            recommended_directions=decision_lines,
            accounting=accounting,
        ),
    }


def _sanitize_user_value(value: Any) -> Any:
    if isinstance(value, str):
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
        return [_sanitize_user_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_user_value(item) for key, item in value.items()}
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


def build_result_package(
    project: ModernizationProject,
    snapshot: dict[str, Any] | None,
    result: StructuredRebuildResult | None,
    *,
    assets: list[dict[str, Any]],
    polish_bundle: dict[str, Any] | None = None,
    app_version: str | None = None,
) -> dict[str, Any]:
    run_state = _project_status_from_run(snapshot)
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
        "project_name": project.project_name,
        "client_name": project.client_name,
        "template_key": project.template_key,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "run_status": (snapshot or {}).get("status") or project.status,
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
    accounting = None
    if result and isinstance(result.extensions, dict):
        accounting_block = result.extensions.get("accounting")
        if isinstance(accounting_block, dict):
            accounting = _build_accounting_package_view(accounting_block)
    surface_extensions = _surface_extensions(result)
    authoritative_payload = {
        "structure_snapshot": deepcopy(result.structure_snapshot) if result else {},
        "diagnosis_report": deepcopy(result.diagnosis_report) if result else {},
        "decision_summary": deepcopy(result.decision_summary) if result else {},
        "improvement_plan_bundle": deepcopy(result.improvement_plan_bundle) if result else {},
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
        decision_items=decision_items,
        diagnosis=diagnosis,
        recommended_option=recommended_option,
        accounting=accounting,
    )
    return _sanitize_user_value({
        "project": {
            "id": project.id,
            "project_name": project.project_name,
            "client_name": project.client_name,
            "template_key": project.template_key,
            "status": project.status,
        },
        "assets": assets,
        "provenance": provenance,
        "executive_summary": executive_summary,
        "primary_judgment": primary_judgment,
        "template_judgment": template_judgment,
        "structural_judgment": structural_judgment,
        "narrative_axis": narrative_axis,
        "feature_signal_mode": (result.feature_signal_mode if result else "").strip(),
        "report_purpose": (result.report_purpose if result else "").strip(),
        "report_scope": list(result.report_scope) if result else [],
        "report_questions": list(result.report_questions) if result else [],
        "executive_summary_v2": executive_summary_v2,
        "scope_notice": scope_notice,
        "core_conclusion": core_conclusion,
        "core_business_rules": list(result.core_business_rules) if result else [],
        "grounded_business_rules": grounded_business_rules,
        "decision_items": decision_items,
        "retained_contracts": retained_contracts,
        "priority_split_items": priority_split_items,
        "verification_checkpoints": verification_checkpoints,
        "design_options": design_options,
        "recommended_option": recommended_option,
        "execution_plan": execution_plan,
        "recommended_directions": recommended_directions,
        "accounting": accounting,
        "extensions": surface_extensions,
        "authoritative_payload": authoritative_payload,
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


def _load_project_result_context(
    project: ModernizationProject,
    *,
    db: Session,
    app_version: str | None = None,
) -> dict[str, Any]:
    snapshot = get_run_snapshot(project.run_id, db=db)
    _sync_project_status(project, snapshot, db)
    events = get_run_events(project.run_id, db=db)
    structured = _extract_structured_result(events)
    polish_bundle = _extract_polish_bundle(events, structured)
    assets = _build_assets_payload(project, db)
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
    return mapping.get(evidence_kind, f"제공 자산에서 '{rule_title}' 관련 근거가 확인되었습니다.")


def _translate_condition_excerpt(rule_title: str, excerpt: str) -> str:
    text = (excerpt or "").strip()
    lowered = text.lower()
    if not text:
        return ""

    if "지점장 300만원 한도" in rule_title and ("3000000" in lowered or "branch_manager" in lowered or "지점장" in lowered):
        return "청구 금액이 300만원 이상이면 지점장 권한으로는 처리할 수 없도록 제한하는 조건이 확인되었습니다."
    if "대리점 고액 주문 본사 전용" in rule_title and any(token in lowered for token in ("agency", "hq", "5000000", "대리점", "본사")):
        return "대리점 채널의 고액 주문은 본사 승인 조건을 충족해야 처리되도록 제한하는 조건이 확인되었습니다."
    if "수출 주문 고액건 REVIEW_REQUIRED" in rule_title and any(token in lowered for token in ("export", "7000000", "수출")):
        return "수출 주문은 고액 조건에 해당하면 REVIEW_REQUIRED 상태로 전이되도록 설정한 조건이 확인되었습니다."
    if "fraud" in lowered and "hq_reviewer" in lowered:
        return "사고 유형이 FRAUD이면 HQ_REVIEWER 권한에서만 처리되도록 제한하는 조건이 확인되었습니다."
    if "dept_code" in lowered and "claim_audit" in lowered and "!=" in lowered:
        return "CLAIM_AUDIT 부서가 아니면 고액 청구를 처리할 수 없도록 제한하는 조건이 확인되었습니다."
    if ("3000000" in lowered or "300만원" in lowered) and ("branch_manager" in lowered or "지점장" in lowered):
        return "청구 금액이 300만원 이상이면 지점장 권한으로는 처리할 수 없도록 제한하는 조건이 확인되었습니다."
    if ("10000000" in lowered or "1천만원" in lowered) and "claim_audit" in lowered:
        return "청구 금액이 1천만원 이상이면 CLAIM_AUDIT 부서만 처리하도록 제한하는 조건이 확인되었습니다."
    if "b99" in lowered and ("urgent" in lowered or "긴급" in lowered):
        return "B99 지점의 긴급 건은 본사 선승인 조건이 충족되어야 처리되도록 제한하는 조건이 확인되었습니다."
    if ("closed" in lowered or "cancelled" in lowered) and ("조정" in lowered or "adjust" in lowered):
        return "상태가 CLOSED 또는 CANCELLED이면 조정을 차단하는 조건이 확인되었습니다."
    if "vip" in lowered and any(token in lowered for token in ("22", "23", "00", "night", "야간")):
        return "VIP 고객은 야간 시간대에 주문 마감을 할 수 없도록 제한하는 조건이 확인되었습니다."
    if ("deliveryholdflag" in lowered or "delivery_hold" in lowered or "배송보류" in lowered) and any(token in lowered for token in ('"y"', "=y", "해제", "release")):
        return "delivery_hold_flag 가 Y인 경우 주문 마감을 차단하는 선행 검증 조건이 확인되었습니다."
    if ("agency" in lowered or "대리점" in lowered) and ("hq" in lowered or "본사" in lowered):
        return "대리점 채널의 고액 주문은 본사 승인 조건을 충족해야 처리되도록 제한하는 조건이 확인되었습니다."
    if ("export" in lowered or "수출" in lowered) and "review_required" in lowered:
        return "수출 주문은 고액 조건에 해당하면 REVIEW_REQUIRED 상태로 전이되도록 설정한 조건이 확인되었습니다."
    status_in_match = re.search(r"status\s+in\s*\(([^)]+)\)", text, flags=re.IGNORECASE)
    if status_in_match:
        raw_values = status_in_match.group(1)
        values = [item.strip(" '\"") for item in raw_values.split(",") if item.strip()]
        if values:
            return f"상태값이 {', '.join(values)}인 경우에만 처리 대상으로 포함하는 조건이 확인되었습니다."
    if "user_role" in lowered and "hq_reviewer" in lowered and "!=" in lowered:
        return "HQ_REVIEWER 권한이 아니면 특수 사고 청구를 처리할 수 없도록 제한하는 조건이 확인되었습니다."
    if "status eq" in lowered or "status ==" in lowered:
        status_context = re.search(r"status\s*(?:eq|==)\s*(?:\"|')([A-Z_]+)(?:\"|')", text, flags=re.IGNORECASE)
        if status_context:
            return f"상태값이 {status_context.group(1)}일 때만 화면 액션 또는 처리 흐름이 열리도록 제한하는 조건이 확인되었습니다."
    if "status in" in lowered:
        quoted = re.findall(r"(?:\"|')([A-Z_]+)(?:\"|')", text)
        filtered = [item for item in quoted if item in {"PAID", "READY", "REVIEW_REQUIRED", "REVIEW", "CLOSED", "CANCELLED", "APPROVED", "PENDING", "REJECTED"}]
        if filtered:
            return f"상태값이 {', '.join(filtered)}일 때만 화면 액션 또는 처리 흐름이 열리도록 제한하는 조건이 확인되었습니다."
    quoted_value = re.findall(r"(?:\"|')([A-Z0-9_]+)(?:\"|')", text)
    if ("branch_code" in lowered or "channel_code" in lowered) and quoted_value:
        if "hq" in lowered:
            return f"{quoted_value[0]} 조건에서는 본사 승인 또는 본사 조직 조건이 필요하도록 제한하는 규칙이 확인되었습니다."

    state_list_match = re.search(r"\[(?:\"|')([A-Z_]+)(?:\"|')(?:\s*,\s*(?:\"|')([A-Z_]+)(?:\"|'))+\]", text)
    if state_list_match and any(token in lowered for token in ("closed", "cancelled", "ready", "paid", "review_required")):
        values = re.findall(r"(?:\"|')([A-Z_]+)(?:\"|')", text)
        if values:
            return f"상태값이 {', '.join(values)}로 제한되는 조건이 확인되었습니다."

    amount_match = re.search(r">=\s*([0-9]{6,})", text)
    if amount_match:
        amount = amount_match.group(1)
        return f"처리 금액이 {amount} 이상일 때 별도 제한을 적용하는 조건이 확인되었습니다."
    if ".equals(" in text or "==" in text:
        quoted = re.findall(r"(?:\"|')([^\"']+)(?:\"|')", text)
        if quoted:
            return f"{', '.join(quoted[:2])} 값 비교를 기준으로 처리 가능 여부를 분기하는 조건이 확인되었습니다."

    if "지점장 300만원 한도" in rule_title:
        return "청구 금액이 300만원 이상이면 지점장 권한으로는 처리할 수 없도록 제한하는 조건이 확인되었습니다."
    if "대리점 고액 주문 본사 전용" in rule_title:
        return "대리점 채널의 고액 주문은 본사 승인 조건을 충족해야 처리되도록 제한하는 조건이 확인되었습니다."
    if "수출 주문 고액건 REVIEW_REQUIRED" in rule_title:
        return "수출 주문은 고액 조건에 해당하면 REVIEW_REQUIRED 상태로 전이되도록 설정한 조건이 확인되었습니다."
    if "FRAUD 본사 심사 전용" in rule_title:
        return "사고 유형이 FRAUD이면 HQ_REVIEWER 권한에서만 처리되도록 제한하는 조건이 확인되었습니다."
    if "B99 긴급건 본사 선승인" in rule_title:
        return "B99 지점의 긴급 건은 본사 선승인 조건이 충족되어야 처리되도록 제한하는 조건이 확인되었습니다."
    if "마감 상태 조정 금지" in rule_title or "마감/취소 상태 조정 금지" in rule_title or "상태 조정 금지" in rule_title:
        return "상태가 CLOSED 또는 CANCELLED이면 조정을 차단하는 조건이 확인되었습니다."
    if rule_title:
        return f"제공 자산에서 '{rule_title}'와 직접 연결되는 조건이 확인되었습니다."
    return ""


def _result_package_markdown(pkg: dict[str, Any], *, surface_mode: str = "internal") -> str:
    normalized_surface_mode = normalize_surface_mode(surface_mode)
    export_review_artifacts = can_export_review_artifacts(policy_for_surface_mode(normalized_surface_mode).access_profile)
    if not export_review_artifacts:
        explanation = ExplanationPresenter().present(
            project_id=str((pkg.get("project") or {}).get("id") or ""),
            result_package=pkg,
            audience="manager",
            surface_mode=normalized_surface_mode,
        )
        return _result_explanation_markdown(explanation)
    executive_summary = pkg.get("executive_summary") or {}
    provenance = pkg.get("provenance") or {}
    scope_notice = pkg.get("scope_notice") or {}
    executive_state = _humanize_summary_state(str(executive_summary.get("state") or ""))
    diagnosis_state = _humanize_summary_state(str((pkg.get("diagnosis") or {}).get("state") or ""))
    draft_state = _humanize_summary_state(str((pkg.get("transition_draft") or {}).get("state") or ""))
    report_purpose = str(pkg.get("report_purpose") or "").strip()
    report_scope = _trim_items(pkg.get("report_scope") or [], limit=6)
    report_questions = _trim_items(pkg.get("report_questions") or [], limit=6)
    summary_lines = executive_summary.get("summary_lines") or []
    decision_focus = executive_summary.get("decision_focus") or []
    risk_lines = executive_summary.get("key_risks") or []
    next_step_lines = executive_summary.get("next_steps") or []
    summary_markdown = [f"- {item}" for item in summary_lines] if summary_lines else ["- 해당 없음"]
    decision_focus_markdown = [f"- {item}" for item in decision_focus] if decision_focus else ["- 해당 없음"]
    risk_markdown = [f"- {item}" for item in risk_lines] if risk_lines else ["- 해당 없음"]
    next_step_markdown = [f"- {item}" for item in next_step_lines] if next_step_lines else ["- 해당 없음"]
    lines = [
        f"# 결과 패키지 - {pkg['project']['project_name']}",
        "",
        "## Executive Summary",
        f"- 제목: {executive_summary.get('title') or '-'}",
        f"- 상태: {executive_state or '-'}",
        "",
        "### 결정 요약",
        f"- {executive_summary.get('core_message') or '-'}",
        "",
        "### 핵심 판단",
        *summary_markdown,
        "",
        "### 이번 회의 결정 항목",
        *decision_focus_markdown,
        "",
        "### 주요 리스크",
        *risk_markdown,
        "",
        "### 다음 실행",
        *next_step_markdown,
        "",
        "## 보고서 목적",
        f"- {report_purpose or '이 실행의 목적이 아직 정리되지 않았습니다.'}",
        "",
        "## 분석 범위",
        *([f"- {item}" for item in report_scope] if report_scope else ["- 해당 없음"]),
        "",
        "## 검증 질문",
        *([f"- {item}" for item in report_questions] if report_questions else ["- 해당 없음"]),
        "",
        "## 핵심 결론",
        f"- {(pkg.get('core_conclusion') or '결과 생성 중')}",
        "",
        "## 핵심 업무 규칙",
    ]
    grounded_rules = pkg.get("grounded_business_rules") or []
    if grounded_rules:
        for rule in grounded_rules:
            lines.extend(
                [
                    f"### {rule.get('title') or '-'}",
                    f"- 설명: {rule.get('description') or '-'}",
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
                    lines.append(f"    - 조건 요약: {evidence.get('condition_summary') or '-'}")
                    lines.append(f"    - 설계 반영 위치: {', '.join(evidence.get('design_targets') or []) or '-'}")
                    lines.append(f"    - 신뢰도: {evidence.get('confidence') or '-'}")
    else:
        fallback_core_rules = _trim_items(pkg.get("core_business_rules") or [], limit=4)
        if fallback_core_rules:
            lines.extend(f"- {item}" for item in fallback_core_rules)
        else:
            lines.append("- 직접 확인된 핵심 업무 규칙이 없습니다.")
    lines.extend(
        [
            "",
            "## 즉시 결정 필요",
        ]
    )
    decisions = pkg.get("decision_items") or []
    if decisions:
        for item in decisions:
            lines.append(f"- {item.get('statement') or '-'}")
            lines.append(f"  - 근거: {item.get('rationale') or '-'}")
    else:
        lines.append("- 즉시 결정할 항목이 없습니다.")
    lines.extend(
        [
            "",
            "## 유지해야 할 계약",
        ]
    )
    retained = pkg.get("retained_contracts") or []
    if retained:
        for item in retained:
            lines.append(f"- {item.get('item') or '-'}")
            lines.append(f"  - 근거: {item.get('basis') or '-'}")
    else:
        lines.append("- 직접 확인된 유지 계약이 없습니다.")
    lines.extend(["", "## 분리 우선순위"])
    for item in pkg.get("priority_split_items") or []:
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
    lines.extend(["", "## 확인 필요 항목"])
    verification = pkg.get("verification_checkpoints") or []
    if verification:
        for item in verification:
            lines.append(f"- {item.get('item') or '-'}")
            lines.append(f"  - 사유: {item.get('reason') or '-'}")
    else:
        lines.append("- 해당 없음")
    lines.extend(["", "## 설계 선택지 비교"])
    for option in pkg.get("design_options") or []:
        lines.extend(
            [
                f"### {option.get('name') or '-'}",
                f"- 구조 설명: {option.get('structure_summary') or '-'}",
                f"- 장점: {' / '.join(option.get('advantages') or []) or '-'}",
                f"- 리스크: {' / '.join(option.get('risks') or []) or '-'}",
                f"- 예상 난이도: {option.get('difficulty') or '-'}",
                f"- 예상 기간: {option.get('duration_weeks') or 0}주",
                f"- 추천 여부: {'예' if option.get('recommended') else '아니오'}",
                f"- 선택 근거: {option.get('selection_reason') or '-'}",
                "",
            ]
        )
    if lines[-1] == "":
        lines.pop()
    lines.extend(["", "## 추천안"])
    recommended_option = pkg.get("recommended_option") or {}
    if recommended_option:
        lines.extend(
            [
                f"- {recommended_option.get('name') or '-'}",
                f"- 구조 설명: {recommended_option.get('structure_summary') or '-'}",
                f"- 선택 근거: {recommended_option.get('selection_reason') or '-'}",
            ]
        )
    else:
        lines.append("- 추천안 미생성")
    lines.extend(["", "## 실행 계획"])
    for week in pkg.get("execution_plan") or []:
        lines.extend(
            [
                f"### {week.get('week_label') or '-'}",
                f"- 목표: {week.get('goal') or '-'}",
                f"- 작업: {' / '.join(week.get('tasks') or []) or '해당 없음'}",
                f"- 관련 규칙: {', '.join(week.get('related_rules') or []) or '해당 없음'}",
                f"- 관련 계약: {', '.join(week.get('related_contracts') or []) or '해당 없음'}",
                f"- 인력: {' / '.join(week.get('roles') or []) or '해당 없음'}",
                f"- 기간: {week.get('duration_weeks') or 0}주",
                f"- 산출물: {' / '.join(week.get('deliverables') or []) or '해당 없음'}",
            ]
        )
    accounting = pkg.get("accounting") or {}
    if accounting:
        calc_status = accounting.get("calculation_status") or {}
        input_validation = accounting.get("input_validation") or {}
        analysis = accounting.get("accounting_analysis") or {}
        fx_calc = accounting.get("fx_calculation") or {}
        voucher_review = accounting.get("voucher_review") or {}
        lines.extend(
            [
                "",
                "## 회계 계산 요약",
                f"- {accounting.get('summary_sentence') or '-'}",
                "",
                "## 계산 가능 여부",
                f"- 계산 가능: {'예' if calc_status.get('can_calculate') else '아니오'}",
                f"- 사유: {calc_status.get('reason') or calc_status.get('blocking_issue') or '-'}",
            ]
        )
        if input_validation.get("missing_required_inputs"):
            lines.append(f"- 누락 입력: {', '.join(input_validation.get('missing_required_inputs') or [])}")
        lines.extend(["", "## 회계 방식 분석"])
        if analysis.get("candidate_methods"):
            lines.append(f"- 후보 방식: {', '.join(analysis.get('candidate_methods') or [])}")
        lines.append(f"- 추천 방식: {analysis.get('recommended_method') or '-'}")
        for item in analysis.get("reasons") or []:
            lines.append(f"- {item.get('message') or '-'}")
        lines.extend(["", "## 외화 계산 결과"])
        lines.append(f"- 계산 상태: {fx_calc.get('status') or '-'}")
        lines.append(f"- 적용 방식: {fx_calc.get('method') or '-'}")
        if fx_calc.get("realized_gain_loss_krw") is not None:
            lines.append(f"- 환차손익: {fx_calc.get('realized_gain_loss_krw'):,}원")
        if fx_calc.get("failure_reason"):
            lines.append(f"- 실패 사유: {fx_calc.get('failure_reason')}")
        for step in fx_calc.get("detail_steps") or []:
            lines.append(f"- {step.get('message') or '-'}")
        lines.extend(["", "## 전표 검토 결과"])
        lines.append(f"- 검토 상태: {voucher_review.get('status') or '-'}")
        if voucher_review.get("status") == "입력 부족":
            lines.append("- 차변/대변 균형: 검토 불가")
            lines.append("- 정책 일치: 검토 불가")
        else:
            if voucher_review.get("balance_ok") is not None:
                lines.append(f"- 차변/대변 균형: {'예' if voucher_review.get('balance_ok') else '아니오'}")
            if voucher_review.get("policy_consistent") is not None:
                lines.append(f"- 정책 일치: {'예' if voucher_review.get('policy_consistent') else '아니오'}")
        if voucher_review.get("failure_reason"):
            lines.append(f"- 실패 사유: {voucher_review.get('failure_reason')}")
        for item in voucher_review.get("review_points") or []:
            lines.append(f"- {item.get('message') or '-'}")
        for item in voucher_review.get("mismatches") or []:
            lines.append(f"- 불일치: {item.get('message') or '-'}")
    lines.extend(["", "## 리스크"])
    risks = pkg["diagnosis"].get("risks") or []
    if risks:
        lines.extend(f"- {item}" for item in risks)
    else:
        lines.append(f"- {diagnosis_state}")
    lines.extend(["", "## 전환 초안"])
    draft = (pkg["transition_draft"].get("recomposition_draft") or {})
    draft_lines = []
    for key in ("database", "backend", "frontend"):
        values = draft.get(key) or []
        if values:
            draft_lines.append(f"### {key}")
            draft_lines.extend(f"- {item}" for item in values)
            draft_lines.append("")
    if draft_lines:
        lines.extend(draft_lines[:-1])
    else:
        lines.append(f"- {draft_state}")
    review_diff = (((pkg.get("extensions") or {}) if isinstance(pkg, dict) else {}) or {}).get("review_diff") or {}
    review_diff_markdown = str(review_diff.get("markdown") or "").strip()
    if review_diff_markdown:
        lines.extend(["", review_diff_markdown])
    lines.extend(["", "## 부록"])
    lines.extend(
        [
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
    taxonomy = explanation.taxonomy_view
    cards = explanation.summary_cards or []
    sections = explanation.section_views or []
    lines = [
        f"# 구조 판단 - {explanation.project_id}",
        "",
        "## 구조 판단",
        f"- {taxonomy.core_judgment.structural_judgment or '-'}",
        "",
        "## 권장 전략",
        f"- {taxonomy.core_judgment.recommended_strategy or '-'}",
        f"- 개선 방식: {taxonomy.core_judgment.top_decision_type or '-'}",
        "",
        "## 판단 근거",
    ]
    if taxonomy.evidence_view.top_priority_score is not None:
        lines.append(f"- 우선순위 점수: {taxonomy.evidence_view.top_priority_score}")
    score_breakdown = taxonomy.evidence_view.score_breakdown or {}
    if score_breakdown:
        lines.append(
            "- 점수 요약: "
            + ", ".join(f"{key}={value}" for key, value in score_breakdown.items())
        )
    explainability = taxonomy.evidence_view.explainability or {}
    if explainability.get("score_summary"):
        lines.append(f"- 계산 요약: {explainability.get('score_summary')}")
    if cards:
        lines.extend(["", "## 요약 카드"])
        for card in cards:
            lines.append(f"### {card.title}")
            lines.append(f"- {card.body}")
    if sections:
        lines.extend(["", "## 다음 단계"])
        for section in sections:
            lines.append(f"### {section.title}")
            for row in str(section.text or "").splitlines():
                normalized = row.strip()
                if normalized:
                    lines.append(f"- {normalized}")
    lines.extend(
        [
            "",
            "## 설명 관점",
            f"- {taxonomy.explanation_context.narrative_axis or '-'}",
        ]
    )
    return "\n".join(lines).strip() + "\n"


async def _result_package_docx_response(
    project: ModernizationProject,
    pkg: dict[str, Any],
    *,
    surface_mode: str = "internal",
) -> FileResponse:
    if not app_state.doc_service or not app_state.doc_service.is_available():
        raise HTTPException(status_code=503, detail="Document Service unavailable")

    normalized_surface_mode = normalize_surface_mode(surface_mode)
    export_review_artifacts = can_export_review_artifacts(policy_for_surface_mode(normalized_surface_mode).access_profile)
    suffix_name = "result.docx" if export_review_artifacts else "external_result.docx"
    download_name = _safe_download_name(project.project_name, suffix_name)
    title = f"{'결과 패키지' if export_review_artifacts else '구조 판단'} - {project.project_name}"
    markdown_content = _result_package_markdown(pkg, surface_mode=normalized_surface_mode)
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
    return FileResponse(
        path=result.output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name,
        headers={"Content-Disposition": _download_disposition(download_name, "project_result.docx")},
    )


async def _result_package_pptx_response(
    project: ModernizationProject,
    pkg: dict[str, Any],
    *,
    surface_mode: str = "internal",
) -> FileResponse:
    if not app_state.doc_service or not app_state.doc_service.is_available():
        raise HTTPException(status_code=503, detail="Document Service unavailable")

    normalized_surface_mode = normalize_surface_mode(surface_mode)
    export_review_artifacts = can_export_review_artifacts(policy_for_surface_mode(normalized_surface_mode).access_profile)
    suffix_name = "result.pptx" if export_review_artifacts else "external_result.pptx"
    download_name = _safe_download_name(project.project_name, suffix_name)
    title = f"{'결과 패키지' if export_review_artifacts else '구조 판단'} - {project.project_name}"
    markdown_content = _result_package_markdown(pkg, surface_mode=normalized_surface_mode)
    result = await app_state.doc_service.generate(
        DocumentRequest(
            content=markdown_content,
            output_type=DocumentType.PPTX,
            title=title,
            filename=download_name,
            style_options={
                "subtitle": f"{project.client_name} · 현대화 분석 결과 요약",
                "font_size": 20,
            },
        )
    )
    return FileResponse(
        path=result.output_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=download_name,
        headers={"Content-Disposition": _download_disposition(download_name, "project_result.pptx")},
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


@router.get("/projects/create", include_in_schema=False)
async def project_create_view() -> FileResponse:
    return FileResponse(_static_file("projects_create.html"))


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
    projects = db.query(ModernizationProject).filter(ModernizationProject.user_id == user.id).order_by(ModernizationProject.created_at.desc()).all()
    items = []
    for project in projects:
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
    return {"projects": items}


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
            template_key=payload.template_key,
            template_mode="recommended",
            constraints_json=json.dumps(payload.constraints, ensure_ascii=False),
            upload_session_id=payload.upload_session_id,
            asset_manifest_json=_serialize_asset_manifest([item.model_dump() for item in payload.asset_manifest]),
            status="running",
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

    status = "running"
    try:
        project = db.query(ModernizationProject).filter(ModernizationProject.id == project_id).first()
        ordered_assets = _ordered_project_assets(project, db) if project else []
        context_parts = [
            (asset.original_filename, read_text(asset.extracted_relative_path, project_asset=True))
            for asset in ordered_assets
        ]
        app_state.TEMP_CONTEXT_STORE[payload.upload_session_id] = build_temp_context(context_parts)
        safe_bundle = _build_safe_bundle_for_project(project, db) if project else None
        start_project_wrapped_run(
            run_id=run_id,
            session_id=session_id,
            project_name=payload.project_name,
            client_name=payload.client_name,
            upload_session_id=payload.upload_session_id,
            constraints=payload.constraints,
            asset_manifest=payload.asset_manifest,
            safe_bundle=safe_bundle,
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
    project.status = "running"
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

    status = "running"
    try:
        safe_bundle = _build_safe_bundle_for_project(project, db)
        start_project_wrapped_run(
            run_id=new_run_id,
            session_id=new_session_id,
            project_name=project.project_name,
            client_name=project.client_name,
            upload_session_id=project.upload_session_id,
            constraints=_parse_json_list(project.constraints_json),
            asset_manifest=[ProjectAssetItem.model_validate(item) for item in _parse_json_list(project.asset_manifest_json)],
            safe_bundle=safe_bundle,
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
    _rebuild_project_temp_context(project, db)

    new_run_id, new_session_id = create_project_wrapped_run(db=db, user=user)
    sequence_no = _history_sequence_next(project.id, db)
    project.run_id = new_run_id
    project.session_id = new_session_id
    project.status = "running"
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

    status = "running"
    try:
        safe_bundle = _build_safe_bundle_for_project(project, db)
        start_project_wrapped_run(
            run_id=new_run_id,
            session_id=new_session_id,
            project_name=project.project_name,
            client_name=project.client_name,
            upload_session_id=project.upload_session_id,
            constraints=_parse_json_list(project.constraints_json),
            asset_manifest=[ProjectAssetItem.model_validate(item) for item in _parse_json_list(project.asset_manifest_json)],
            safe_bundle=safe_bundle,
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
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> Any:
    if _wants_html(request, format):
        return FileResponse(_static_file("project_result.html"))
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    project = _project_or_404(project_id, user, db)
    context = _load_project_result_context(project, db=db, app_version=getattr(request.app, "version", None))
    result_package = _surface_filtered_result_package(context["result_package"], surface_mode=surface_mode)
    if format == "md":
        download_name = _safe_download_name(project.project_name, "external_result.md" if surface_mode == "external" else "result.md")
        return Response(
            content=_result_package_markdown(result_package, surface_mode=surface_mode),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": _download_disposition(download_name, "project_result.md")
            },
        )
    if format == "docx":
        return await _result_package_docx_response(project, result_package, surface_mode=surface_mode)
    if format == "pptx":
        return await _result_package_pptx_response(project, result_package, surface_mode=surface_mode)
    if format == "json":
        return result_package
    return result_package


@router.get("/projects/{project_id}/result/explanation", response_model=ResultExplanationResponse)
async def project_result_explanation(
    project_id: str,
    request: Request,
    audience: str = Query("manager", pattern="^(developer|manager|client)$"),
    surface_mode: str = Query("internal", pattern="^(internal|external)$"),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> ResultExplanationResponse:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    project = _project_or_404(project_id, user, db)
    context = _load_project_result_context(project, db=db, app_version=getattr(request.app, "version", None))
    return ExplanationPresenter().present(
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
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> ResultQAResponse:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    project = _project_or_404(project_id, user, db)
    context = _load_project_result_context(project, db=db, app_version=getattr(request.app, "version", None))
    return await ResultQuestionAnsweringService().answer(
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
