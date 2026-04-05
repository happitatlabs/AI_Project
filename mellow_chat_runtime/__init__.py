"""Compatibility shim for the role-based workspace layout."""

from __future__ import annotations

from pathlib import Path


_PACKAGE_ROOT = Path(__file__).resolve().parent
_TARGET = _PACKAGE_ROOT.parent / "core" / "mellow_chat_runtime"

if not _TARGET.is_dir():
    raise ModuleNotFoundError(f"Expected package directory not found: {_TARGET}")

__path__ = [str(_TARGET)]
