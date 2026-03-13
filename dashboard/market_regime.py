"""Market regime calculation for the BTC dashboard.

Canonical version is now backend/services/regime_service.py.
This thin wrapper re-exports for backward compatibility.
"""

from backend.services.regime_service import (  # noqa: F401
    build_regime_payload,
    calculate_regime_history,
)
