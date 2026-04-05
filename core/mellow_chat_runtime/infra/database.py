from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker


def _workspace_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[2],  # before move: AI_Project
        Path(__file__).resolve().parents[3],  # after move: AI_Project
        Path.cwd().resolve(),
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "core" / "mellow_chat_runtime").exists():
            return resolved
        if resolved.name == "core" and (resolved / "mellow_chat_runtime").exists():
            return resolved.parent
        if (resolved / "mellow_chat_runtime").exists():
            return resolved
    return Path.cwd().resolve()


_ROOT = _workspace_root()
_LEGACY_DATA_DIR = _ROOT / "mellow_chat_runtime_data"
_ROLE_DATA_DIR = _ROOT / "data" / "runtime" / "mellow_chat_runtime_data"
DATA_DIR = _ROLE_DATA_DIR if _ROLE_DATA_DIR.exists() or (not _LEGACY_DATA_DIR.exists() and (_ROOT / "core").exists()) else _LEGACY_DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "chatbot.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(120), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sessions = relationship("ChatSession", back_populates="user")


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False, default="New Chat")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    selected_mode = Column(String(50), nullable=True)
    processing_time = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")


class MessageFeedback(Base):
    __tablename__ = "message_feedback"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    is_positive = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_or_create_user(db: Session, username: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    user = User(username=username)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_session(db: Session, user_id: int, session_id: int | None = None) -> ChatSession:
    if session_id:
        found = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id, ChatSession.is_active == True).first()
        if found:
            return found
    session = ChatSession(user_id=user_id, title="New Chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
