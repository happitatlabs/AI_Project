from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from mellow_link.infra import get_current_user, get_db, User
from mellow_link.infra.run_events import create_run
from mellow_link.routers.runs import _resolve_run_session_id

from .runner import start_research_run
from .schemas import ResearchAssistantStartRequest, ResearchAssistantStartResponse

router = APIRouter(prefix="/modules/research_assistant", tags=["Modules"])
_STATIC_DIR = Path(__file__).resolve().parent / "static"


@router.get("", include_in_schema=False)
def research_assistant_ui() -> FileResponse:
    return FileResponse(str(_STATIC_DIR / "index.html"))


@router.post("/runs", response_model=ResearchAssistantStartResponse)
def start_research_assistant(
    payload: ResearchAssistantStartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResearchAssistantStartResponse:
    session_id = _resolve_run_session_id(db, user, None)
    run_id = create_run(session_id=session_id, db=db, module_id="research_assistant", run_kind="research_run")
    start_research_run(run_id=run_id, session_id=session_id, question=payload.question, context_note=payload.context_note)
    return ResearchAssistantStartResponse(run_id=run_id, session_id=session_id)
