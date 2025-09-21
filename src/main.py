"""
Voice AI Platform - FastAPI Application Entry Point

This module serves as the main entry point for the Voice AI Platform application.
It sets up the FastAPI application with automatic OpenAPI documentation,
CORS middleware, and basic health check endpoints.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn
import os
from pathlib import Path

# Initialize FastAPI application
app = FastAPI(
    title="Voice AI Platform",
    description="Voice AI Platform for EMR Integration - Enables voice-controlled appointment scheduling",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint that provides basic information about the API."""
    return """
    <html>
        <head>
            <title>Voice AI Platform</title>
        </head>
        <body>
            <h1>Voice AI Platform</h1>
            <p>Voice AI Platform for EMR Integration</p>
            <ul>
                <li><a href="/docs">API Documentation (OpenAPI)</a></li>
                <li><a href="/redoc">API Documentation (ReDoc)</a></li>
                <li><a href="/health">Health Check</a></li>
                <li><a href="/dashboard">Dashboard</a> (Coming Soon)</li>
            </ul>
        </body>
    </html>
    """


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring application status."""
    return {"status": "healthy", "service": "Voice AI Platform", "version": "0.1.0"}


@app.get("/dev/status")
async def dev_status():
    """Development status endpoint for testing hot reload functionality."""
    import os

    return {
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "debug": os.getenv("DEBUG", "false"),
        "hot_reload": "enabled",
        "message": "Development environment is working correctly!",
        "timestamp": "2025-01-20T00:00:00Z",
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Basic dashboard endpoint (placeholder for future development)."""
    dashboard_path = Path("static/dashboard.html")

    if dashboard_path.exists():
        with open(dashboard_path, "r") as f:
            return f.read()
    else:
        return """
        <html>
            <head>
                <title>Voice AI Platform - Dashboard</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body>
                <div class="container mt-5">
                    <h1>Voice AI Platform Dashboard</h1>
                    <p class="lead">Dashboard coming soon...</p>
                    <div class="alert alert-info">
                        <strong>Note:</strong> This is the infrastructure setup phase.
                        Dashboard functionality will be implemented in future stories.
                    </div>
                    <a href="/docs" class="btn btn-primary">View API Documentation</a>
                </div>
            </body>
        </html>
        """


if __name__ == "__main__":
    # Development server entry point
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["src"],
    )
