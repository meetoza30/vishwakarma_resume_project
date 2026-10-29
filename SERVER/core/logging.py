import logging
import uuid
import sys
import json
import time
import re
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

# Configure Root Logger
logger = logging.getLogger("vishwakarma_platform")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)


def mask_sensitive_info(text: str) -> str:
    """Scrub sensitive keys (Bearer tokens, API keys) from logs."""
    if not isinstance(text, str):
        return str(text)
    # Mask API keys
    text = re.sub(r'sk-[a-zA-Z0-9_-]{20,}', 'sk-***REDACTED***', text)
    text = re.sub(r'Bearer\s+[a-zA-Z0-9._-]+', 'Bearer ***REDACTED***', text)
    return text


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that assigns a unique X-Request-ID to every request for trace-ability.
    """
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id
        
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        
        response.headers["X-Request-ID"] = correlation_id
        response.headers["X-Process-Time-Ms"] = str(process_time_ms)
        
        log_data = f"Method={request.method} Path={request.url.path} Status={response.status_code} Time={process_time_ms}ms RequestID={correlation_id}"
        logger.info(mask_sensitive_info(log_data))
        
        return response
