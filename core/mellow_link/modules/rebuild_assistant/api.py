from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from mellow_link.infra import User, get_current_user, get_db
from mellow_link.infra.run_events import create_run
from mellow_link.routers.runs import _resolve_run_session_id
from mellow_link.services.anonymization.schemas import SafeAnalysisBundle
from mellow_link.services.refactoring_support_engine.analysis_context_builder import AnalysisContextBuilder
from mellow_link.services.refactoring_support_engine.schemas import AnalysisContextBundle

from .runner import start_rebuild_assistant_safe_bundle_run
from .schemas import (
    ProjectAssetItem,
    RebuildAssistantBundleRequest,
    RebuildAssistantStartResponse,
)

router = APIRouter(prefix="/modules/rebuild_assistant", tags=["Modules"])
_STATIC_DIR = Path(__file__).resolve().parent / "static"


def build_project_goal(project_name: str, client_name: str) -> str:
    return (
        f"{client_name}의 {project_name} 레거시 자산을 분석해 기능 분류, 업무 규칙 추출, "
        "현대화 설계안, 전환 초안을 작성하라."
    )


def _safe_bundle_goal_text(safe_bundle: SafeAnalysisBundle | None) -> str:
    if safe_bundle is None:
        return ""
    asset_name_by_id = {
        str(asset.asset_id or ""): str(asset.name or "").strip().lower()
        for asset in list(safe_bundle.asset_summary or [])
    }
    goal_chunks: list[str] = []
    for source in list(safe_bundle.sources or []):
        asset_name = asset_name_by_id.get(str(source.asset_id or ""), "")
        if asset_name != "goal.txt":
            continue
        content = str(source.content or "").strip()
        if content:
            goal_chunks.append(content)
    return "\n".join(goal_chunks).strip()


def resolve_project_goal(
    *,
    inline_goal: str,
    safe_bundle: SafeAnalysisBundle | None,
    project_name: str,
    client_name: str,
) -> str:
    explicit_goal = str(inline_goal or "").strip()
    if explicit_goal:
        return explicit_goal
    file_goal = _safe_bundle_goal_text(safe_bundle)
    if file_goal:
        return file_goal
    return build_project_goal(project_name=project_name, client_name=client_name)


def launch_project_wrapped_run(
    *,
    db: Session,
    user: User,
    project_name: str,
    client_name: str,
    upload_session_id: str,
    constraints: list[str] | None = None,
    asset_manifest: list[ProjectAssetItem] | None = None,
    safe_bundle: SafeAnalysisBundle,
    goal: str = "",
    analysis_context: AnalysisContextBundle | None = None,
) -> tuple[str, str]:
    session_id = _resolve_run_session_id(db, user, None)
    run_id = create_run(session_id=session_id, db=db, module_id="rebuild_assistant", run_kind="rebuild_plan")
    start_project_wrapped_run(
        run_id=run_id,
        session_id=session_id,
        project_name=project_name,
        client_name=client_name,
        goal=goal,
        upload_session_id=upload_session_id,
        constraints=constraints,
        asset_manifest=asset_manifest,
        safe_bundle=safe_bundle,
        analysis_context=analysis_context,
    )
    return run_id, session_id


def create_project_wrapped_run(
    *,
    db: Session,
    user: User,
) -> tuple[str, str]:
    session_id = _resolve_run_session_id(db, user, None)
    run_id = create_run(session_id=session_id, db=db, module_id="rebuild_assistant", run_kind="rebuild_plan")
    return run_id, session_id


def start_project_wrapped_run(
    *,
    run_id: str,
    session_id: str,
    project_name: str,
    client_name: str,
    upload_session_id: str,
    constraints: list[str] | None = None,
    asset_manifest: list[ProjectAssetItem] | None = None,
    safe_bundle: SafeAnalysisBundle,
    goal: str = "",
    analysis_context: AnalysisContextBundle | None = None,
) -> None:
    resolved_goal = str(goal or "").strip() or resolve_project_goal(
        inline_goal="",
        safe_bundle=safe_bundle,
        project_name=project_name,
        client_name=client_name,
    )
    wrapped_constraints = (constraints or []) + [
        f"project_name={project_name}",
        f"client_name={client_name}",
        f"asset_count={len(asset_manifest or [])}",
    ]
    if analysis_context is None:
        analysis_context = AnalysisContextBuilder().build(
            project_id=safe_bundle.project_id,
            run_id=run_id,
            safe_bundle=safe_bundle,
            goal=resolved_goal,
            constraints=constraints or [],
            project_name=project_name,
            client_name=client_name,
        )
    start_rebuild_assistant_safe_bundle_run(
        run_id=run_id,
        session_id=session_id,
        goal=resolved_goal,
        safe_bundle=safe_bundle,
        constraints=wrapped_constraints,
        analysis_context=analysis_context,
    )


@router.get("", include_in_schema=False)
def rebuild_assistant_ui() -> FileResponse:
    return FileResponse(str(_STATIC_DIR / "index.html"))


@router.post("/runs", include_in_schema=False)
def start_rebuild_assistant_disabled() -> RebuildAssistantStartResponse:
    raise HTTPException(status_code=403, detail="Raw rebuild entrypoint is disabled. Use safe bundle execution.")


@router.post("/bundle-runs", response_model=RebuildAssistantStartResponse)
def start_rebuild_assistant_from_bundle(
    payload: RebuildAssistantBundleRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RebuildAssistantStartResponse:
    session_id = _resolve_run_session_id(db, user, None)
    run_id = create_run(session_id=session_id, db=db, module_id="rebuild_assistant", run_kind="rebuild_plan")
    start_rebuild_assistant_safe_bundle_run(
        run_id=run_id,
        session_id=session_id,
        goal=payload.goal,
        safe_bundle=payload.safe_bundle,
        constraints=payload.constraints,
    )
    return RebuildAssistantStartResponse(run_id=run_id, session_id=session_id)
