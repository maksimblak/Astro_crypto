"""Config endpoints: /api/config for threshold management."""

from fastapi import APIRouter

from backend.services.config_service import get_all_config, seed_defaults

router = APIRouter(tags=["config"])


@router.get("/config")
def api_config():
    """Return all thresholds grouped by category."""
    return get_all_config()


@router.post("/config/seed")
def api_config_seed():
    """Seed default thresholds (does not overwrite existing)."""
    inserted = seed_defaults(overwrite=False)
    return {"inserted": inserted}
