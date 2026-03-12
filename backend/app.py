"""AstroBTC FastAPI backend."""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add dashboard dir to path so auto_update, market_regime are importable
_project_root = Path(__file__).resolve().parent.parent
_dashboard_dir = str(_project_root / "dashboard")
if _dashboard_dir not in sys.path:
    sys.path.append(_dashboard_dir)

from backend.routers import astro, market, regime, system  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    from auto_update import start_auto_updater

    start_auto_updater()
    yield


app = FastAPI(title="AstroBTC", lifespan=lifespan)

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
app.include_router(market.router, prefix="/api")
app.include_router(regime.router, prefix="/api")
app.include_router(system.router, prefix="/api")

# Serve React build in production
_frontend_dist = _project_root / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
