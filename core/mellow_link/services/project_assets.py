from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path


DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
TEMP_UPLOADS_ROOT = DATA_ROOT / "temp_uploads"
PROJECT_ASSETS_ROOT = DATA_ROOT / "project_assets"


def make_temp_file_id() -> str:
    return f"tempf_{uuid.uuid4().hex}"


def make_project_asset_id() -> str:
    return f"asset_{uuid.uuid4().hex[:12]}"


def ensure_storage_roots() -> None:
    TEMP_UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECT_ASSETS_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return cleaned.strip("._") or "unknown"


def _to_relative(path: Path) -> str:
    return path.resolve().relative_to(DATA_ROOT.resolve()).as_posix()


def _resolve_under(relative_path: str, base_dir: Path) -> Path:
    candidate = (DATA_ROOT / str(relative_path or "")).resolve()
    resolved_base = base_dir.resolve()
    if resolved_base not in candidate.parents and candidate != resolved_base:
        raise FileNotFoundError("Path escapes storage root")
    return candidate


def stage_temp_upload(
    *,
    session_id: str,
    temp_file_id: str,
    content_bytes: bytes,
    extracted_text: str,
) -> dict[str, str]:
    ensure_storage_roots()
    stage_dir = TEMP_UPLOADS_ROOT / _safe_segment(session_id) / _safe_segment(temp_file_id)
    stage_dir.mkdir(parents=True, exist_ok=True)
    source_path = stage_dir / "source"
    extracted_path = stage_dir / "extracted.txt"
    source_path.write_bytes(content_bytes)
    extracted_path.write_text(extracted_text, encoding="utf-8")
    return {
        "file_path": _to_relative(source_path),
        "extracted_relative_path": _to_relative(extracted_path),
    }


def promote_staged_asset(
    *,
    project_id: str,
    asset_id: str,
    staged_file_path: str,
    staged_extracted_path: str,
) -> dict[str, str]:
    ensure_storage_roots()
    source_path = resolve_temp_upload_path(staged_file_path)
    extracted_path = resolve_temp_upload_path(staged_extracted_path)
    asset_dir = PROJECT_ASSETS_ROOT / _safe_segment(project_id) / _safe_segment(asset_id)
    asset_dir.mkdir(parents=True, exist_ok=True)
    project_source = asset_dir / "source"
    project_extracted = asset_dir / "extracted.txt"
    shutil.copy2(source_path, project_source)
    shutil.copy2(extracted_path, project_extracted)
    return {
        "stored_relative_path": _to_relative(project_source),
        "extracted_relative_path": _to_relative(project_extracted),
    }


def cleanup_project_asset_dir(project_id: str, asset_id: str) -> None:
    asset_dir = PROJECT_ASSETS_ROOT / _safe_segment(project_id) / _safe_segment(asset_id)
    if asset_dir.exists():
        shutil.rmtree(asset_dir, ignore_errors=True)
    project_dir = asset_dir.parent
    if project_dir.exists():
        try:
            project_dir.rmdir()
        except OSError:
            pass


def cleanup_staged_upload(session_id: str, temp_file_id: str) -> None:
    stage_dir = TEMP_UPLOADS_ROOT / _safe_segment(session_id) / _safe_segment(temp_file_id)
    if stage_dir.exists():
        shutil.rmtree(stage_dir, ignore_errors=True)
    session_dir = stage_dir.parent
    if session_dir.exists():
        try:
            session_dir.rmdir()
        except OSError:
            pass


def resolve_temp_upload_path(relative_path: str) -> Path:
    return _resolve_under(relative_path, TEMP_UPLOADS_ROOT)


def resolve_project_asset_path(relative_path: str) -> Path:
    return _resolve_under(relative_path, PROJECT_ASSETS_ROOT)


def read_text(relative_path: str, *, project_asset: bool) -> str:
    path = resolve_project_asset_path(relative_path) if project_asset else resolve_temp_upload_path(relative_path)
    return path.read_text(encoding="utf-8")


def build_temp_context(parts: list[tuple[str, str]]) -> str:
    blocks = []
    for filename, extracted_text in parts:
        blocks.append(f"===== ASSET: {filename} =====\n{extracted_text}")
    return "\n\n".join(blocks)
