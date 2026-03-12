"""Centralized project configuration."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CHARTS_DIR = BASE_DIR / "charts"
DB_PATH = str(DATA_DIR / "btc_research.duckdb")

# --- Market data ---
BTC_TICKER = "BTC-USD"
BTC_START_DATE = "2016-01-01"

# --- API ---
HTTP_TIMEOUT = int(os.getenv("ASTROBTC_HTTP_TIMEOUT", "30"))
HTTP_MAX_RETRIES = int(os.getenv("ASTROBTC_HTTP_MAX_RETRIES", "3"))
HTTP_USER_AGENT = "AstroBTC/1.0 (market feature pipeline)"

# --- Dashboard ---
DASHBOARD_HOST = os.getenv("ASTROBTC_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("ASTROBTC_PORT", "5000"))
REGIME_CACHE_TTL = int(os.getenv("ASTROBTC_REGIME_CACHE_TTL", "300"))

# --- Auto-update ---
AUTO_UPDATE_ENABLED = os.getenv("ASTROBTC_AUTO_UPDATE", "true").lower() in {"1", "true", "yes", "on"}
AUTO_UPDATE_INTERVAL = int(os.getenv("ASTROBTC_AUTO_UPDATE_INTERVAL_SECONDS", str(12 * 60 * 60)))
AUTO_UPDATE_STARTUP_DELAY = int(os.getenv("ASTROBTC_AUTO_UPDATE_STARTUP_DELAY_SECONDS", "30"))

# --- Model ---
MODEL_FDR_THRESHOLD = 0.25
MODEL_MIN_BINARY_WEIGHT = 0.15
MODEL_MIN_CONTINUOUS_WEIGHT = 0.05
MODEL_MIN_DIRECTION_WEIGHT = 0.10
WEIGHT_SHRINKAGE_FACTOR = float(os.getenv("ASTROBTC_WEIGHT_SHRINKAGE", "0.85"))
