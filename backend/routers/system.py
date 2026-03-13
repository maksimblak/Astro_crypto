"""System endpoints: /api/update-status."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["system"])

_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "auto_update.log"


@router.get("/update-status")
def api_update_status():
    from auto_update import load_update_status

    return load_update_status()


@router.get("/update-log")
def api_update_log(tail: int = 200):
    if not _LOG_PATH.exists():
        return PlainTextResponse("No log file yet.")
    lines = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return PlainTextResponse("\n".join(lines[-tail:]))
