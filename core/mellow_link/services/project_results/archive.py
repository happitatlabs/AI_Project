from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy.orm import Session

from mellow_link.infra import ModernizationProject


def build_project_result_archive_paths(
    *, archive_root: Path, project_id: str, run_id: str
) -> dict[str, Path]:
    archive_dir = (
        archive_root / (project_id or "unknown_project") / (run_id or "unknown_run")
    )
    return {
        "dir": archive_dir,
        "markdown": archive_dir / "result.md",
        "docx": archive_dir / "result.docx",
        "external_docx": archive_dir / "external_result.docx",
    }


async def persist_project_result_archive(
    project: ModernizationProject,
    *,
    run_id: str,
    db: Session,
    archive_root: Path,
    logger: Any,
    get_run_snapshot_fn: Callable[..., dict[str, Any] | None],
    get_run_events_fn: Callable[..., list[dict[str, Any]]],
    extract_structured_result_fn: Callable[[list[dict[str, Any]]], Any],
    build_assets_payload_fn: Callable[..., list[dict[str, Any]]],
    build_result_package_fn: Callable[..., dict[str, Any]],
    extract_polish_bundle_fn: Callable[..., dict[str, Any] | None],
    result_package_markdown_fn: Callable[..., str],
    generate_result_package_docx_fn: Callable[..., Awaitable[tuple[Path, str]]],
    assets: list[dict[str, Any]] | None = None,
    app_version: str | None = None,
    result_package: dict[str, Any] | None = None,
    docx_source_path: Path | None = None,
) -> dict[str, str]:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return {}

    snapshot = get_run_snapshot_fn(normalized_run_id, db=db)
    events = get_run_events_fn(normalized_run_id, db=db)
    structured = extract_structured_result_fn(events)
    if structured is None:
        return {}

    archive_paths = build_project_result_archive_paths(
        archive_root=archive_root,
        project_id=project.id,
        run_id=normalized_run_id,
    )
    archive_paths["dir"].mkdir(parents=True, exist_ok=True)

    if result_package is None:
        resolved_assets = (
            assets if assets is not None else build_assets_payload_fn(project, db)
        )
        result_package = build_result_package_fn(
            project,
            snapshot,
            structured,
            assets=resolved_assets,
            polish_bundle=extract_polish_bundle_fn(events, structured),
            app_version=app_version,
        )

    markdown_content = result_package_markdown_fn(
        result_package,
        surface_mode="internal",
        internal_export_mode="full",
    )
    archive_paths["markdown"].write_text(markdown_content, encoding="utf-8")

    try:
        if docx_source_path is not None:
            shutil.copy2(str(docx_source_path), str(archive_paths["docx"]))
        elif not archive_paths["docx"].exists():
            generated_docx_path, _ = await generate_result_package_docx_fn(
                project,
                result_package,
                surface_mode="internal",
                internal_export_mode="full",
            )
            shutil.copy2(str(generated_docx_path), str(archive_paths["docx"]))

        generated_external_path, _ = await generate_result_package_docx_fn(
            project,
            result_package,
            surface_mode="external",
            internal_export_mode="deck-only",
        )
        shutil.copy2(str(generated_external_path), str(archive_paths["external_docx"]))
    except Exception:
        logger.warning(
            "[Projects] Failed to persist one or more DOCX archive artifacts"
        )

    return {
        "markdown_path": str(archive_paths["markdown"]),
        "docx_path": str(archive_paths["docx"]),
        "external_docx_path": str(archive_paths["external_docx"]),
    }
