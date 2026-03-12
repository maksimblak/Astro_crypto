"""System endpoints: /api/update-status."""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/update-status")
def api_update_status():
    from auto_update import load_update_status

    return load_update_status()
