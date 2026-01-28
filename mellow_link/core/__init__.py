"""
Core Module - Mellow-Link Orchestration System

This module contains the core logic for the AI orchestration system:
- State management (FSM)
- Event-driven messaging
- Main orchestrator coordination
- Request/Response schemas
- Security & Admin bootstrapping
"""

from .states import SystemState, TaskPriority, TransitionResult
from .events import Event, TaskEvent, StateChangeEvent, EventType
from .orchestrator import Orchestrator, ChatContext
from .schemas import ImageRequest
from .security import (
    bootstrap_admin_account,
    check_admin_exists,
    create_admin_user,
    get_admin_user,
    safe_get_password_hash,
    is_admin_user,
    is_superuser,
)

__all__ = [
    # States
    "SystemState",
    "TaskPriority",
    "TransitionResult",
    # Events
    "Event",
    "TaskEvent",
    "StateChangeEvent",
    "EventType",
    # Orchestrator
    "Orchestrator",
    "ChatContext",
    # Schemas
    "ImageRequest",
    # Security
    "bootstrap_admin_account",
    "check_admin_exists",
    "create_admin_user",
    "get_admin_user",
    "safe_get_password_hash",
    "is_admin_user",
    "is_superuser",
]
