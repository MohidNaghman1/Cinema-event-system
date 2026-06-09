import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.security import cleanup_revoked_tokens
from app.db.mongodb import connect_to_mongo
from app.middleware.request_id import RequestIDFilter, RequestIDMiddleware
from app.tasks.cleanup_tasks import cleanup_expired_holds, expire_pending_bookings

# --- Routers ---
from app.api.v1.auth.router import router as auth_router
from app.api.v1.venues.router import router as venues_router
from app.api.v1.events.router import router as events_router
from app.api.v1.bookings.seats import router as seats_router
from app.api.v1.bookings.router import router as bookings_router
from app.api.v1.tickets.router import router as tickets_router
from app.api.v1.payments.router import router as payments_router
from app.api.v1.payments.stripe import router as stripe_router

# Admin Routers
from app.api.v1.admin.users import router as admin_users_router
from app.api.v1.admin.events import router as admin_events_router
from app.api.v1.admin.bookings import router as admin_bookings_router
from app.api.v1.admin.payments import router as admin_payments_router
from app.api.v1.admin.reports import router as admin_reports_router


settings = get_settings()

# Setup logging with Request ID filters
logger = logging.getLogger("cinema_app")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [ReqID: %(request_id)s] %(message)s"))
handler.addFilter(RequestIDFilter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)


async def run_cleanup_loop():
    """Background polling loop replacing Celery Beat for system cleanups."""
    while True:
        try:
            await cleanup_expired_holds()
            await expire_pending_bookings()
        except Exception as e:
            logger.error(f"Error in cleanup loop: {e}")
        await asyncio.sleep(300)  # every 5 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle hooks controlling MongoDB connection pooling and internal state limits."""
    logger.info("Initializing database mappings...")
    await connect_to_mongo()
    
    logger.info("Purging stale in-memory token state...")
    cleanup_revoked_tokens()
    
    logger.info("Starting asyncio cleanup loop...")
    cleanup_task = asyncio.create_task(run_cleanup_loop())
    
    yield
    
    logger.info("Shutting down background loops...")
    cleanup_task.cancel()


app_description = """
## Cinema & Concert Event Management API

Welcome to the core backend for our Cinema & Concert management system. 

### Features
* **Auth**: Full OAuth2 + JWT authentication stack.
* **Venues & Events**: Complete inventory management with dynamic seat layouts.
* **Bookings**: Fast in-memory seat reservations.
* **Payments**: Idempotent Stripe webhook integrations.
* **Admin**: Powerful real-time dashboards and bulk-cancellation tools.

### Authentication
Most endpoints require a `Bearer` token.
Use the `/api/v1/auth/login` endpoint to acquire an access token, or use the integrated Google/GitHub OAuth flows.

"""

tags_metadata = [
    {"name": "Authentication", "description": "Authentication and authorization flows."},
    {"name": "Venues", "description": "Venue management and seat map schemas."},
    {"name": "Events", "description": "Public event catalogs and details."},
    {"name": "Bookings", "description": "User booking lifecycle management and concurrent seat locking."},
    {"name": "Tickets", "description": "PDF and QR code generation for digital tickets."},
    {"name": "Payments", "description": "Stripe payment intents and webhooks."},
    {"name": "Admin — Users", "description": "User administration and bans."},
    {"name": "Admin — Events", "description": "Event administration and publish controls."},
    {"name": "Admin — Bookings", "description": "Override capabilities for bookings."},
    {"name": "Admin — Payments", "description": "Manual refund triggers."},
    {"name": "Admin — Reports", "description": "Real-time analytics and revenue aggregations."},
]

app = FastAPI(
    title="Cinema & Concert Event Management API",
    description=app_description,
    version="1.0.0",
    contact={
        "name": "API Support",
        "email": "support@cinema-events.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={
        "persistAuthorization": True, 
        "displayRequestDuration": True
    },
    lifespan=lifespan,
)

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": "Not Found"})

@app.exception_handler(405)
async def custom_405_handler(request: Request, exc):
    return JSONResponse(status_code=405, content={"detail": "Method Not Allowed"})


# --- Middlewares ---
app.add_middleware(RequestIDMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)

trusted_hosts = os.environ.get("TRUSTED_HOSTS")
if trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts.split(","))

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- Attach Routers ---
app.include_router(auth_router)
app.include_router(venues_router)
app.include_router(events_router)
app.include_router(seats_router)
app.include_router(bookings_router)
app.include_router(tickets_router)
app.include_router(payments_router)
app.include_router(stripe_router)

# Attach Admin specific domain
app.include_router(admin_users_router)
app.include_router(admin_events_router)
app.include_router(admin_bookings_router)
app.include_router(admin_payments_router)
app.include_router(admin_reports_router)
