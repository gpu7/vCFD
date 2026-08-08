"""Application configuration loaded from environment variables."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenFOAMMode(StrEnum):
    MOCK = "mock"
    DOCKER = "docker"
    NATIVE = "native"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VCFD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cases_root: Path = Field(default=Path("./cases/workspace"))
    templates_root: Path = Field(default=Path("./cases/templates"))
    jobs_root: Path = Field(default=Path("./.vcfd/jobs"))
    openfoam_mode: OpenFOAMMode = OpenFOAMMode.MOCK
    openfoam_docker_image: str = "opencfd/openfoam-default:2506"
    openfoam_bashrc: str | None = None
    auth_token: str | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    max_concurrent_jobs: int = 2
    default_job_timeout_sec: int = 3600

    def ensure_dirs(self) -> None:
        self.cases_root.mkdir(parents=True, exist_ok=True)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        if not self.templates_root.exists():
            # Allow missing templates only when using absolute custom roots in tests.
            pass


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
