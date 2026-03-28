import logging
import os
import shutil

logger = logging.getLogger("report_retention")

DEFAULT_RETENTION_POLICY = {
    "report_": 1,
    "change_summary_": 3,
    "memory_analysis_": 3,
    "workspace_reporter_": 3,
    "code_reviewer_": 3,
    "file_classifier_": 3,
}

DEFAULT_RETENTION_MODE = "archive"


def reports_dir(workspace: str) -> str:
    return os.path.join(workspace, "reports")


def archive_reports_dir(workspace: str) -> str:
    return os.path.join(workspace, "archive", "reports")


def ensure_report_dirs(workspace: str, mode: str = DEFAULT_RETENTION_MODE) -> str:
    report_path = reports_dir(workspace)
    os.makedirs(report_path, exist_ok=True)
    if mode == "archive":
        os.makedirs(archive_reports_dir(workspace), exist_ok=True)
    return report_path


def resolve_retention_policy(filename: str) -> tuple[str | None, int | None]:
    for prefix, keep in DEFAULT_RETENTION_POLICY.items():
        if filename.startswith(prefix):
            return prefix, keep
    return None, None


def write_report(
    workspace: str,
    filename: str,
    lines: list[str],
    mode: str = DEFAULT_RETENTION_MODE,
) -> tuple[str, str]:
    report_path = ensure_report_dirs(workspace, mode=mode)
    filepath = os.path.join(report_path, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return filepath, f"reports/{filename}"


def read_latest_signature(workspace: str, prefix: str) -> str | None:
    report_path = reports_dir(workspace)
    if not os.path.isdir(report_path):
        return None
    matched = sorted(
        [name for name in os.listdir(report_path) if name.startswith(prefix) and name.endswith(".md")]
    )
    if not matched:
        return None

    latest_path = os.path.join(report_path, matched[-1])
    try:
        with open(latest_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("<!-- report_signature:"):
                    return line.replace("<!-- report_signature:", "").replace("-->", "").strip()
    except OSError:
        return None
    return None


def apply_retention(
    workspace: str,
    prefix: str,
    keep: int,
    mode: str = DEFAULT_RETENTION_MODE,
) -> dict:
    report_path = reports_dir(workspace)
    if not os.path.isdir(report_path):
        return {"kept": keep, "archived": 0, "deleted": 0, "affected": []}

    matched = sorted(
        [name for name in os.listdir(report_path) if name.startswith(prefix) and name.endswith(".md")]
    )
    overflow = max(0, len(matched) - keep)
    affected: list[str] = []
    archived = 0
    deleted = 0

    for victim in matched[:overflow]:
        source = os.path.join(report_path, victim)
        if mode == "archive":
            ensure_report_dirs(workspace, mode=mode)
            destination = os.path.join(archive_reports_dir(workspace), victim)
            shutil.move(source, destination)
            archived += 1
        else:
            os.remove(source)
            deleted += 1
        affected.append(victim)

    label = prefix.rstrip("_")
    logger.info(
        f"[Retention] {label}: kept={keep} "
        f"{'archived' if mode == 'archive' else 'deleted'}={archived if mode == 'archive' else deleted}"
    )
    return {
        "kept": keep,
        "archived": archived,
        "deleted": deleted,
        "affected": affected,
    }


def write_report_with_retention(
    workspace: str,
    filename: str,
    lines: list[str],
    mode: str = DEFAULT_RETENTION_MODE,
) -> dict:
    _, relative_path = write_report(workspace, filename, lines, mode=mode)
    prefix, keep = resolve_retention_policy(filename)
    retention = {"kept": 0, "archived": 0, "deleted": 0, "affected": []}
    if prefix and keep is not None:
        retention = apply_retention(workspace, prefix, keep, mode=mode)
    return {"report_file": relative_path, "retention": retention}
