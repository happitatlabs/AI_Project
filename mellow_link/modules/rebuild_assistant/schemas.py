from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class RebuildAssetsPayload(BaseModel):
    source_code: str = ""
    database_schema: str = ""
    sql_queries: str = ""
    ui_template: str = ""
    framework_info: str = ""

    def has_any_content(self) -> bool:
        return any(
            bool((value or "").strip())
            for value in (
                self.source_code,
                self.database_schema,
                self.sql_queries,
                self.ui_template,
                self.framework_info,
            )
        )


class LayeredListResult(BaseModel):
    database: list[str] = Field(default_factory=list)
    backend: list[str] = Field(default_factory=list)
    frontend: list[str] = Field(default_factory=list)


class StructuredRebuildResult(BaseModel):
    one_line_conclusion: str = ""
    analysis_summary: list[str] = Field(default_factory=list)
    rebuild_strategy: list[str] = Field(default_factory=list)
    layer_reconstruction: LayeredListResult = Field(default_factory=LayeredListResult)
    recomposition_draft: LayeredListResult = Field(default_factory=LayeredListResult)
    risks: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    missing_context: list[str] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        try:
            numeric = float(value)
        except Exception:
            numeric = 0.0
        return max(0.0, min(1.0, numeric))


class RebuildAssistantStartRequest(BaseModel):
    goal: str = Field(..., description="Single feature/page legacy reconstruction goal")
    assets: RebuildAssetsPayload = Field(default_factory=RebuildAssetsPayload)
    constraints: list[str] = Field(default_factory=list)
    temp_session_id: str | None = None

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, value: str) -> str:
        stripped = (value or "").strip()
        if len(stripped) < 8:
            raise ValueError("goal must be at least 8 characters after trimming")
        return stripped

    @model_validator(mode="after")
    def validate_assets_or_temp_context(self) -> "RebuildAssistantStartRequest":
        if self.assets.has_any_content() or (self.temp_session_id or "").strip():
            return self
        raise ValueError("Provide at least one asset or temp_session_id")


class RebuildAssistantStartResponse(BaseModel):
    run_id: str
    session_id: str
    module_id: str = "rebuild_assistant"
    run_kind: str = "rebuild_plan"
