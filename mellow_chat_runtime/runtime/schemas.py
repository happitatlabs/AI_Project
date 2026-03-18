from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class TurnRequestUser(BaseModel):
    id: str


class TurnRequestInput(BaseModel):
    text: str
    locale: Optional[str] = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("input.text must not be blank")
        return value


class TurnRequestContext(BaseModel):
    character_id: Optional[str] = "default"
    model_tier_requested: Optional[str] = "free"
    client_turn_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TurnRequest(BaseModel):
    session_id: str
    user: TurnRequestUser
    input: TurnRequestInput
    context: Optional[TurnRequestContext] = None


class TurnClarify(BaseModel):
    question: str
    reason: Optional[str] = None
    options: List[str] = Field(default_factory=list)


class TurnPayload(BaseModel):
    id: str
    speech: str
    passage: Optional[str]
    ooc: Optional[str]
    clarify: Optional[TurnClarify]


class TurnState(BaseModel):
    session_id: str
    state_version: int
    system_state: str
    model_tier_effective: str


class TurnMeta(BaseModel):
    trace_id: str
    runtime_impl: str
    latency_ms: Optional[float]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TurnResponse(BaseModel):
    turn: TurnPayload
    state: TurnState
    meta: TurnMeta


class StatusRuntime(BaseModel):
    impl: str
    version: str
    uptime_sec: float


class StatusHealth(BaseModel):
    system_state: str
    last_error: Optional[str]
    degraded: bool


class StatusResponse(BaseModel):
    runtime: StatusRuntime
    health: StatusHealth
    time: datetime = Field(default_factory=datetime.utcnow)


class ErrorDetail(BaseModel):
    code: str
    message: str
    trace_id: Optional[str]


class ErrorBody(BaseModel):
    error: ErrorDetail
