from __future__ import annotations

"""
PHASED REMOVAL NOTICE

- Purpose: migration-only raw compatibility path for private tests and temporary internal callers.
- Scope: not a public API, not a product execution path, not for new feature work.
- Removal target: delete after all rebuild_assistant regression tests and internal callers migrate to
  SafeAnalysisBundle-only execution in the next cleanup phase.
"""

from mellow_link import app_state

from .runner import _spawn_rebuild_run
from .schemas import RebuildAssetsPayload


def start_rebuild_assistant_run_compat(
    run_id: str,
    session_id: str | None,
    *,
    goal: str,
    assets: RebuildAssetsPayload,
    constraints: list[str] | None = None,
    temp_session_id: str | None = None,
) -> None:
    """Compatibility-only raw path kept for private tests and phased migration support."""
    temp_context = str(app_state.TEMP_CONTEXT_STORE.get(temp_session_id, "") or "") if temp_session_id else ""
    _spawn_rebuild_run(
        run_id=run_id,
        session_id=session_id,
        goal=goal,
        prepare_input=lambda service: service.prepare_input(
            goal=goal,
            assets=assets,
            constraints=constraints,
            temp_context=temp_context,
        ),
        run_meta={"temp_session_id": temp_session_id, "compatibility_mode": True},
    )
