"""Main FastAPI application for Zoria."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from core.config import settings
from core.database import init_db, get_db

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("Starting Zoria backend...")
    
    # Validate settings
    try:
        settings.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    
    # Ensure upload directory exists
    settings.ensure_upload_dir()
    
    # Initialize database
    db = init_db()
    await db.connect()
    logger.info("Database connected")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Zoria backend...")
    db = get_db()
    await db.close()
    logger.info("Database connection closed")


# Create FastAPI app
app = FastAPI(
    title="Zoria API",
    description="Educational Learning Platform API",
    version="1.0.0",
    lifespan=lifespan,
    # Trust proxy headers for HTTPS redirects
    root_path="",
    root_path_in_servers=False
)

# Trust proxy headers middleware (must be first)
@app.middleware("http")
async def add_proxy_headers(request: Request, call_next):
    """Handle proxy headers for HTTPS redirects behind Cloudflare."""
    # Trust X-Forwarded-Proto from Cloudflare
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests for debugging."""
    import time
    start_time = time.time()
    
    # Log request
    logger.info(f"→ {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}")
    
    # Process request
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"← {request.method} {request.url.path} - {response.status_code} ({process_time:.3f}s)")
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"✗ {request.method} {request.url.path} - ERROR after {process_time:.3f}s: {str(e)}", exc_info=True)
        raise


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Zoria API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        db = get_db()
        # Simple query to check database connection
        await db.fetchval("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }, 503


# Import and include routers
from api.v1 import auth, admin, parent, child, documents, tests, tikz

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(parent.router, prefix="/api/v1/parent", tags=["parent"])
app.include_router(child.router, prefix="/api/v1/child", tags=["child"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(tests.router, prefix="/api/v1/tests", tags=["tests"])
app.include_router(tikz.router, prefix="/api/v1/tikz", tags=["tikz"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
