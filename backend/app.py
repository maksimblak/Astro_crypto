"""AstroBTC FastAPI backend."""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("astrobtc")

# Add dashboard dir to path so auto_update is importable
_project_root = Path(__file__).resolve().parent.parent
_dashboard_dir = str(_project_root / "dashboard")
if _dashboard_dir not in sys.path:
    sys.path.append(_dashboard_dir)

from backend.routers import astro, backtest, config, cycle, market, regime, system, ws  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    from auto_update import start_auto_updater
    from backend.services.config_service import seed_defaults

    # Run pending DB migrations
    try:
        from migrations.runner import upgrade as run_migrations
        applied = run_migrations()
        if applied:
            logger.info("Applied %d migration(s): %s", len(applied), ", ".join(applied))
    except Exception:
        logger.exception("Migration runner failed (non-fatal)")

    seed_defaults()
    start_auto_updater()
    yield


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(title="AstroBTC", lifespan=lifespan)

# Logging middleware — must be added before CORS
from backend.middleware import RequestLoggingMiddleware  # noqa: E402
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://astro-crypto-dashboard.onrender.com",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(astro.router, prefix="/api")
app.include_router(cycle.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(regime.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(ws.router)

# Serve React build in production
_frontend_dist = _project_root / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
