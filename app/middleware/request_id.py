import contextvars
import logging
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# ContextVar storing the current request ID asynchronously across execution flows
request_id_contextvar: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class RequestIDFilter(logging.Filter):
    """Injects the asynchronous request_id contextvar into the standard python logging pipeline."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_contextvar.get()
        return True


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware interceptor injecting UUID4 tracing strings into every request scope.
    Allows for strict lifecycle logging and distributed debugging across asynchronous domains.
    """
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID")
        if not req_id:
            req_id = str(uuid.uuid4())
            
        token = request_id_contextvar.set(req_id)
        
        response = await call_next(request)
        
        # Inject the tracing ID strictly into the outbound response headers
        response.headers["X-Request-ID"] = req_id
        
        request_id_contextvar.reset(token)
        return response
