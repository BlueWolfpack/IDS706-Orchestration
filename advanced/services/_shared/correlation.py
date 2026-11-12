"""Lightweight correlation-id middleware copied into each service image path via PYTHONPATH."""

from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("automl")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    header_name = "X-Correlation-Id"

    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers[self.header_name] = cid
        logger.info(
            "%s %s correlation_id=%s",
            request.method,
            request.url.path,
            cid,
        )
        return response
