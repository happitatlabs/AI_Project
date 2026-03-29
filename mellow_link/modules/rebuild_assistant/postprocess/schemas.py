from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PolishedSection(BaseModel):
    section_key: str
    title: str
    original_text: str
    polished_text: str
    audience_variants: dict[str, str] = Field(default_factory=dict)
    delivery_variants: dict[str, str] = Field(default_factory=dict)


class StructuredResultPolishBundle(BaseModel):
    primary_judgment: str
    audience: str = "manager"
    delivery_mode: str = "client_report"
    use_ai_rewrite: bool = False
    original_result: dict[str, Any]
    polished_sections: list[PolishedSection] = Field(default_factory=list)
    preserved_facts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
