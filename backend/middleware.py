"""FastAPI middleware: request logging and exception handling."""

from __future__ import annotations

import logging
import time
import traceback

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("astrobtc.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and duration."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "%s %s -> 500 (%.0fms) UNHANDLED EXCEPTION\n%s",
                method, path, duration_ms, traceback.format_exc(),
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )

        duration_ms = (time.perf_counter() - start) * 1000
        status = response.status_code

        if status >= 500:
            logger.error("%s %s -> %d (%.0fms)", method, path, status, duration_ms)
        elif status >= 400:
            logger.warning("%s %s -> %d (%.0fms)", method, path, status, duration_ms)
        else:
            logger.info("%s %s -> %d (%.0fms)", method, path, status, duration_ms)

        return response
