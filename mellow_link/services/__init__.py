"""
Services Module - Mellow-Link

중요:
  이 패키지는 일부 서비스(예: auth/crypto/RAG/DB)가 옵션 의존성(bcrypt 등)을 가질 수 있다.
  따라서 __init__.py에서 "모든 서비스"를 즉시 import 하면,
  ImageService/VideoService만 필요한 환경에서도 불필요한 ImportError가 발생한다.

정책:
  - ImageService / VideoService는 항상 즉시 import (TUI 핵심 경로)
  - 그 외 서비스는 attribute access 시점에만 지연 import (PEP 562)
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, Tuple

# --- Always-available core services (TUI needs only these) ---
from .image_service import ImageService, create_image_service
from .video_service import VideoService, create_video_service

__all__ = [
    "ImageService",
    "create_image_service",
    "VideoService",
    "create_video_service",
]

# --- Optional services (lazy) ---
_OPTIONAL_EXPORTS: Dict[str, Tuple[str, str]] = {
    # LLM
    "LLMService": (".llm_service", "LLMService"),
    "create_llm_service": (".llm_service", "create_llm_service"),
    # Document
    "DocumentService": (".doc_service", "DocumentService"),
    "DocumentRequest": (".doc_service", "DocumentRequest"),
    "DocumentType": (".doc_service", "DocumentType"),
    "create_document_service": (".doc_service", "create_document_service"),
    # VTuber Relay
    "VTuberRelayService": (".vtuber_relay", "VTuberRelayService"),
    "VTuberConnectionStatus": (".vtuber_relay", "VTuberConnectionStatus"),
    "VTuberMessage": (".vtuber_relay", "VTuberMessage"),
    "VTuberStatus": (".vtuber_relay", "VTuberStatus"),
    "create_vtuber_relay": (".vtuber_relay", "create_vtuber_relay"),
    "get_vtuber_relay": (".vtuber_relay", "get_vtuber_relay"),
    "set_vtuber_relay": (".vtuber_relay", "set_vtuber_relay"),
    # RAG
    "RAGService": (".rag_service", "RAGService"),
    "RAGSearchResult": (".rag_service", "RAGSearchResult"),
    "TempChunk": (".rag_service", "TempChunk"),
    "create_rag_service": (".rag_service", "create_rag_service"),
    "get_rag_service": (".rag_service", "get_rag_service"),
    "set_rag_service": (".rag_service", "set_rag_service"),
}


def __getattr__(name: str) -> Any:
    """
    지연 import로 옵션 서비스 노출.

    옵션 의존성이 없는 환경에서는 Image/Video만 사용 가능해야 한다.
    """
    target = _OPTIONAL_EXPORTS.get(name)
    if not target:
        raise AttributeError(name)
    module_name, attr_name = target
    try:
        mod = import_module(module_name, __name__)
        return getattr(mod, attr_name)
    except Exception as e:
        raise ImportError(
            f"mellow_link.services.{name} 는 옵션 서비스입니다. "
            f"현재 환경에서 해당 의존성이 누락되었을 수 있습니다. (원인: {type(e).__name__}: {e})"
        ) from e


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(_OPTIONAL_EXPORTS.keys()))
