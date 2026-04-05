from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mellow_chat_runtime import app_state
from mellow_chat_runtime.core.states import SystemState, TransitionResult
from mellow_chat_runtime.infra.database import (
    ChatMessage,
    ChatSession,
    MessageFeedback,
    get_db,
    get_or_create_session,
    get_or_create_user,
)

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    question: str = Field(...)
    mode: str = Field("fast")
    session_id: Optional[int] = None
    stream: bool = True
    persona_id: str = "default"
    user_profile_id: str = "default"
    lore_topic: str = "default"
    character_id: str = "default"
    world_id: str = "default"
    scene_id: str = "default"


def _user_from_header(x_user: Optional[str]) -> str:
    return (x_user or "default_user").strip() or "default_user"


@router.get("/chat/sessions")
async def get_chat_sessions(x_user: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    username = _user_from_header(x_user)
    user = get_or_create_user(db, username)
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user.id, ChatSession.is_active == True)
        .order_by(ChatSession.created_at.desc())
        .limit(50)
        .all()
    )
    return [{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in sessions]


@router.get("/chat/sessions/{session_id}/messages")
async def get_session_messages(session_id: int, x_user: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    username = _user_from_header(x_user)
    user = get_or_create_user(db, username)
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.timestamp.asc()).all()
    feedbacks = db.query(MessageFeedback).all()
    feedback_map = {f.message_id: f.is_positive for f in feedbacks}

    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "selected_mode": m.selected_mode,
            "processing_time": m.processing_time,
            "feedback_positive": feedback_map.get(m.id),
            "created_at": m.timestamp.isoformat(),
        }
        for m in messages
    ]


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: int, x_user: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    username = _user_from_header(x_user)
    user = get_or_create_user(db, username)
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.is_active = False
    db.commit()
    return {"success": True, "deleted_id": session_id}


@router.post("/chat/messages/{message_id}/feedback")
async def submit_message_feedback(message_id: int, request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    is_positive = body.get("is_positive")
    if is_positive is None:
        raise HTTPException(status_code=400, detail="is_positive is required")

    existing = db.query(MessageFeedback).filter(MessageFeedback.message_id == message_id).first()
    if existing:
        existing.is_positive = bool(is_positive)
    else:
        db.add(MessageFeedback(message_id=message_id, is_positive=bool(is_positive)))
    db.commit()
    return {"success": True, "message_id": message_id, "positive": bool(is_positive)}


@router.post("/chat/ask")
async def chat_ask(request: ChatRequest, http_request: Request, x_user: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    if app_state.orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    username = _user_from_header(x_user)
    user = get_or_create_user(db, username)
    session = get_or_create_session(db=db, user_id=user.id, session_id=request.session_id)

    # save user message
    user_msg = ChatMessage(session_id=session.id, role="user", content=request.question)
    db.add(user_msg)
    db.commit()

    state_result = await app_state.orchestrator.request_state_change(SystemState.TEXT, reason="chat ask")
    if state_result == TransitionResult.INVALID_TRANSITION:
        raise HTTPException(status_code=409, detail="Invalid state transition")

    history_rows = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.timestamp.asc()).all()
    history = [{"role": r.role, "content": r.content} for r in history_rows[-8:]]

    async def stream_generator():
        started = time.time()
        try:
            result = await app_state.orchestrator.run_agent(
                user_input=request.question,
                history=history,
                mode=request.mode,
                persona_id=request.persona_id,
                user_profile_id=request.user_profile_id,
                lore_topic=request.lore_topic,
                character_id=request.character_id,
                world_id=request.world_id,
                scene_id=request.scene_id,
            )

            full = result.answer or ""
            for i in range(0, len(full), 200):
                yield f"data: {json.dumps({'chunk': full[i:i+200]}, ensure_ascii=False)}\\n\\n"

            elapsed_ms = int((time.time() - started) * 1000)
            assistant = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=full,
                selected_mode=request.mode,
                processing_time=elapsed_ms,
            )
            db.add(assistant)
            db.commit()
            db.refresh(assistant)

            yield f"data: {json.dumps({'done': True, 'session_id': session.id, 'message_id': assistant.id, 'processing_time_ms': elapsed_ms}, ensure_ascii=False)}\\n\\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': True, 'message': str(e)}, ensure_ascii=False)}\\n\\n"
        finally:
            await app_state.orchestrator.request_state_change(SystemState.IDLE, reason="chat ask done")

    if request.stream:
        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    # non-streaming fallback
    started = time.time()
    try:
        result = await app_state.orchestrator.run_agent(
            user_input=request.question,
            history=history,
            mode=request.mode,
            persona_id=request.persona_id,
            user_profile_id=request.user_profile_id,
            lore_topic=request.lore_topic,
            character_id=request.character_id,
            world_id=request.world_id,
            scene_id=request.scene_id,
        )
        elapsed_ms = int((time.time() - started) * 1000)
        assistant = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=result.answer or "",
            selected_mode=request.mode,
            processing_time=elapsed_ms,
        )
        db.add(assistant)
        db.commit()
        db.refresh(assistant)
        return {"response": result.answer, "session_id": session.id, "message_id": assistant.id, "processing_time_ms": elapsed_ms}
    finally:
        await app_state.orchestrator.request_state_change(SystemState.IDLE, reason="chat ask done")
