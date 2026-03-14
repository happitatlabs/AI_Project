"""
런처 환경 설정: 시크릿 마스킹, 환경 변수 유틸, FFmpeg PATH 설정.
"""
import os
import sys
from pathlib import Path


def mask_secret(val: str) -> str:
    """키 원문 유출 방지: 존재 여부 + 마스킹만 출력."""
    val = (val or "").strip()
    if not val:
        return ""
    if len(val) <= 10:
        return val[:3] + "..."
    return val[:12] + "..." + val[-6:]


def is_truthy_env(name: str, default: bool = False) -> bool:
    """환경 변수가 truthy 값(1, true, yes, y, on)인지 확인."""
    v = os.environ.get(name)
    if not isinstance(v, str):
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_int_env(name: str, default: int) -> int:
    """환경 변수를 정수로 파싱."""
    v = os.environ.get(name)
    if not isinstance(v, str) or not v.strip():
        return default
    try:
        return int(v.strip())
    except Exception:
        return default


def setup_environment(base_dir: Path) -> None:
    """
    런처 실행 시 환경 변수를 설정합니다.
    FFmpeg 경로를 시스템 PATH에 추가 (프로세스 내 임시 등록)
    """
    vtuber_dir = base_dir / "Open-LLM-VTuber"
    ffmpeg_dir = str(vtuber_dir.absolute())

    current_path = os.environ.get("PATH", "")

    if ffmpeg_dir not in current_path:
        separator = ";" if sys.platform == "win32" else ":"
        new_path = f"{ffmpeg_dir}{separator}{current_path}"
        os.environ["PATH"] = new_path
        print(f"✅ FFmpeg 경로 추가됨: {ffmpeg_dir}")
    else:
        print(f"ℹ️  FFmpeg 경로가 이미 설정되어 있습니다.")


def run_launcher_check() -> None:
    """입구 컷: MOLTBOOK_API_KEY 존재 여부 출력 (마스킹)."""
    moltbook_env_key = os.getenv("MOLTBOOK_API_KEY") or ""
    print(
        "[LauncherCheck] MOLTBOOK_API_KEY:",
        "SET" if moltbook_env_key.strip() else "MISSING",
        mask_secret(moltbook_env_key),
    )
