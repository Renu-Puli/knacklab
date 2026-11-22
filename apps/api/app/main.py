from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.routers import links, redirect
from app.logging_config import configure_logging
from app.middleware import RequestIdMiddleware
from app.errors import register_exception_handlers
from app.cache import init_redis, close_redis

# Initialize structured logging with secret redaction
configure_logging(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize Redis connection pool
    await init_redis()
    yield
    # Shutdown: cleanly close Redis connection pool
    await close_redis()


app = FastAPI(
    title="B2B Multi-Tenant URL Shortener API",
    version="1.0.0",
    lifespan=lifespan,
)

# Register request tracking and latency middleware
app.add_middleware(RequestIdMiddleware)

# Register uniform error envelope exception handlers
register_exception_handlers(app)

# Register routers: support both /links and /api/v1/links for backward compatibility
app.include_router(links.router)
app.include_router(links.router, prefix="/api/v1")
app.include_router(redirect.router)


@app.get("/health")
def health_check():
    return {"ok": True}
