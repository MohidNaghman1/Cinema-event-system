from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter(tags=["system"])


@router.get("/health", summary="Health check")
async def health(request: Request) -> dict[str, str]:
    """Return service and database connectivity status."""

    database_state = (
        "connected"
        if getattr(request.app.state, "mongo_connected", False)
        else "disconnected"
    )
    return {"status": "ok", "db": database_state}
