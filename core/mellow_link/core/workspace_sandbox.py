"""
Workspace Sandbox - 자율 에이전트 전용 작업 구역 제어.

지침: mellow_link/workspace/ 폴더 내로만 파일 쓰기 허용.
core/, config/, .env 등은 절대 수정 불가 (읽기만 허용).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 코어 보호: 수정 금지 경로 (자율 에이전트는 쓰기 불가)
_PROTECTED_WRITE_ROOTS = ("core", "infra", "config", "evolution", "main.py")
_PROTECTED_FILES = (".env", "config.py", "settings.py")

# 자율 작업 허용 구역
WORKSPACE_SUBDIR = "workspace"

def _compute_workspace_root() -> Path:
    """
    현재 실행 중인 repo 기준 workspace 루트를 계산한다.

    우선순위:
    1. MELLOW_LINK_PROJECT_ROOT / PROJECT_ROOT
    2. 현재 파일 위치 기준 mellow_link 루트
    """
    root_hint = Path(
        (
            __import__("os").environ.get("MELLOW_LINK_PROJECT_ROOT")
            or __import__("os").environ.get("PROJECT_ROOT")
            or ""
        )
    )
    if str(root_hint).strip():
        base = root_hint.resolve()
        if (base / "core").exists() and (base / "config").exists():
            return (base / WORKSPACE_SUBDIR).resolve()
        if (base / "mellow_link" / "core").exists() and (base / "mellow_link" / "config").exists():
            return (base / "mellow_link" / WORKSPACE_SUBDIR).resolve()
    return (Path(__file__).resolve().parents[1] / WORKSPACE_SUBDIR).resolve()


_WORKSPACE_ROOT_CONSTANT = _compute_workspace_root()


class WorkspaceSandboxError(PermissionError):
    """workspace 샌드박스 정책 위반."""


def get_workspace_root() -> Path:
    """
    mellow_link/workspace 절대 경로 반환.
    repo 루트 또는 명시적 프로젝트 루트 환경변수 기준으로 계산한다.
    """
    _WORKSPACE_ROOT_CONSTANT.mkdir(parents=True, exist_ok=True)
    return _WORKSPACE_ROOT_CONSTANT


def resolve_workspace_path(rel_path: str, base: Optional[Path] = None) -> Optional[Path]:
    """
    상대 경로를 workspace 내 절대 경로로 변환.
    경로 탈출(..) 시도 시 None 반환.
    """
    root = base or get_workspace_root()
    if ".." in rel_path:
        return None
    path = (root / rel_path.lstrip("/")).resolve()
    try:
        path.relative_to(root)
        return path
    except ValueError:
        return None


def can_write_to_path(target: str | Path, sandbox_root: Optional[Path] = None) -> Tuple[bool, str]:
    """
    자율 에이전트가 해당 경로에 쓰기할 수 있는지 검사.
    
    Returns:
        (허용 여부, 거부 사유)
    """
    base = sandbox_root or Path(__file__).resolve().parents[1]
    path = Path(target)
    if not path.is_absolute():
        path = (base / target).resolve()
    
    try:
        rel = path.relative_to(base)
    except ValueError:
        return False, "sandbox 루트 밖의 경로"
    
    parts = rel.parts
    if not parts:
        return False, "잘못된 경로"
    
    # 코어 보호: 수정 금지
    first = parts[0].lower()
    for protected in _PROTECTED_WRITE_ROOTS:
        if first == protected.lower():
            return False, f"core 보호: {first}/ 수정 금지"
    
    if path.name.lower() in (f.lower() for f in _PROTECTED_FILES):
        return False, f"core 보호: {path.name} 수정 금지"
    
    # workspace/ 내에서만 쓰기 허용
    if first != WORKSPACE_SUBDIR:
        return False, f"작업 구역 제한: {WORKSPACE_SUBDIR}/ 내에서만 쓰기 허용"
    
    return True, ""


def ensure_workspace_safe_path(rel_path: str) -> Optional[Path]:
    """
    workspace 내 안전한 경로 반환. 탈출 시도 시 None.
    """
    return resolve_workspace_path(rel_path)
