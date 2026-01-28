"""
Infrastructure Module - Mellow-Link

This module contains infrastructure components:
- GPU/VRAM monitoring
- System resource management
- Hardware abstraction layer
- Event logging (JSONL + DB)
- Database models & authentication
"""

from .watchdog import VRAMWatchdog, VRAMStatus, create_watchdog
from .event_logger import log_event, log_intent, SBMA_INTENTS, EVENTS_DIR, EVENTS_FILE
from .database import (
    # Engine & Session
    engine,
    SessionLocal,
    Base,
    init_db,
    get_db,
    # Role Enum
    UserRole,
    # Models
    User,
    AgentFolder,
    UserMemory,
    ChatSession,
    ChatMessage,
    FolderDocument,
    MessageFeedback,
    TempResource,
    EventLog,
    DailyUsage,
    GuestUsage,
    DocumentChunk,
    # Helper Functions
    create_default_folders_for_user,
    ensure_user_has_folders,
    get_or_create_default_session,
    # Auth Functions
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    get_current_user_optional,
    get_or_create_guest_user,
    get_token_payload,
    # Guest Functions
    get_guest_usage_today,
    increment_guest_usage,
    check_guest_limit,
    # Constants
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

__all__ = [
    # Watchdog
    "VRAMWatchdog",
    "VRAMStatus",
    "create_watchdog",
    # Event Logger
    "log_event",
    "log_intent",
    "SBMA_INTENTS",
    "EVENTS_DIR",
    "EVENTS_FILE",
    # Database Engine & Session
    "engine",
    "SessionLocal",
    "Base",
    "init_db",
    "get_db",
    # Role Enum
    "UserRole",
    # Models
    "User",
    "AgentFolder",
    "UserMemory",
    "ChatSession",
    "ChatMessage",
    "FolderDocument",
    "MessageFeedback",
    "TempResource",
    "EventLog",
    "DailyUsage",
    "GuestUsage",
    "DocumentChunk",
    # Helper Functions
    "create_default_folders_for_user",
    "ensure_user_has_folders",
    "get_or_create_default_session",
    # Auth Functions
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "get_current_user",
    "get_current_user_optional",
    "get_or_create_guest_user",
    "get_token_payload",
    # Guest Functions
    "get_guest_usage_today",
    "increment_guest_usage",
    "check_guest_limit",
    # Constants
    "ACCESS_TOKEN_EXPIRE_MINUTES",
]
