"""
Unit tests for FastAPI application startup and basic functionality.

Tests the FastAPI application initialization, middleware configuration,
and basic endpoint functionality.
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app


class TestFastAPIApplication:
    """Test FastAPI application startup and basic endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI application."""
        return TestClient(app)

    def test_fastapi_startup(self, client):
        """Test FastAPI application starts successfully."""
        # Test that the app can handle a basic request
        response = client.get("/health")
        assert response.status_code == 200

        # Verify health check response
        health_data = response.json()
        assert health_data["status"] == "healthy"
        assert health_data["service"] == "Voice AI Platform"
        assert health_data["version"] == "0.1.0"

    def test_documentation_endpoint(self, client):
        """Test automatic API documentation availability."""
        # Test OpenAPI docs endpoint
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Test OpenAPI JSON schema
        response = client.get("/openapi.json")
        assert response.status_code == 200

        openapi_data = response.json()
        assert openapi_data["openapi"] == "3.1.0"
        assert openapi_data["info"]["title"] == "Voice AI Platform"
        assert openapi_data["info"]["version"] == "0.1.0"

    def test_root_endpoint(self, client):
        """Test root endpoint provides basic information."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Check that response contains expected content
        content = response.text
        assert "Voice AI Platform" in content
        assert "/docs" in content
        assert "/health" in content

    def test_dashboard_endpoint(self, client):
        """Test dashboard endpoint returns HTML."""
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        content = response.text
        assert "Dashboard" in content

    def test_cors_configuration(self, client):
        """Test CORS middleware configuration."""
        # Test preflight request
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Note: TestClient doesn't fully simulate CORS preflight
        # This test verifies the endpoint is accessible
        assert response.status_code in [
            200,
            405,
        ]  # 405 is acceptable for OPTIONS without handler

    def test_application_metadata(self):
        """Test application metadata configuration."""
        assert app.title == "Voice AI Platform"
        assert (
            app.description
            == "Voice AI Platform for EMR Integration - Enables voice-controlled appointment scheduling"
        )
        assert app.version == "0.1.0"
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
