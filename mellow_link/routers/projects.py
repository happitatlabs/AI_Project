from __future__ import annotations

import json
import os
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
    return f"{base}_result.{suffix}"


def _download_disposition(download_name: str, fallback_name: str) -> str:
    return f'attachment; filename="{fallback_name}"; filename*=UTF-8\'\'{quote(download_name)}'


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
    feature_mode = finished_payload.get("primary_feature_mode") or "-"
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
    return normalized[:limit]


def _build_executive_next_steps(
    *,
    missing_context_details: list[dict[str, Any]],
    recommended_directions: list[str],
) -> list[str]:
    if missing_context_details:
        first_required = str(missing_context_details[0].get("required_material") or "").strip() or "-"
        first = f"추가 자료 확보: {first_required}"
    else:
        first = "현대화 방향 검토: 추천 방향 기준 우선순위 합의"
    return [
        first,
        "파일럿 범위 확정: 단일 기능 / 단일 화면 기준 상세 범위 합의",
        "후속 실행 결정: 설계안 검토 후 재분석 또는 상세 설계 착수",
    ]


def _build_executive_summary(
    *,
    run_state: str,
    core_conclusion: str,
    recommended_directions: list[str],
    diagnosis: dict[str, Any],
    design: dict[str, Any],
) -> dict[str, Any]:
    missing_context_details = list(diagnosis.get("missing_context_details") or [])
    limited_recommended_directions = _trim_items(recommended_directions)[:3]
    design_strategy = _trim_items(list(design.get("rebuild_strategy") or []))[:3]
    key_risks = _trim_items(list(diagnosis.get("risks") or []))[:3]
    modernization_direction = (limited_recommended_directions or design_strategy)[:3]
    has_core = bool(core_conclusion)
    has_direction = bool(limited_recommended_directions)

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
        "title": "1페이지 요약",
        "state": state,
        "core_message": core_message,
        "modernization_direction": modernization_direction[:3],
        "key_risks": key_risks[:3],
        "next_steps": _build_executive_next_steps(
            missing_context_details=missing_context_details,
            recommended_directions=modernization_direction,
        ),
    }


def build_result_package(
    project: ModernizationProject,
    snapshot: dict[str, Any] | None,
    result: StructuredRebuildResult | None,
    *,
    assets: list[dict[str, Any]],
    app_version: str | None = None,
) -> dict[str, Any]:
    run_state = _project_status_from_run(snapshot)
    core_conclusion = (result.one_line_conclusion if result else "").strip()
    recommended_directions = list(result.recommended_directions[:3]) if result else []
    layer_dump = result.layer_reconstruction.model_dump() if result else {}
    extracted_rules_dump = result.extracted_rules.model_dump() if result else {}
    recomposition_dump = result.recomposition_draft.model_dump() if result else {}
    diagnosis_state = "ready" if result and (result.analysis_summary or result.risks or result.missing_context_details) else ("결과 생성 중" if run_state == "running" else "데이터 없음")
    design_state = "ready" if result and (result.rebuild_strategy or _has_layer_content(layer_dump) or _has_extracted_rules_content(extracted_rules_dump)) else ("결과 생성 중" if run_state == "running" else "데이터 없음")
    draft_state = "ready" if result and _has_layer_content(recomposition_dump) else ("결과 생성 중" if run_state == "running" else "데이터 없음")
    diagnosis = {
        "analysis_summary": list(result.analysis_summary) if result else [],
        "risks": list(result.risks) if result else [],
        "missing_context_details": _missing_context_blocks(result),
        "state": diagnosis_state,
    }
    design = {
        "rebuild_strategy": list(result.rebuild_strategy) if result else [],
        "layer_reconstruction": layer_dump,
        "extracted_rules": extracted_rules_dump,
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
    executive_summary = _build_executive_summary(
        run_state=run_state,
        core_conclusion=core_conclusion,
        recommended_directions=recommended_directions,
        diagnosis=diagnosis,
        design=design,
    )
    return {
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
        "scope_notice": scope_notice,
        "core_conclusion": core_conclusion,
        "recommended_directions": recommended_directions,
        "diagnosis": diagnosis,
        "design": design,
        "transition_draft": transition_draft,
        "appendix": appendix,
    }


def _result_package_markdown(pkg: dict[str, Any]) -> str:
    executive_summary = pkg.get("executive_summary") or {}
    provenance = pkg.get("provenance") or {}
    scope_notice = pkg.get("scope_notice") or {}
    direction_lines = executive_summary.get("modernization_direction") or []
    risk_lines = executive_summary.get("key_risks") or []
    next_step_lines = executive_summary.get("next_steps") or []
    direction_markdown = [f"- {item}" for item in direction_lines] if direction_lines else ["- 해당 없음"]
    risk_markdown = [f"- {item}" for item in risk_lines] if risk_lines else ["- 해당 없음"]
    next_step_markdown = [f"- {item}" for item in next_step_lines] if next_step_lines else ["- 해당 없음"]
    lines = [
        f"# 결과 패키지 - {pkg['project']['project_name']}",
        "",
        "## 1페이지 요약",
        f"- 제목: {executive_summary.get('title') or '-'}",
        f"- 상태: {executive_summary.get('state') or '-'}",
        "",
        "### 핵심 결론",
        f"- {executive_summary.get('core_message') or '-'}",
        "",
        "### 현대화 방향",
        *direction_markdown,
        "",
        "### 주요 리스크",
        *risk_markdown,
        "",
        "### 다음 단계",
        *next_step_markdown,
        "",
        "## Provenance",
        f"- Run ID: {provenance.get('run_id') or '-'}",
        f"- 생성 기준 시각 (UTC): {provenance.get('generated_at') or '-'}",
        f"- Run 상태: {provenance.get('run_status') or '-'}",
        f"- 앱 버전: {provenance.get('app_version') or '-'}",
        f"- 모듈 버전: {provenance.get('module_version') or '-'}",
        f"- 템플릿 키: {provenance.get('template_key') or '-'}",
        f"- 입력 자산 수: {len(provenance.get('input_assets') or [])}",
        "",
        "## 범위 및 한계",
        f"- {scope_notice.get('version_label') or '-'}",
        f"- {scope_notice.get('summary') or '-'}",
        "",
        "### 지원 범위",
        *[f"- {item}" for item in (scope_notice.get("supported") or [])],
        "",
        "### 비지원 범위",
        *[f"- {item}" for item in (scope_notice.get("not_supported") or [])],
        "",
        "## 핵심 결론",
        f"- {(pkg.get('core_conclusion') or '결과 생성 중')}",
        "",
        "## 추천 방향",
    ]
    directions = pkg.get("recommended_directions") or []
    if directions:
        lines.extend(f"- {item}" for item in directions)
    else:
        lines.append(f"- {pkg['diagnosis']['state']}")
    lines.extend(
        [
            "",
            "## 진단",
        ]
    )
    analysis = pkg["diagnosis"].get("analysis_summary") or []
    risks = pkg["diagnosis"].get("risks") or []
    missing = pkg["diagnosis"].get("missing_context_details") or []
    if analysis:
        lines.extend(f"- {item}" for item in analysis)
    else:
        lines.append(f"- {pkg['diagnosis']['state']}")
    if risks:
        lines.extend(["", "### 리스크", *[f"- {item}" for item in risks]])
    if missing:
        lines.append("")
        lines.append("### 추가 자료 요청")
        for item in missing:
            lines.extend(
                [
                    "[필요 자료]",
                    f"- {item.get('required_material') or '-'}",
                    "",
                    "[이유]",
                    f"- {item.get('reason') or '-'}",
                    "",
                ]
            )
    lines.extend(["", "## 설계안"])
    strategy = pkg["design"].get("rebuild_strategy") or []
    if strategy:
        lines.extend(f"- {item}" for item in strategy)
    else:
        lines.append(f"- {pkg['design']['state']}")
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
        lines.append(f"- {pkg['transition_draft']['state']}")
    lines.extend(["", "## 부록"])
    for item in pkg["appendix"].get("asset_manifest") or []:
        filename = item.get("name") or "-"
        size = item.get("size") or 0
        lines.append(f"- {filename} ({size} bytes)")
    return "\n".join(lines).strip() + "\n"


async def _result_package_docx_response(project: ModernizationProject, pkg: dict[str, Any]) -> FileResponse:
    if not app_state.doc_service or not app_state.doc_service.is_available():
        raise HTTPException(status_code=503, detail="Document Service unavailable")

    download_name = _safe_download_name(project.project_name, "docx")
    title = f"결과 패키지 - {project.project_name}"
    markdown_content = _result_package_markdown(pkg)
    result = await app_state.doc_service.generate(
        DocumentRequest(
            content=markdown_content,
            output_type=DocumentType.DOCX,
            title=title,
            filename=download_name,
        )
    )
    return FileResponse(
        path=result.output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name,
        headers={"Content-Disposition": _download_disposition(download_name, "project_result.docx")},
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

    return ProjectStartResponse(project_id=project_id, run_id=run_id, session_id=session_id, status=status)


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
        "missing_context_details": _missing_context_blocks(structured),
        "structured_result": structured.model_dump() if structured else None,
    }


@router.get("/projects/{project_id}/result", include_in_schema=False)
async def project_result(
    project_id: str,
    request: Request,
    format: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> Any:
    if _wants_html(request, format):
        return FileResponse(_static_file("project_result.html"))
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    project = _project_or_404(project_id, user, db)
    snapshot = get_run_snapshot(project.run_id, db=db)
    _sync_project_status(project, snapshot, db)
    events = get_run_events(project.run_id, db=db)
    structured = _extract_structured_result(events)
    assets = _build_assets_payload(project, db)
    result_package = build_result_package(
        project,
        snapshot,
        structured,
        assets=assets,
        app_version=getattr(request.app, "version", None),
    )
    if format == "md":
        download_name = _safe_download_name(project.project_name, "md")
        return Response(
            content=_result_package_markdown(result_package),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": _download_disposition(download_name, "project_result.md")
            },
        )
    if format == "docx":
        return await _result_package_docx_response(project, result_package)
    if format == "json":
        return result_package
    return result_package


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
