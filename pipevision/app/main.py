"""
PipeVision - DWG Preprocessing for AR/GIS Platforms
Main FastAPI Application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import uploads, projects, exports, auth
from app.core.config import settings
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    await init_db()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="PipeVision API",
    description="DWG preprocessing and conversion for AR/GIS platforms",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(uploads.router, prefix="/api/uploads", tags=["Uploads"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(exports.router, prefix="/api/exports", tags=["Exports"])


@app.get("/")
async def root():
    return {
        "name": "PipeVision API",
        "version": "0.1.0",
        "status": "operational",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
