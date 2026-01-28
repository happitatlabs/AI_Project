"""
Settings Management for Mellow-Link

Centralized configuration using pydantic-settings for environment variable
support, validation, and type safety.

Usage:
    from mellow_link.config.settings import get_settings

    settings = get_settings()
    print(settings.ollama_host)
"""

from typing import Optional, List
from pathlib import Path
from functools import lru_cache
import os

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field, field_validator, AliasChoices
    PYDANTIC_V2 = True
except ImportError:
    # Fallback for pydantic v1
    from pydantic import BaseSettings, Field, validator
    AliasChoices = None
    PYDANTIC_V2 = False

# Force output_dir to be inside mellow_link package
_MELLOW_LINK_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent
_FORCED_OUTPUT_DIR = _MELLOW_LINK_DIR / "outputs"


class Settings(BaseSettings):
    """
    Main settings class for Mellow-Link using pydantic-settings.

    All settings can be overridden via environment variables with the
    MELLOW_ prefix. For example:
        - MELLOW_OLLAMA_HOST=192.168.1.100
        - MELLOW_COMFYUI_PORT=8189
        - MELLOW_MODEL_DIR=/path/to/models

    Attributes:
        model_dir: Directory for AI models (Ollama, ComfyUI checkpoints)
        data_dir: Directory for application data (documents, outputs)

        ollama_host: Ollama server hostname
        ollama_port: Ollama server port
        ollama_timeout: Request timeout for Ollama (seconds)

        comfyui_host: ComfyUI server hostname
        comfyui_port: ComfyUI server port
        comfyui_timeout: Request timeout for ComfyUI (seconds)

        vram_warning_threshold: VRAM % to trigger warning
        vram_critical_threshold: VRAM % to trigger critical alert
        vram_poll_interval: Seconds between VRAM checks

        api_host: FastAPI server host
        api_port: FastAPI server port
        api_debug: Enable debug mode

        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """

    # ==================== Directory Settings ====================
    model_dir: Path = Field(
        default=Path("./models"),
        description="Directory for AI models",
        validation_alias="MELLOW_MODEL_DIR" if PYDANTIC_V2 else None
    )
    data_dir: Path = Field(
        default=Path("./data"),
        description="Directory for application data",
        validation_alias="MELLOW_DATA_DIR" if PYDANTIC_V2 else None
    )
    output_dir: Path = Field(
        default=Path("./outputs"),
        description="Directory for generated outputs",
        validation_alias="MELLOW_OUTPUT_DIR" if PYDANTIC_V2 else None
    )

    # ==================== Ollama (LLM) Settings ====================
    ollama_host: str = Field(
        default="localhost",
        description="Ollama server hostname",
        validation_alias="MELLOW_OLLAMA_HOST" if PYDANTIC_V2 else None
    )
    ollama_port: int = Field(
        default=11434,
        ge=1,
        le=65535,
        description="Ollama server port"
    )
    ollama_timeout: float = Field(
        default=300.0,
        ge=1.0,
        description="Ollama request timeout in seconds"
    )

    # Ollama model configuration
    fast_model: str = Field(
        default="qwen2.5:7b",
        description="Lightweight model for quick responses",
        validation_alias="MELLOW_LLM_FAST_MODEL" if PYDANTIC_V2 else None
    )
    thinking_model: str = Field(
        default="qwen2.5:7b",
        description="Main model for deep reasoning",
        validation_alias="MELLOW_LLM_THINKING_MODEL" if PYDANTIC_V2 else None
    )
    research_model: str = Field(
        default="qwen2.5:7b",
        description="Model for research/web search tasks"
    )
    embedding_model: str = Field(
        default="nomic-embed-text",
        description="Model for embeddings",
        validation_alias="MELLOW_LLM_EMBEDDING_MODEL" if PYDANTIC_V2 else None
    )

    # ==================== ComfyUI (Image) Settings ====================
    comfyui_host: str = Field(
        default="localhost",
        description="ComfyUI server hostname",
        validation_alias="MELLOW_COMFYUI_HOST" if PYDANTIC_V2 else None
    )
    comfyui_port: int = Field(
        default=8188,
        ge=1,
        le=65535,
        description="ComfyUI server port"
    )
    comfyui_timeout: float = Field(
        default=600.0,
        ge=1.0,
        description="ComfyUI request timeout in seconds"
    )

    # ComfyUI default checkpoint
    default_checkpoint: str = Field(
        default="flux1-dev-fp8.safetensors",
        description="Default Stable Diffusion checkpoint"
    )

    # ==================== VRAM Watchdog Settings ====================
    vram_warning_threshold: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        description="VRAM % to trigger warning",
        validation_alias="MELLOW_VRAM_WARNING_THRESHOLD" if PYDANTIC_V2 else None
    )
    vram_critical_threshold: float = Field(
        default=95.0,
        ge=0.0,
        le=100.0,
        description="VRAM % to trigger critical alert",
        validation_alias="MELLOW_VRAM_CRITICAL_THRESHOLD" if PYDANTIC_V2 else None
    )
    vram_poll_interval: float = Field(
        default=2.0,
        ge=0.5,
        description="Seconds between VRAM checks"
    )
    gpu_device_id: int = Field(
        default=0,
        ge=0,
        description="GPU device index to monitor"
    )

    # ==================== Orchestrator Settings ====================
    gpu_cooldown_seconds: float = Field(
        default=2.0,
        ge=0.0,
        description="Cooldown between GPU state transitions"
    )
    max_queue_size: int = Field(
        default=100,
        ge=1,
        description="Maximum pending tasks in queue"
    )

    # ==================== API Server Settings ====================
    api_host: str = Field(
        default="0.0.0.0",
        description="FastAPI server host",
        validation_alias=AliasChoices("SERVER_HOST", "MELLOW_API_HOST") if (PYDANTIC_V2 and AliasChoices) else None
    )
    server_host: str = Field(
        default="0.0.0.0",
        description="Server host (alias for api_host)",
        validation_alias="SERVER_HOST" if PYDANTIC_V2 else None
    )
    api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="FastAPI server port",
        validation_alias=AliasChoices("SERVER_PORT", "MELLOW_API_PORT") if (PYDANTIC_V2 and AliasChoices) else None
    )
    server_port: int = Field(
        default=8002,
        ge=1,
        le=65535,
        description="Server port (alias for api_port)",
        validation_alias="SERVER_PORT" if PYDANTIC_V2 else None
    )
    api_debug: bool = Field(
        default=False,
        description="Enable API debug mode",
        validation_alias=AliasChoices("DEBUG", "MELLOW_DEBUG") if (PYDANTIC_V2 and AliasChoices) else None
    )
    debug: bool = Field(
        default=False,
        description="Debug mode (alias for api_debug)",
        validation_alias="DEBUG" if PYDANTIC_V2 else None
    )
    app_title: str = Field(
        default="Aventurine v3",
        description="Application title",
        validation_alias="APP_TITLE" if PYDANTIC_V2 else None
    )
    cors_origins: str = Field(
        default="*",
        description="Allowed CORS origins (comma-separated string or * for all)"
    )

    # ==================== Document Service Settings ====================
    doc_max_workers: int = Field(
        default=2,
        ge=1,
        le=8,
        description="Thread pool workers for document generation"
    )
    template_dir: Path = Field(
        default=Path("./templates"),
        description="Directory for document templates"
    )

    # ==================== Logging Settings ====================
    log_level: str = Field(
        default="INFO",
        description="Logging level",
        validation_alias="MELLOW_LOG_LEVEL" if PYDANTIC_V2 else None
    )

    # ==================== Authentication Settings ====================
    guest_access_code: str = Field(
        default="lucky777",
        description="Access code for guest login",
        validation_alias="GUEST_ACCESS_CODE" if PYDANTIC_V2 else None
    )
    guest_token_expire_hours: int = Field(
        default=24,
        ge=1,
        description="Guest token expiry in hours",
        validation_alias="GUEST_TOKEN_EXPIRE_HOURS" if PYDANTIC_V2 else None
    )
    api_key: str = Field(
        default="",
        description="API key for external access",
        validation_alias="API_KEY" if PYDANTIC_V2 else None
    )
    
    # ==================== RBAC Settings ====================
    limit_admin: int = Field(
        default=-1,
        description="Daily usage limit for admin (-1 for unlimited)",
        validation_alias="LIMIT_ADMIN" if PYDANTIC_V2 else None
    )
    limit_user: int = Field(
        default=150,
        ge=-1,
        description="Daily usage limit for user (-1 for unlimited)",
        validation_alias="LIMIT_USER" if PYDANTIC_V2 else None
    )
    limit_guest: int = Field(
        default=20,
        ge=-1,
        description="Daily usage limit for guest (-1 for unlimited)",
        validation_alias="LIMIT_GUEST" if PYDANTIC_V2 else None
    )

    # ==================== Avatar Service Settings ====================
    avatar_ws_port: int = Field(
        default=12393,
        ge=1,
        le=65535,
        description="Avatar service WebSocket port",
        validation_alias="AVATAR_WS_PORT" if PYDANTIC_V2 else None
    )
    avatar_ws_url: str = Field(
        default="ws://localhost:12393",
        description="Avatar service WebSocket URL",
        validation_alias="AVATAR_WS_URL" if PYDANTIC_V2 else None
    )

    # ==================== Pydantic Configuration ====================
    if PYDANTIC_V2:
        model_config = SettingsConfigDict(
            env_file=".env",  # .env file load
            env_file_encoding="utf-8",  # encoding settings
            extra="ignore",  # ignore undefined variables in .env without error
            case_sensitive=False
        )
    else:
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            case_sensitive = False

    # ==================== Validators ====================
    if PYDANTIC_V2:
        @field_validator("vram_critical_threshold")
        @classmethod
        def critical_must_exceed_warning(cls, v, info):
            warning = info.data.get("vram_warning_threshold", 80.0)
            if v <= warning:
                raise ValueError(
                    f"Critical threshold ({v}) must be greater than warning ({warning})"
                )
            return v

        @field_validator("model_dir", "data_dir", "output_dir", "template_dir", mode="before")
        @classmethod
        def convert_to_path(cls, v):
            if isinstance(v, str):
                return Path(v)
            return v
    else:
        @validator("vram_critical_threshold")
        def critical_must_exceed_warning(cls, v, values):
            warning = values.get("vram_warning_threshold", 80.0)
            if v <= warning:
                raise ValueError(
                    f"Critical threshold ({v}) must be greater than warning ({warning})"
                )
            return v

        @validator("model_dir", "data_dir", "output_dir", "template_dir", pre=True)
        def convert_to_path(cls, v):
            if isinstance(v, str):
                return Path(v)
            return v

    # ==================== Computed Properties ====================
    @property
    def ollama_url(self) -> str:
        """Full Ollama API URL."""
        return f"http://{self.ollama_host}:{self.ollama_port}"

    @property
    def comfyui_url(self) -> str:
        """Full ComfyUI API URL."""
        return f"http://{self.comfyui_host}:{self.comfyui_port}"

    @property
    def comfyui_ws_url(self) -> str:
        """ComfyUI WebSocket URL."""
        return f"ws://{self.comfyui_host}:{self.comfyui_port}/ws"

    @property
    def image_output_dir(self) -> Path:
        """
        Directory for generated images.
        FORCED to mellow_link/outputs/images regardless of .env settings.
        """
        return _FORCED_OUTPUT_DIR / "images"

    @property
    def document_output_dir(self) -> Path:
        """
        Directory for generated documents.
        FORCED to mellow_link/outputs/documents regardless of .env settings.
        """
        return _FORCED_OUTPUT_DIR / "documents"

    # ==================== Methods ====================
    def ensure_directories(self) -> None:
        """Create all required directories if they don't exist."""
        directories = [
            self.model_dir,
            self.data_dir,
            _FORCED_OUTPUT_DIR,  # Force outputs inside mellow_link/outputs
            self.image_output_dir,  # mellow_link/outputs/images
            self.document_output_dir,  # mellow_link/outputs/documents
            self.template_dir,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if isinstance(self.cors_origins, str):
            if self.cors_origins == "*":
                return ["*"]
            return [origin.strip() for origin in self.cors_origins.split(",")]
        return self.cors_origins if isinstance(self.cors_origins, list) else ["*"]
    
    def get_limit_for_role(self, role: str) -> int:
        """Get daily request limit for a given role."""
        limits = {
            "admin": self.limit_admin,
            "user": self.limit_user,
            "guest": self.limit_guest,
        }
        return limits.get(role.lower(), self.limit_guest)

    def to_dict(self) -> dict:
        """Export settings to dictionary."""
        return {
            "model_dir": str(self.model_dir),
            "data_dir": str(self.data_dir),
            "output_dir": str(self.output_dir),
            "ollama": {
                "host": self.ollama_host,
                "port": self.ollama_port,
                "url": self.ollama_url,
                "timeout": self.ollama_timeout,
                "models": {
                    "fast": self.fast_model,
                    "thinking": self.thinking_model,
                    "research": self.research_model,
                }
            },
            "comfyui": {
                "host": self.comfyui_host,
                "port": self.comfyui_port,
                "url": self.comfyui_url,
                "timeout": self.comfyui_timeout,
                "default_checkpoint": self.default_checkpoint,
            },
            "vram": {
                "warning_threshold": self.vram_warning_threshold,
                "critical_threshold": self.vram_critical_threshold,
                "poll_interval": self.vram_poll_interval,
                "device_id": self.gpu_device_id,
            },
            "api": {
                "host": self.api_host,
                "port": self.api_port,
                "debug": self.api_debug,
            },
            "log_level": self.log_level,
        }


# =============================================================================
# Global Settings Access
# =============================================================================

@lru_cache()
def get_settings() -> Settings:
    """
    Get the global settings instance (cached singleton).

    Uses lru_cache to ensure only one Settings instance is created.
    Settings are loaded from environment variables and .env file.

    Returns:
        Global Settings instance

    Example:
        settings = get_settings()
        print(settings.ollama_url)
    """
    return Settings()


def clear_settings_cache() -> None:
    """
    Clear the settings cache to force reload.

    Useful for testing or when environment variables change.
    """
    get_settings.cache_clear()


def configure(custom_settings: Settings) -> Settings:
    """
    Configure with custom settings (bypasses cache).

    Note: This doesn't update the cached settings.
    Use clear_settings_cache() first if needed.

    Args:
        custom_settings: Custom Settings instance

    Returns:
        The provided settings instance
    """
    return custom_settings


# =============================================================================
# Convenience Functions
# =============================================================================

def get_ollama_config() -> dict:
    """Get Ollama configuration as dict."""
    s = get_settings()
    return {
        "host": s.ollama_host,
        "port": s.ollama_port,
        "timeout": s.ollama_timeout,
        "models": {
            "fast": s.fast_model,
            "thinking": s.thinking_model,
            "research": s.research_model,
        }
    }


def get_comfyui_config() -> dict:
    """Get ComfyUI configuration as dict."""
    s = get_settings()
    return {
        "host": s.comfyui_host,
        "port": s.comfyui_port,
        "timeout": s.comfyui_timeout,
        "output_dir": s.image_output_dir,
    }


def get_vram_config() -> dict:
    """Get VRAM watchdog configuration as dict."""
    s = get_settings()
    return {
        "warning_threshold": s.vram_warning_threshold,
        "critical_threshold": s.vram_critical_threshold,
        "poll_interval": s.vram_poll_interval,
        "device_id": s.gpu_device_id,
    }

settings = Settings()