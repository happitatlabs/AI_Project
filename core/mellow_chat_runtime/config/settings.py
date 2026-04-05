from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _workspace_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[2],  # before move: AI_Project
        Path(__file__).resolve().parents[3],  # after move: AI_Project
        Path.cwd().resolve(),
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "core" / "mellow_chat_runtime").exists():
            return resolved
        if resolved.name == "core" and (resolved / "mellow_chat_runtime").exists():
            return resolved.parent
        if (resolved / "mellow_chat_runtime").exists():
            return resolved
    return Path.cwd().resolve()


_ROOT = _workspace_root()
_LEGACY_DATA_DIR = _ROOT / "mellow_chat_runtime_data"
_ROLE_DATA_DIR = _ROOT / "data" / "runtime" / "mellow_chat_runtime_data"
_DEFAULT_DATA_DIR = _ROLE_DATA_DIR if _ROLE_DATA_DIR.exists() or (not _LEGACY_DATA_DIR.exists() and (_ROOT / "core").exists()) else _LEGACY_DATA_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8010)
    api_debug: bool = Field(default=False)
    runtime_impl: str = Field(default="engine-backed")

    ollama_host: str = Field(default="localhost")
    ollama_port: int = Field(default=11434)
    ollama_timeout: float = Field(default=60.0)

    fast_model: str = Field(default="qwen2.5:7b")
    thinking_model: str = Field(default="qwen2.5:7b")
    research_model: str = Field(default="qwen2.5:7b")

    data_dir: Path = Field(default=_DEFAULT_DATA_DIR)
    domain_data_file: Path = Field(default=_DEFAULT_DATA_DIR / "domain_data.json")

    @property
    def ollama_url(self) -> str:
        return f"http://{self.ollama_host}:{self.ollama_port}"


def get_settings() -> Settings:
    return _get_settings()


@lru_cache()
def _get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.domain_data_file.parent.mkdir(parents=True, exist_ok=True)
    return s
