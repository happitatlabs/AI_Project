import argparse
import tempfile
from enum import Enum
from pathlib import Path


EXPERIMENTAL_SANDBOX_FLAG = "--experimental-sandbox"
CONFIRM_EXPERIMENTAL_FLAG = "--confirm-experimental"


class ExecutionMode(str, Enum):
    OPERATIONAL = "operational"
    EXPERIMENTAL_SANDBOX = "experimental_sandbox"


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def add_experimental_sandbox_flags(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        EXPERIMENTAL_SANDBOX_FLAG,
        action="store_true",
        help="Enable experimental sandbox execution mode",
    )
    parser.add_argument(
        CONFIRM_EXPERIMENTAL_FLAG,
        action="store_true",
        help="Confirm experimental sandbox execution mode",
    )
    return parser


def normalize_execution_flags(flags: dict | argparse.Namespace | None = None) -> dict:
    if flags is None:
        raw = {}
    elif isinstance(flags, argparse.Namespace):
        raw = vars(flags)
    else:
        raw = dict(flags)
    return {
        "experimental_sandbox": bool(
            raw.get("experimental_sandbox") or raw.get(EXPERIMENTAL_SANDBOX_FLAG)
        ),
        "confirm_experimental": bool(
            raw.get("confirm_experimental") or raw.get(CONFIRM_EXPERIMENTAL_FLAG)
        ),
    }


def resolve_execution_mode(flags: dict | argparse.Namespace | None = None) -> ExecutionMode:
    normalized = normalize_execution_flags(flags)
    if normalized["experimental_sandbox"] and normalized["confirm_experimental"]:
        return ExecutionMode.EXPERIMENTAL_SANDBOX
    return ExecutionMode.OPERATIONAL


def build_experimental_sandbox_gate(
    sandbox_root: str | Path,
    *,
    flags: dict | argparse.Namespace | None = None,
) -> dict:
    normalized_flags = normalize_execution_flags(flags)
    execution_mode = resolve_execution_mode(normalized_flags)
    resolved_root = Path(sandbox_root).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    path_in_temp_dir = _is_relative_to(resolved_root, temp_root)

    blockers = []
    if execution_mode is not ExecutionMode.EXPERIMENTAL_SANDBOX:
        blockers.append(
            "experimental sandbox mode requires both --experimental-sandbox and --confirm-experimental"
        )
    if not path_in_temp_dir:
        blockers.append("sandbox_root must be inside the system temp directory")

    experimental_sandbox_enabled = execution_mode is ExecutionMode.EXPERIMENTAL_SANDBOX and path_in_temp_dir
    return {
        "execution_mode": execution_mode.value,
        "experimental_sandbox_enabled": experimental_sandbox_enabled,
        "enable_mode": execution_mode.value if experimental_sandbox_enabled else "blocked",
        "enable_blockers": blockers,
        "required_flags": normalized_flags,
        "required_cli_flags": [
            EXPERIMENTAL_SANDBOX_FLAG,
            CONFIRM_EXPERIMENTAL_FLAG,
        ],
        "sandbox_root": str(resolved_root),
        "temp_root": str(temp_root),
        "path_in_temp_dir": path_in_temp_dir,
        "path_policy_reason": "workspace write allowed only inside temp-dir sandbox",
        "runtime_recording_scope": "runtime-data only",
        "prohibitions": [
            "real workspace write forbidden",
            "subprocess execution forbidden",
            "network access forbidden",
            "daemon integration forbidden",
            "automatic apply forbidden",
        ],
    }
