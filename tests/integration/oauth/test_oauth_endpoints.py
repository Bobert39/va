"""
Integration tests for OAuth endpoints.

Tests OAuth API endpoints with mock OpenEMR responses,
configuration integration, and audit logging.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services.emr import EMROAuthClient


class TestOAuthEndpoints:
    """Test cases for OAuth API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_oauth_config(self):
        """Mock OAuth configuration."""
        return {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "redirect_uri": "http://localhost:8000/oauth/callback",
            "authorization_endpoint": "https://test-emr.com/oauth2/authorize",
            "token_endpoint": "https://test-emr.com/oauth2/token",
            "fhir_base_url": "https://test-emr.com/apis/default/fhir",
            "scopes": ["openid", "fhirUser", "patient/*.read"],
        }

    @pytest.fixture
    def mock_token_data(self):
        """Mock token data."""
        expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        return {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_at": expires_at,
            "scope": "openid fhirUser patient/*.read",
        }

    @patch("src.main.oauth_client")
    @patch("src.main.audit_logger")
    def test_oauth_authorize_success(self, mock_audit, mock_oauth_client, client):
        """Test OAuth authorization endpoint success."""
        # Mock OAuth client methods
        mock_oauth_client.build_authorization_url.return_value = (
            "https://test-emr.com/oauth2/authorize?response_type=code&client_id=test",
            "test_state",
            "test_verifier",
        )
        mock_oauth_client._get_oauth_config.return_value = {"client_id": "test_client"}

        response = client.get("/oauth/authorize")

        assert response.status_code == 302
        assert response.headers["location"].startswith(
            "https://test-emr.com/oauth2/authorize"
        )
        mock_audit.log_event.assert_called_once()

    @patch("src.main.oauth_client")
    @patch("src.main.audit_logger")
    def test_oauth_authorize_configuration_error(
        self, mock_audit, mock_oauth_client, client
    ):
        """Test OAuth authorization with configuration error."""
        from src.services.emr import ConfigurationError

        mock_oauth_client.build_authorization_url.side_effect = ConfigurationError(
            "OAuth client ID not configured"
        )

        response = client.get("/oauth/authorize")

        assert response.status_code == 400
        assert "OAuth configuration error" in response.json()["detail"]
        mock_audit.log_event.assert_called_once()

    @patch("src.main.oauth_client")
    @patch("src.main.audit_logger")
    def test_oauth_callback_success(self, mock_audit, mock_oauth_client, client):
        """Test OAuth callback endpoint success."""
        # Set up session state
        from src.main import oauth_sessions

        test_state = "test_state_123"
        oauth_sessions[test_state] = {
            "code_verifier": "test_verifier",
            "timestamp": "2023-01-01T00:00:00Z",
        }

        # Mock token exchange
        mock_token_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        }
        mock_oauth_client.exchange_code_for_tokens = AsyncMock(
            return_value=mock_token_response
        )
        mock_oauth_client.store_tokens = Mock()

        response = client.get(f"/oauth/callback?code=test_code&state={test_state}")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "success"
        assert "OAuth authentication completed" in response_data["message"]

        # Verify session cleanup
        assert test_state not in oauth_sessions

        # Verify audit logging
        mock_audit.log_event.assert_called()

    @patch("src.main.oauth_client")
    @patch("src.main.audit_logger")
    def test_oauth_callback_invalid_state(self, mock_audit, mock_oauth_client, client):
        """Test OAuth callback with invalid state."""
        response = client.get("/oauth/callback?code=test_code&state=invalid_state")

        assert response.status_code == 400
        assert "Invalid OAuth state parameter" in response.json()["detail"]
        mock_audit.log_event.assert_called_once()

    @patch("src.main.oauth_client")
    @patch("src.main.audit_logger")
    def test_oauth_callback_token_exchange_error(
        self, mock_audit, mock_oauth_client, client
    ):
        """Test OAuth callback with token exchange error."""
        # Set up session state
        from src.main import oauth_sessions
        from src.services.emr import OAuthError

        test_state = "test_state_123"
        oauth_sessions[test_state] = {
            "code_verifier": "test_verifier",
            "timestamp": "2023-01-01T00:00:00Z",
        }

        # Mock token exchange error
        mock_oauth_client.exchange_code_for_tokens = AsyncMock(
            side_effect=OAuthError("invalid_grant", "Authorization code expired")
        )

        response = client.get(f"/oauth/callback?code=expired_code&state={test_state}")

        assert response.status_code == 400
        assert "OAuth error" in response.json()["detail"]

        # Verify session cleanup on error
        assert test_state not in oauth_sessions

    @patch("src.main.oauth_client")
    def test_oauth_status_authenticated(
        self, mock_oauth_client, client, mock_token_data
    ):
        """Test OAuth status endpoint with authenticated user."""
        mock_oauth_client.get_stored_tokens.return_value = mock_token_data
        mock_oauth_client.is_token_valid.return_value = True

        response = client.get("/api/v1/oauth/status")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["authenticated"] is True
        assert response_data["expires_at"] == mock_token_data["expires_at"]
        assert response_data["error"] == ""

    @patch("src.main.oauth_client")
    def test_oauth_status_not_authenticated(self, mock_oauth_client, client):
        """Test OAuth status endpoint with no tokens."""
        mock_oauth_client.get_stored_tokens.return_value = None

        response = client.get("/api/v1/oauth/status")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["authenticated"] is False
        assert "No OAuth tokens found" in response_data["error"]

    @patch("src.main.oauth_client")
    def test_oauth_status_token_expired(
        self, mock_oauth_client, client, mock_token_data
    ):
        """Test OAuth status endpoint with expired token."""
        expired_token = mock_token_data.copy()
        expired_token["expires_at"] = (
            datetime.utcnow() - timedelta(hours=1)
        ).isoformat()

        mock_oauth_client.get_stored_tokens.return_value = expired_token
        mock_oauth_client.is_token_valid.return_value = False

        response = client.get("/api/v1/oauth/status")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["authenticated"] is False
        assert "Token expired" in response_data["error"]

    @patch("src.main.oauth_client")
    @patch("src.main.audit_logger")
    def test_oauth_test_success(self, mock_audit, mock_oauth_client, client):
        """Test OAuth connection test success."""
        mock_oauth_client.test_connection = AsyncMock(
            return_value={
                "status": "success",
                "fhir_version": "4.0.1",
                "software": "OpenEMR",
                "message": "Connection successful",
            }
        )

        response = client.post("/api/v1/oauth/test")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "success"
        assert response_data["fhir_version"] == "4.0.1"
        assert response_data["software"] == "OpenEMR"
        assert "Connection successful" in response_data["message"]

        mock_audit.log_event.assert_called_once()

    @patch("src.main.oauth_client")
    @patch("src.main.audit_logger")
    def test_oauth_test_authentication_error(
        self, mock_audit, mock_oauth_client, client
    ):
        """Test OAuth connection test with authentication error."""
        mock_oauth_client.test_connection = AsyncMock(
            return_value={
                "status": "error",
                "error": "authentication_required",
                "message": "No OAuth tokens stored",
            }
        )

        response = client.post("/api/v1/oauth/test")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "error"
        assert response_data["error"] == "authentication_required"
        assert "No OAuth tokens stored" in response_data["message"]

    @patch("src.main.oauth_client")
    @patch("src.main.audit_logger")
    def test_oauth_test_network_error(self, mock_audit, mock_oauth_client, client):
        """Test OAuth connection test with network error."""
        mock_oauth_client.test_connection = AsyncMock(
            return_value={
                "status": "error",
                "error": "network_error",
                "message": "Failed to connect to FHIR API",
            }
        )

        response = client.post("/api/v1/oauth/test")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "error"
        assert response_data["error"] == "network_error"
        assert "Failed to connect to FHIR API" in response_data["message"]

    @patch("src.main.oauth_client")
    @patch("src.main.audit_logger")
    def test_oauth_test_unexpected_error(self, mock_audit, mock_oauth_client, client):
        """Test OAuth connection test with unexpected error."""
        mock_oauth_client.test_connection = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        response = client.post("/api/v1/oauth/test")

        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "error"
        assert "Unexpected error during connection test" in response_data["message"]

    def test_oauth_session_management(self, client):
        """Test OAuth session state management."""
        from src.main import oauth_sessions

        # Clear any existing sessions
        oauth_sessions.clear()

        # Verify empty sessions
        assert len(oauth_sessions) == 0

        # Add test session
        test_state = "test_session_state"
        oauth_sessions[test_state] = {
            "code_verifier": "test_verifier",
            "timestamp": "2023-01-01T00:00:00Z",
        }

        assert test_state in oauth_sessions
        assert oauth_sessions[test_state]["code_verifier"] == "test_verifier"

        # Clean up
        del oauth_sessions[test_state]
        assert test_state not in oauth_sessions


class TestOAuthConfigurationIntegration:
    """Test OAuth configuration integration."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @patch("src.services.emr.get_config")
    def test_oauth_config_caching(self, mock_get_config):
        """Test OAuth configuration caching."""
        oauth_config = {"client_id": "test_client", "client_secret": "test_secret"}
        mock_get_config.return_value = oauth_config

        oauth_client = EMROAuthClient()

        # First call should trigger config loading
        config1 = oauth_client._get_oauth_config()
        assert config1 == oauth_config

        # Second call within cache TTL should use cached config
        config2 = oauth_client._get_oauth_config()
        assert config2 == oauth_config

        # get_config should only be called once due to caching
        assert mock_get_config.call_count == 1

    @patch("src.services.emr.get_config")
    @patch("src.services.emr.set_config")
    def test_token_storage_integration(self, mock_set_config, mock_get_config):
        """Test token storage integration with configuration system."""
        oauth_client = EMROAuthClient()

        token_data = {
            "access_token": "test_token",
            "refresh_token": "test_refresh",
            "token_type": "Bearer",
            "expires_at": "2023-12-31T23:59:59",
            "scope": "openid fhirUser",
        }

        oauth_client.store_tokens(token_data)

        expected_stored_data = {
            "access_token": "test_token",
            "refresh_token": "test_refresh",
            "token_type": "Bearer",
            "expires_at": "2023-12-31T23:59:59",
            "scope": "openid fhirUser",
        }

        mock_set_config.assert_called_once_with("oauth_tokens", expected_stored_data)


if __name__ == "__main__":
    pytest.main([__file__])
