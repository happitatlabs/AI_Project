from __future__ import annotations

from pathlib import Path

from mellow_link.modules.base import ModuleManifest, RegisteredModule
from mellow_link.modules.registry import ModuleRegistry

from .api import router

MODULE_VERSION = "0.1.0"

MANIFEST = ModuleManifest(
    module_id="rebuild_assistant",
    name="Legacy Modernization Analysis",
    description="레거시 자산을 분석해 기능 분류, 업무 규칙, 현대화 설계안과 전환 초안을 정리합니다.",
    run_kind="rebuild_plan",
    start_path="/modules/rebuild_assistant",
    icon="RB",
)


def register_module(registry: ModuleRegistry) -> None:
    base_dir = Path(__file__).resolve().parent
    registry.register(
        RegisteredModule(
            manifest=MANIFEST,
            router=router,
            base_dir=base_dir,
            readme_path=base_dir / "README.md",
        )
    )
