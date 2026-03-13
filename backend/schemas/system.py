"""Pydantic schemas for system endpoints."""

from pydantic import BaseModel


class UpdateStatusResponse(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: int
    startup_delay_seconds: int
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    last_stage: str | None = None
    log_path: str
    status_path: str
