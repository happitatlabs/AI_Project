# database.py — The "Universal Adapter" Version
from datetime import datetime, timedelta, date, timezone
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float, Date, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import sessionmaker, relationship, Session, declarative_base
from pathlib import Path
import os
import enum
from typing import Optional

from mellow_link.infra.env_loader import load_dotenv_early

# [Fix] bcrypt 에러 침묵용 패치
import bcrypt
if not hasattr(bcrypt, '__about__'):
    class MockAbout:
        __version__ = getattr(bcrypt, '__version__', '4.0.0')
    bcrypt.__about__ = MockAbout()

from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Header

# =========================
# Configuration
# =========================

_MELLOW_LINK_DIR = Path(__file__).parent.parent
_FORCED_DATA_DIR = _MELLOW_LINK_DIR / "data"
_FORCED_DATA_DIR.mkdir(parents=True, exist_ok=True)

def _normalize_sqlite_path(path: Path) -> str:
    """Return a Windows-safe absolute path for sqlite URLs."""
    resolved = str(path.resolve())
    if os.name == "nt" and resolved.startswith("\\\\?\\"):
        return resolved[4:]
    return resolved


DB_PATH = _FORCED_DATA_DIR / "aventurine_v3.db"
DATABASE_URL = f"sqlite:///{_normalize_sqlite_path(DB_PATH)}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Ensure JWT secrets in .env are loaded before auth constants are fixed at import time.
load_dotenv_early()
_SECRET_RAW = os.getenv("JWT_SECRET_KEY") or os.getenv("MELLOW_JWT_SECRET")
if not _SECRET_RAW or not str(_SECRET_RAW).strip():
    # 운영 환경에서는 JWT 시크릿 필수 (재시작 시 토큰 무효화 방지)
    if os.getenv("MELLOW_ENV") == "production" or os.getenv("MELLOW_REQUIRE_JWT_SECRET", "").lower() in ("1", "true", "yes"):
        raise RuntimeError(
            "JWT_SECRET_KEY 또는 MELLOW_JWT_SECRET을 설정하세요. "
            "운영 환경에서는 .env에 반드시 설정해야 합니다."
        )
    import secrets
    import warnings
    SECRET_KEY = secrets.token_urlsafe(32)
    warnings.warn(
        "JWT_SECRET_KEY/MELLOW_JWT_SECRET not set; using random key (tokens invalidate on restart).",
        UserWarning,
        stacklevel=2,
    )
else:
    SECRET_KEY = _SECRET_RAW.strip()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

# =========================
# Role Enum
# =========================
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"

# =========================
# Models
# =========================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default=UserRole.USER.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    folders = relationship("AgentFolder", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("UserMemory", back_populates="user", cascade="all, delete-orphan")
    daily_usages = relationship("DailyUsage", back_populates="user", cascade="all, delete-orphan")

class AgentFolder(Base):
    __tablename__ = "agent_folders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    system_prompt = Column(Text, nullable=False)
    use_rag = Column(Boolean, default=False, nullable=False)
    rag_collection_name = Column(String(255), nullable=True)
    icon = Column(String(10), default="📁", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_creative = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="folders")
    sessions = relationship("ChatSession", back_populates="folder")
    documents = relationship("FolderDocument", back_populates="folder", cascade="all, delete-orphan")

class UserMemory(Base):
    __tablename__ = "user_memories"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = relationship("User", back_populates="memories")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    folder_id = Column(Integer, ForeignKey("agent_folders.id"), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="sessions")
    folder = relationship("AgentFolder", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    state_info = Column(String(255), nullable=True)
    evolution_payload = Column(Text, nullable=True)  # full evolution_report JSON when content is derived patch_report
    rag_used = Column(Boolean, default=False, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    auto_selected = Column(Boolean, default=False, nullable=False)
    selected_mode = Column(String(50), nullable=True)
    processing_time = Column(Float, nullable=True)
    session = relationship("ChatSession", back_populates="messages")

class FolderDocument(Base):
    __tablename__ = "folder_documents"
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("agent_folders.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=True, default="")
    file_size = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="processing", nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    folder = relationship("AgentFolder", back_populates="documents")

class MessageFeedback(Base):
    __tablename__ = "message_feedbacks"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    is_positive = Column(Boolean, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    message = relationship("ChatMessage")

class TempResource(Base):
    __tablename__ = "temp_resources"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    temp_session_id = Column(String(255), nullable=False, index=True)
    temp_file_id = Column(String(100), nullable=True, index=True)
    original_filename = Column(String(500), nullable=True, default="")
    file_path = Column(String(1000), nullable=True)
    extracted_relative_path = Column(String(1000), nullable=True, default="")
    file_size = Column(Integer, default=0, nullable=False)
    content_type = Column(String(255), nullable=True, default="")
    collection_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(50), default="UPLOADING", nullable=False)
    stage_status = Column(String(50), default="staged", nullable=False)
    promoted_to_project_id = Column(String(40), nullable=True, index=True)
    retry_count = Column(Integer, default=0, nullable=False)

class EventLog(Base):
    __tablename__ = "event_logs"
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    message = Column(Text, nullable=False)
    context_metadata = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed = Column(Boolean, default=False, nullable=False)

class DailyUsage(Base):
    __tablename__ = "daily_usages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    count = Column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint('user_id', 'date', name='uq_user_date'),)
    user = relationship("User", back_populates="daily_usages")


class DailyState(Base):
    __tablename__ = "daily_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    sleep_hours = Column(Float, nullable=False)
    wake_count = Column(Integer, nullable=False)
    pain_wrist = Column(Integer, nullable=False)
    pain_elbow = Column(Integer, nullable=False)
    pain_back = Column(Integer, nullable=False)
    pain_foot = Column(Integer, nullable=False)
    mood_anxiety = Column(Integer, nullable=False)
    mood_depression = Column(Integer, nullable=False)
    mood_irritation = Column(Integer, nullable=False)
    self_harm_urge = Column(Integer, nullable=False)
    meal_breakfast = Column(Boolean, nullable=False, default=False)
    meal_lunch = Column(Boolean, nullable=False, default=False)
    meal_dinner = Column(Boolean, nullable=False, default=False)
    hydration = Column(Float, nullable=False)
    medication_morning = Column(Boolean, nullable=False, default=False)
    medication_evening = Column(Boolean, nullable=False, default=False)
    energy = Column(Integer, nullable=False)
    daily_brick = Column(String(300), nullable=False, default="")
    daily_brick_completed = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User")
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_daily_states_user_date"),
    )


class GuestUsage(Base):
    __tablename__ = "guest_usages"
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    count = Column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint('ip_address', 'date', name='uq_guest_ip_date'),)


class DocumentChunk(Base):
    """RAG document chunks with embeddings for persistent storage."""
    __tablename__ = "document_chunks"
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("agent_folders.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("folder_documents.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(Text, nullable=False)  # JSON serialized embedding vector
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    folder = relationship("AgentFolder")
    document = relationship("FolderDocument")


class AgentRun(Base):
    """Agent execution run tracking."""
    __tablename__ = "agent_runs"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), unique=True, nullable=False, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    module_id = Column(String(100), nullable=False, default="engine")
    run_kind = Column(String(100), nullable=False, default="generic")
    status = Column(String(50), nullable=False, default="pending")  # pending, running, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    summary = Column(Text, nullable=True)
    
    events = relationship("AgentRunEvent", back_populates="run", cascade="all, delete-orphan", order_by="AgentRunEvent.ts")


class AgentRunEvent(Base):
    """Agent run events for progress tracking."""
    __tablename__ = "agent_run_events"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), ForeignKey("agent_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    ts = Column(Float, nullable=False, index=True)  # Unix timestamp
    type = Column(String(50), nullable=False, index=True)  # run_started, plan_created, todo_started, etc.
    payload_json = Column(Text, nullable=False)  # JSON serialized payload
    
    run = relationship("AgentRun", back_populates="events")


class ModernizationProject(Base):
    """Commercial v1 modernization project wrapper around a single run."""
    __tablename__ = "modernization_projects"

    id = Column(String(40), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    run_id = Column(String(100), nullable=False, unique=True, index=True)
    project_name = Column(String(255), nullable=False)
    client_name = Column(String(255), nullable=False)
    goal_text = Column(Text, nullable=False, default="")
    template_key = Column(String(100), nullable=False, default="default_modernization_v1")
    template_mode = Column(String(20), nullable=False, default="recommended")
    constraints_json = Column(Text, nullable=False, default="[]")
    upload_session_id = Column(String(255), nullable=False)
    asset_manifest_json = Column(Text, nullable=False, default="[]")
    status = Column(String(50), nullable=False, default="running")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ProjectAsset(Base):
    __tablename__ = "project_assets"

    id = Column(String(40), primary_key=True, index=True)
    project_id = Column(String(40), ForeignKey("modernization_projects.id"), nullable=False, index=True)
    source_temp_session_id = Column(String(255), nullable=False, index=True)
    source_temp_file_id = Column(String(100), nullable=False, index=True)
    original_filename = Column(String(500), nullable=False)
    stored_relative_path = Column(String(1000), nullable=False)
    extracted_relative_path = Column(String(1000), nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    content_type = Column(String(255), nullable=True, default="")
    category_hint = Column(String(100), nullable=False, default="")
    extracted_chars = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProjectRunHistory(Base):
    __tablename__ = "project_run_history"

    id = Column(String(40), primary_key=True, index=True)
    project_id = Column(String(40), ForeignKey("modernization_projects.id"), nullable=False, index=True)
    run_id = Column(String(100), nullable=False, index=True)
    sequence_no = Column(Integer, nullable=False)
    trigger_kind = Column(String(20), nullable=False, default="reanalysis")
    asset_manifest_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "sequence_no", name="uq_project_run_history_project_sequence"),
        UniqueConstraint("project_id", "run_id", name="uq_project_run_history_project_run"),
    )


class AnalysisContext(Base):
    __tablename__ = "analysis_contexts"

    context_id = Column(String(120), primary_key=True, index=True)
    project_id = Column(String(40), ForeignKey("modernization_projects.id"), nullable=False, index=True)
    run_id = Column(String(100), nullable=False, unique=True, index=True)
    safe_bundle_id = Column(String(100), nullable=False, default="", index=True)
    input_fingerprint = Column(String(64), nullable=False, index=True)
    schema_version = Column(String(50), nullable=False, default="analysis_context_v1")
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PilotStateRecord(Base):
    """Persistent review, approval, and delivery state for one project run."""

    __tablename__ = "pilot_states"

    pilot_id = Column(String(40), primary_key=True, index=True)
    project_id = Column(
        String(40), ForeignKey("modernization_projects.id"), nullable=False, index=True
    )
    run_id = Column(
        String(100), ForeignKey("agent_runs.run_id"), nullable=False, index=True
    )
    status = Column(String(50), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    review_requested_at = Column(DateTime(timezone=True), nullable=True, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    review_started_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True, index=True)
    delivered_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True, index=True)
    change_request_reason = Column(Text, nullable=True)
    delivery_reference = Column(String(500), nullable=True)
    last_transition_id = Column(String(40), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "run_id", name="uq_pilot_states_project_run"
        ),
        CheckConstraint(
            "status IN ('draft', 'ready_for_review', 'under_review', "
            "'changes_requested', 'approved', 'delivered')",
            name="ck_pilot_states_status",
        ),
        CheckConstraint("version >= 0", name="ck_pilot_states_version"),
    )


class PilotAuditEvent(Base):
    """Append-only audit event written atomically with a Pilot state change."""

    __tablename__ = "pilot_audit_events"

    event_id = Column(String(40), primary_key=True, index=True)
    pilot_id = Column(
        String(40), ForeignKey("pilot_states.pilot_id"), nullable=False, index=True
    )
    project_id = Column(
        String(40), ForeignKey("modernization_projects.id"), nullable=False, index=True
    )
    run_id = Column(
        String(100), ForeignKey("agent_runs.run_id"), nullable=False, index=True
    )
    event_type = Column(String(80), nullable=False, index=True)
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    idempotency_key = Column(String(200), nullable=False)
    result_version = Column(Integer, nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        CheckConstraint(
            "from_status IS NULL OR from_status IN ('draft', 'ready_for_review', "
            "'under_review', 'changes_requested', 'approved', 'delivered')",
            name="ck_pilot_audit_from_status",
        ),
        CheckConstraint(
            "to_status IN ('draft', 'ready_for_review', 'under_review', "
            "'changes_requested', 'approved', 'delivered')",
            name="ck_pilot_audit_to_status",
        ),
        CheckConstraint("result_version >= 0", name="ck_pilot_audit_version"),
    )


class PilotCommandResult(Base):
    """Stored response used to replay an idempotent Pilot command."""

    __tablename__ = "pilot_command_results"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String(200), nullable=False)
    operation = Column(String(80), nullable=False)
    request_hash = Column(String(64), nullable=False)
    pilot_id = Column(
        String(40), ForeignKey("pilot_states.pilot_id"), nullable=False, index=True
    )
    result_version = Column(Integer, nullable=False)
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "actor_id", "idempotency_key", name="uq_pilot_commands_actor_key"
        ),
        CheckConstraint("result_version >= 0", name="ck_pilot_commands_version"),
    )


class DeliveryChecklistTemplate(Base):
    __tablename__ = "delivery_checklist_templates"

    template_id = Column(String(40), primary_key=True, index=True)
    template_key = Column(String(100), nullable=False)
    template_version = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    retired_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "template_key",
            "template_version",
            name="uq_delivery_template_key_version",
        ),
        CheckConstraint("template_version > 0", name="ck_delivery_template_version"),
    )


class DeliveryChecklistTemplateItem(Base):
    __tablename__ = "delivery_checklist_template_items"

    template_item_id = Column(String(40), primary_key=True)
    template_id = Column(
        String(40),
        ForeignKey("delivery_checklist_templates.template_id"),
        nullable=False,
        index=True,
    )
    item_key = Column(String(100), nullable=False)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    requirement = Column(String(20), nullable=False)
    artifact_type = Column(String(50), nullable=False)
    source = Column(String(100), nullable=False)
    waiver_allowed = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "template_id", "item_key", name="uq_delivery_template_item_key"
        ),
        CheckConstraint(
            "requirement IN ('required', 'optional')",
            name="ck_delivery_template_item_requirement",
        ),
        CheckConstraint("sort_order >= 0", name="ck_delivery_template_item_order"),
    )


class DeliveryChecklist(Base):
    __tablename__ = "delivery_checklists"

    checklist_id = Column(String(40), primary_key=True, index=True)
    pilot_id = Column(
        String(40), ForeignKey("pilot_states.pilot_id"), nullable=False, index=True
    )
    project_id = Column(
        String(40), ForeignKey("modernization_projects.id"), nullable=False, index=True
    )
    run_id = Column(
        String(100), ForeignKey("agent_runs.run_id"), nullable=False, index=True
    )
    template_id = Column(
        String(40),
        ForeignKey("delivery_checklist_templates.template_id"),
        nullable=False,
    )
    template_version = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "pilot_id",
            "template_id",
            "template_version",
            name="uq_delivery_checklist_pilot_template",
        ),
        CheckConstraint("version >= 0", name="ck_delivery_checklist_version"),
    )


class DeliveryChecklistItem(Base):
    __tablename__ = "delivery_checklist_items"

    checklist_item_id = Column(String(40), primary_key=True)
    checklist_id = Column(
        String(40),
        ForeignKey("delivery_checklists.checklist_id"),
        nullable=False,
        index=True,
    )
    item_key = Column(String(100), nullable=False)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    requirement = Column(String(20), nullable=False)
    artifact_type = Column(String(50), nullable=False)
    source = Column(String(100), nullable=False)
    waiver_allowed = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, index=True)
    artifact_ref = Column(String(100), nullable=True)
    artifact_fingerprint = Column(String(64), nullable=True)
    verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    waived_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    waived_at = Column(DateTime(timezone=True), nullable=True)
    waiver_reason = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "checklist_id", "item_key", name="uq_delivery_checklist_item_key"
        ),
        CheckConstraint(
            "requirement IN ('required', 'optional')",
            name="ck_delivery_checklist_item_requirement",
        ),
        CheckConstraint(
            "status IN ('pending', 'present', 'missing', 'waived', 'invalid', 'stale')",
            name="ck_delivery_checklist_item_status",
        ),
        CheckConstraint("version >= 0", name="ck_delivery_checklist_item_version"),
        CheckConstraint("sort_order >= 0", name="ck_delivery_checklist_item_order"),
    )


class DeliveryPackageAssembly(Base):
    __tablename__ = "delivery_package_assemblies"

    assembly_id = Column(String(40), primary_key=True, index=True)
    pilot_id = Column(
        String(40), ForeignKey("pilot_states.pilot_id"), nullable=False, index=True
    )
    checklist_id = Column(
        String(40), ForeignKey("delivery_checklists.checklist_id"), nullable=False
    )
    project_id = Column(
        String(40), ForeignKey("modernization_projects.id"), nullable=False, index=True
    )
    run_id = Column(
        String(100), ForeignKey("agent_runs.run_id"), nullable=False, index=True
    )
    status = Column(String(20), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=0)
    attempt = Column(Integer, nullable=False, default=1)
    request_fingerprint = Column(String(64), nullable=False, unique=True, index=True)
    source_pilot_version = Column(Integer, nullable=False)
    checklist_version = Column(Integer, nullable=False)
    template_version = Column(Integer, nullable=False)
    artifact_set_fingerprint = Column(String(64), nullable=False)
    manifest_version = Column(String(50), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    failure_code = Column(String(80), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'assembling', 'assembled', 'failed', 'superseded')",
            name="ck_delivery_assembly_status",
        ),
        CheckConstraint("version >= 0", name="ck_delivery_assembly_version"),
        CheckConstraint(
            "attempt >= 1 AND attempt <= 3", name="ck_delivery_assembly_attempt"
        ),
    )


class DeliveryPackage(Base):
    __tablename__ = "delivery_packages"

    package_id = Column(String(40), primary_key=True, index=True)
    assembly_id = Column(
        String(40),
        ForeignKey("delivery_package_assemblies.assembly_id"),
        nullable=False,
        unique=True,
    )
    pilot_id = Column(
        String(40), ForeignKey("pilot_states.pilot_id"), nullable=False, index=True
    )
    project_id = Column(
        String(40), ForeignKey("modernization_projects.id"), nullable=False, index=True
    )
    run_id = Column(
        String(100), ForeignKey("agent_runs.run_id"), nullable=False, index=True
    )
    status = Column(String(20), nullable=False, index=True)
    manifest_version = Column(String(50), nullable=False)
    manifest_json = Column(Text, nullable=False)
    artifact_reference = Column(String(100), nullable=False, unique=True)
    byte_size = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('assembled', 'superseded')",
            name="ck_delivery_package_status",
        ),
        CheckConstraint("byte_size >= 0", name="ck_delivery_package_size"),
    )


class DeliveryAuditEvent(Base):
    __tablename__ = "delivery_audit_events"

    event_id = Column(String(40), primary_key=True, index=True)
    pilot_id = Column(
        String(40), ForeignKey("pilot_states.pilot_id"), nullable=False, index=True
    )
    project_id = Column(
        String(40), ForeignKey("modernization_projects.id"), nullable=False, index=True
    )
    run_id = Column(
        String(100), ForeignKey("agent_runs.run_id"), nullable=False, index=True
    )
    checklist_id = Column(String(40), nullable=True, index=True)
    assembly_id = Column(String(40), nullable=True, index=True)
    package_id = Column(String(40), nullable=True, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    idempotency_key = Column(String(200), nullable=True)
    result_version = Column(Integer, nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        CheckConstraint("result_version >= 0", name="ck_delivery_audit_version"),
    )


class DeliveryCommandResult(Base):
    __tablename__ = "delivery_command_results"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String(200), nullable=False)
    operation = Column(String(80), nullable=False)
    request_hash = Column(String(64), nullable=False)
    resource_type = Column(String(40), nullable=False)
    resource_id = Column(String(40), nullable=False, index=True)
    result_version = Column(Integer, nullable=False)
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "actor_id", "idempotency_key", name="uq_delivery_commands_actor_key"
        ),
        CheckConstraint("result_version >= 0", name="ck_delivery_command_version"),
    )


class DeliveryDownloadReference(Base):
    __tablename__ = "delivery_download_references"

    reference_id = Column(String(40), primary_key=True)
    package_id = Column(
        String(40),
        ForeignKey("delivery_packages.package_id"),
        nullable=False,
        index=True,
    )
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_digest = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)


# =========================
# Helper Functions
# =========================

def init_db():
    Base.metadata.create_all(bind=engine)
    # Migration: FolderDocument file_size, status (기존 DB 호환)
    from sqlalchemy import text
    for col_sql in [
        "ALTER TABLE folder_documents ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE folder_documents ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'processing'",
        "ALTER TABLE chat_messages ADD COLUMN evolution_payload TEXT",
        "ALTER TABLE agent_runs ADD COLUMN module_id VARCHAR(100) NOT NULL DEFAULT 'engine'",
        "ALTER TABLE agent_runs ADD COLUMN run_kind VARCHAR(100) NOT NULL DEFAULT 'generic'",
        "ALTER TABLE modernization_projects ADD COLUMN goal_text TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE temp_resources ADD COLUMN user_id INTEGER",
        "ALTER TABLE temp_resources ADD COLUMN temp_file_id VARCHAR(100)",
        "ALTER TABLE temp_resources ADD COLUMN original_filename VARCHAR(500) DEFAULT ''",
        "ALTER TABLE temp_resources ADD COLUMN extracted_relative_path VARCHAR(1000) DEFAULT ''",
        "ALTER TABLE temp_resources ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE temp_resources ADD COLUMN content_type VARCHAR(255) DEFAULT ''",
        "ALTER TABLE temp_resources ADD COLUMN stage_status VARCHAR(50) NOT NULL DEFAULT 'staged'",
        "ALTER TABLE temp_resources ADD COLUMN promoted_to_project_id VARCHAR(40)",
    ]:
        try:
            with engine.connect() as conn:
                conn.execute(text(col_sql))
                conn.commit()
        except Exception:
            pass  # column already exists or non-SQLite
    
    # Create indexes for agent_run_events
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_run_events_run_ts ON agent_run_events(run_id, ts)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_runs_module_kind ON agent_runs(module_id, run_kind)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_modernization_projects_user_created ON modernization_projects(user_id, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_modernization_projects_status ON modernization_projects(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_temp_resources_session_file ON temp_resources(temp_session_id, temp_file_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_temp_resources_temp_file_id ON temp_resources(temp_file_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_project_assets_project_created ON project_assets(project_id, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_project_assets_source_file ON project_assets(source_temp_file_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_project_run_history_project_sequence ON project_run_history(project_id, sequence_no)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_project_run_history_project_created ON project_run_history(project_id, created_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_analysis_contexts_project ON analysis_contexts(project_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_analysis_contexts_input_fingerprint ON analysis_contexts(input_fingerprint)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_analysis_contexts_safe_bundle ON analysis_contexts(safe_bundle_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_states_user_date ON daily_states(user_id, date)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_daily_states_user_date ON daily_states(user_id, date)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_pilot_states_status_updated ON pilot_states(status, updated_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_pilot_audit_pilot_occurred ON pilot_audit_events(pilot_id, occurred_at)"))
            conn.commit()
    except Exception:
        pass  # index already exists

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# [수정됨] role 인자를 받도록 수정 (main.py 호환성)
def create_default_folders_for_user(db: Session, user_id: int, role: str = UserRole.USER.value):
    """회원가입 시 기본 폴더 생성"""
    default_folders = [
        {"name": "일반 대화", "icon": "💬", "system_prompt": "친절한 AI.", "use_rag": True, "rag_collection_name": None},
    ]
    # Admin일 경우 추가 폴더 (선택사항)
    if role == UserRole.ADMIN.value:
        default_folders.insert(0, {"name": "비서", "icon": "🎀", "system_prompt": "비서 모드", "use_rag": True, "rag_collection_name": None})

    created = []
    for folder_data in default_folders:
        folder = AgentFolder(user_id=user_id, **folder_data)
        db.add(folder)
        created.append(folder)
    db.commit()
    for f in created: db.refresh(f)
    return created

def ensure_user_has_folders(db: Session, user_id: int, role: str = UserRole.USER.value) -> list:
    """사용자에게 폴더가 없으면 기본 폴더 생성"""
    count = db.query(AgentFolder).filter(AgentFolder.user_id == user_id, AgentFolder.is_active == True).count()
    if count == 0:
        return create_default_folders_for_user(db, user_id, role)
    return db.query(AgentFolder).filter(AgentFolder.user_id == user_id, AgentFolder.is_active == True).all()

def get_or_create_default_session(db: Session, user_id: int, folder_id: int) -> "ChatSession":
    existing = db.query(ChatSession).filter(
        ChatSession.user_id == user_id, 
        ChatSession.folder_id == folder_id, 
        ChatSession.is_active == True
    ).first()
    
    if existing: return existing
    
    folder = db.query(AgentFolder).filter(AgentFolder.id == folder_id).first()
    folder_name = folder.name if folder else "Folder"
    
    session = ChatSession(
        user_id=user_id, 
        folder_id=folder_id, 
        title=f"Chat in {folder_name}", 
        is_active=True
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

# =========================
# Auth & Guest Functions
# =========================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash. No plaintext fallback (security)."""
    try:
        if pwd_context.verify(plain_password, hashed_password):
            return True
    except Exception:
        pass
    # Fallback: passlib와 bcrypt 라이브러리 호환 이슈 시 bcrypt 직접 검증
    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt
            pw_bytes = plain_password.encode("utf-8")
            h_bytes = hashed_password.encode("utf-8") if isinstance(hashed_password, str) else hashed_password
            return bool(bcrypt.checkpw(pw_bytes, h_bytes))
        except Exception:
            pass
    return False


def get_password_hash(password: str) -> str:
    """Hash password. No plaintext fallback (security)."""
    try:
        return pwd_context.hash(password)
    except Exception:
        import bcrypt
        password_bytes = password.encode("utf-8")
        return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

def create_access_token(data: dict, expires_delta: timedelta = None, role: str = UserRole.USER.value):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire, "role": role})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_optional(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization: return None
    try:
        token = authorization.replace("Bearer ", "").strip()
        if not token: return None
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username: return None
    except JWTError: return None
    return db.query(User).filter(User.username == username).first()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=401, detail="Not authenticated")
    if not token or not token.strip():
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username: raise credentials_exception
    except JWTError: raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if not user: raise credentials_exception
    return user

def get_or_create_guest_user(db: Session) -> User:
    import uuid
    guest_username = f"guest_{uuid.uuid4().hex[:8]}"
    guest_user = User(username=guest_username, hashed_password=get_password_hash("guest"), role=UserRole.GUEST.value)
    db.add(guest_user)
    db.commit()
    db.refresh(guest_user)
    return guest_user

def get_token_payload(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError: return {}

def get_guest_usage_today(db: Session, ip_address: str) -> int:
    today = date.today()
    usage = db.query(GuestUsage).filter(GuestUsage.ip_address == ip_address, GuestUsage.date == today).first()
    return usage.count if usage else 0

def increment_guest_usage(db: Session, ip_address: str) -> int:
    today = date.today()
    usage = db.query(GuestUsage).filter(GuestUsage.ip_address == ip_address, GuestUsage.date == today).first()
    if usage:
        usage.count += 1
    else:
        usage = GuestUsage(ip_address=ip_address, date=today, count=1)
        db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage.count

def check_guest_limit(db: Session, ip_address: str, limit: int) -> tuple:
    if limit == -1: return True, 0
    cnt = get_guest_usage_today(db, ip_address)
    return cnt < limit, cnt

# Init DB
init_db()
