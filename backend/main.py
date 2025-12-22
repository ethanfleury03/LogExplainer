"""
FastAPI application entry point for Error Debug feature.
"""

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import error_debug_routes
from backend.utils.db import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
logger.info("Initializing database...")
init_db()
logger.info("Database initialized")

# Create FastAPI app
app = FastAPI(
    title="Error Debug API",
    description="API for managing printer machines and searching error indexes",
    version="1.0.0"
)

# Note: For production (Cloud Run), configure max_request_size in deployment settings
# Upload endpoint uses streaming read (1MB chunks) to handle large files efficiently

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Next.js default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(error_debug_routes.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Error Debug API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    # Configure upload limits: 100MB max request body
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        limit_concurrency=100,
        limit_max_requests=1000,
        timeout_keep_alive=30
    )

