"""
Services Module - Mellow-Link

This module contains service implementations for:
- LLM inference (Ollama)
- Image generation (ComfyUI)
- Document generation (CPU-based)
- VTuber avatar relay (WebSocket)
- RAG (Retrieval-Augmented Generation)

All services implement a common interface for orchestrator integration.
"""

from .llm_service import LLMService, create_llm_service
from .image_service import ImageService, create_image_service
from .doc_service import DocumentService, DocumentRequest, DocumentType, create_document_service
from .vtuber_relay import (
    VTuberRelayService,
    VTuberConnectionStatus,
    VTuberMessage,
    VTuberStatus,
    create_vtuber_relay,
    get_vtuber_relay,
    set_vtuber_relay,
)
from .rag_service import (
    RAGService,
    RAGSearchResult,
    TempChunk,
    create_rag_service,
    get_rag_service,
    set_rag_service,
)
from datetime import datetime  # <-- 이 녀석이 없으면 저장할 때 500 에러 터짐!
import random                  # <-- 이 녀석이 없으면 시드(Seed) 만들 때 터짐!

__all__ = [
    # LLM Service
    "LLMService",
    "create_llm_service",
    # Image Service
    "ImageService",
    "create_image_service",
    # Document Service
    "DocumentService",
    "DocumentRequest",
    "DocumentType",
    "create_document_service",
    # VTuber Relay
    "VTuberRelayService",
    "VTuberConnectionStatus",
    "VTuberMessage",
    "VTuberStatus",
    "create_vtuber_relay",
    "get_vtuber_relay",
    "set_vtuber_relay",
    # RAG Service
    "RAGService",
    "RAGSearchResult",
    "TempChunk",
    "create_rag_service",
    "get_rag_service",
    "set_rag_service",
]
