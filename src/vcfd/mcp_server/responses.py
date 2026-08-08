"""Standard tool response envelope for speakable MCP results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Uniform return type for every MCP tool."""

    summary: str = Field(description="Short natural-language summary for the voice agent to speak.")
    success: bool = True
    job_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def ok(
    summary: str,
    *,
    data: dict[str, Any] | None = None,
    job_id: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return ToolResult(
        summary=summary,
        success=True,
        job_id=job_id,
        data=data or {},
        warnings=warnings or [],
    ).to_dict()


def fail(
    summary: str,
    *,
    data: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return ToolResult(
        summary=summary,
        success=False,
        data=data or {},
        warnings=warnings or [],
    ).to_dict()
