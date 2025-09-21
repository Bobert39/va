"""
End-to-end tests for OAuth flow.

Tests complete OAuth 2.0 authorization code flow with mock OpenEMR server,
token refresh automation, and error recovery scenarios.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.services.emr import EMROAuthClient, OAuthError, TokenExpiredError


class MockOpenEMRServer:
    """Mock OpenEMR server for E2E testing."""

    def __init__(self):
        self.token_responses = {}
        self.authorization_codes = {}
        self.refresh_tokens = {}

    def register_authorization_code(self, code: str, client_id: str) -> str:
        """Register authorization code for testing."""
        self.authorization_codes[code] = {
            "client_id": client_id,
            "expires_at": datetime.utcnow() + timedelta(minutes=10),
        }
        return code

    def create_token_response(
        self, access_token: str, refresh_token: str, expires_in: int = 3600
    ):
        """Create mock token response."""
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": "openid fhirUser patient/*.read",
        }

    def mock_token_endpoint(self, request_data: dict) -> dict:
        """Mock token endpoint response."""
        if request_data.get("grant_type") == "authorization_code":
            code = request_data.get("code")
            if code not in self.authorization_codes:
                return {
                    "error": "invalid_grant",
                    "error_description": "Authorization code is invalid or expired",
                }

            # Return successful token response
            access_token = f"access_token_{code}"
            refresh_token = f"refresh_token_{code}"
            return self.create_token_response(access_token, refresh_token)

        elif request_data.get("grant_type") == "refresh_token":
            refresh_token = request_data.get("refresh_token")
            if not refresh_token.startswith("refresh_token_"):
                return {
                    "error": "invalid_grant",
                    "error_description": "Refresh token is invalid",
                }

            # Return refreshed token response
            new_access_token = (
                f"refreshed_access_token_{int(datetime.utcnow().timestamp())}"
            )
            new_refresh_token = (
                f"new_refresh_token_{int(datetime.utcnow().timestamp())}"
            )
            return self.create_token_response(new_access_token, new_refresh_token)

        return {
            "error": "unsupported_grant_type",
            "error_description": "Grant type not supported",
        }

    def mock_fhir_metadata(self) -> dict:
        """Mock FHIR metadata endpoint response."""
        return {
            "resourceType": "CapabilityStatement",
            "fhirVersion": "4.0.1",
            "software": {"name": "OpenEMR", "version": "7.0.0"},
            "rest": [
                {
                    "mode": "server",
                    "resource": [
                        {"type": "Patient"},
                        {"type": "Encounter"},
                        {"type": "DiagnosticReport"},
                    ],
                }
            ],
        }


class TestOAuthFlowE2E:
    """End-to-end OAuth flow tests."""

    @pytest.fixture
    def mock_server(self):
        """Create mock OpenEMR server."""
        return MockOpenEMRServer()

    @pytest.fixture
    def oauth_client(self):
        """Create OAuth client for testing."""
        return EMROAuthClient(timeout=5, max_retries=2)

    @pytest.fixture
    def oauth_config(self):
        """OAuth configuration for testing."""
        return {
            "client_id": "test_e2e_client",
            "client_secret": "test_e2e_secret",
            "redirect_uri": "http://localhost:8000/oauth/callback",
            "authorization_endpoint": "https://mock-emr.test/oauth2/authorize",
            "token_endpoint": "https://mock-emr.test/oauth2/token",
            "fhir_base_url": "https://mock-emr.test/apis/default/fhir",
            "scopes": ["openid", "fhirUser", "patient/*.read"],
        }

    @pytest.mark.asyncio
    async def test_complete_oauth_flow(self, oauth_client, oauth_config, mock_server):
        """Test complete OAuth authorization code flow."""
        # Step 1: Build authorization URL
        with patch("src.services.emr.get_config", return_value=oauth_config):
            auth_url, state, code_verifier = oauth_client.build_authorization_url()

        # Verify authorization URL structure
        assert oauth_config["authorization_endpoint"] in auth_url
        assert oauth_config["client_id"] in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url

        # Step 2: Simulate authorization code callback
        authorization_code = "test_auth_code_123"
        mock_server.register_authorization_code(
            authorization_code, oauth_config["client_id"]
        )

        # Step 3: Exchange code for tokens
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_server.mock_token_endpoint(
            {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "client_id": oauth_config["client_id"],
            }
        )

        with patch("src.services.emr.get_config", return_value=oauth_config):
            with patch.object(
                oauth_client, "_http_request_with_retry", return_value=mock_response
            ):
                with patch("src.services.emr.set_config") as mock_set_config:
                    token_response = await oauth_client.exchange_code_for_tokens(
                        authorization_code=authorization_code,
                        code_verifier=code_verifier,
                        state=state,
                        expected_state=state,
                    )

        # Verify token response
        assert "access_token" in token_response
        assert "refresh_token" in token_response
        assert "expires_at" in token_response
        assert token_response["access_token"].startswith("access_token_")
        assert token_response["refresh_token"].startswith("refresh_token_")

        # Verify token storage was called
        mock_set_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_refresh_flow(self, oauth_client, oauth_config, mock_server):
        """Test automatic token refresh flow."""
        # Setup expired token
        expired_token = {
            "access_token": "expired_access_token",
            "refresh_token": "refresh_token_test",
            "expires_at": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
        }

        # Mock refresh response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_server.mock_token_endpoint(
            {"grant_type": "refresh_token", "refresh_token": "refresh_token_test"}
        )

        with patch("src.services.emr.get_config", return_value=oauth_config):
            with patch.object(
                oauth_client, "_http_request_with_retry", return_value=mock_response
            ):
                with patch("src.services.emr.set_config"):
                    refreshed_response = await oauth_client.refresh_access_token(
                        "refresh_token_test"
                    )

        # Verify refreshed tokens
        assert "access_token" in refreshed_response
        assert "refresh_token" in refreshed_response
        assert refreshed_response["access_token"].startswith("refreshed_access_token_")
        assert refreshed_response["refresh_token"].startswith("new_refresh_token_")

    @pytest.mark.asyncio
    async def test_fhir_api_connection_test(
        self, oauth_client, oauth_config, mock_server
    ):
        """Test FHIR API connection with valid token."""
        # Mock valid token
        valid_token = {
            "access_token": "valid_access_token",
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        }

        # Mock FHIR metadata response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_server.mock_fhir_metadata()

        with patch("src.services.emr.get_config", return_value=oauth_config):
            with patch.object(
                oauth_client, "get_stored_tokens", return_value=valid_token
            ):
                with patch.object(oauth_client, "needs_refresh", return_value=False):
                    with patch.object(
                        oauth_client,
                        "_http_request_with_retry",
                        return_value=mock_response,
                    ):
                        result = await oauth_client.test_connection()

        # Verify successful connection
        assert result["status"] == "success"
        assert result["fhir_version"] == "4.0.1"
        assert result["software"] == "OpenEMR"

    @pytest.mark.asyncio
    async def test_token_refresh_with_ensure_valid_token(
        self, oauth_client, oauth_config, mock_server
    ):
        """Test ensure_valid_token with automatic refresh."""
        # Token that needs refresh (expires in 2 minutes)
        near_expiry_token = {
            "access_token": "soon_to_expire_token",
            "refresh_token": "refresh_token_test",
            "expires_at": (datetime.utcnow() + timedelta(minutes=2)).isoformat(),
        }

        # Mock refresh response
        mock_response = Mock()
        mock_response.status_code = 200
        refreshed_data = mock_server.mock_token_endpoint(
            {"grant_type": "refresh_token", "refresh_token": "refresh_token_test"}
        )
        mock_response.json.return_value = refreshed_data

        with patch("src.services.emr.get_config", return_value=oauth_config):
            with patch.object(
                oauth_client, "get_stored_tokens", return_value=near_expiry_token
            ):
                with patch.object(
                    oauth_client, "_http_request_with_retry", return_value=mock_response
                ):
                    with patch("src.services.emr.set_config"):
                        valid_token = await oauth_client.ensure_valid_token()

        # Should return the refreshed access token
        assert valid_token.startswith("refreshed_access_token_")

    @pytest.mark.asyncio
    async def test_error_recovery_invalid_authorization_code(
        self, oauth_client, oauth_config, mock_server
    ):
        """Test error recovery with invalid authorization code."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Authorization code is invalid or expired",
        }

        with patch("src.services.emr.get_config", return_value=oauth_config):
            with patch.object(
                oauth_client, "_http_request_with_retry", return_value=mock_response
            ):
                with pytest.raises(OAuthError) as exc_info:
                    await oauth_client.exchange_code_for_tokens(
                        authorization_code="invalid_code",
                        code_verifier="test_verifier",
                        state="test_state",
                        expected_state="test_state",
                    )

        assert exc_info.value.error == "invalid_grant"
        assert "Authorization code is invalid" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_recovery_invalid_refresh_token(
        self, oauth_client, oauth_config
    ):
        """Test error recovery with invalid refresh token."""
        # Mock error response for invalid refresh token
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Refresh token is invalid",
        }

        with patch("src.services.emr.get_config", return_value=oauth_config):
            with patch.object(
                oauth_client, "_http_request_with_retry", return_value=mock_response
            ):
                with pytest.raises(OAuthError) as exc_info:
                    await oauth_client.refresh_access_token("invalid_refresh_token")

        assert exc_info.value.error == "invalid_grant"
        assert "Refresh token is invalid" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_network_retry_mechanism(self, oauth_client, oauth_config):
        """Test network retry mechanism during token exchange."""
        token_data = {
            "grant_type": "authorization_code",
            "code": "test_code",
            "client_id": oauth_config["client_id"],
        }

        # Mock successful response after retries
        successful_response = Mock()
        successful_response.status_code = 200
        successful_response.json.return_value = {
            "access_token": "retry_success_token",
            "refresh_token": "retry_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        retry_count = 0

        async def mock_request_with_failures(*args, **kwargs):
            nonlocal retry_count
            retry_count += 1
            if retry_count <= 2:
                raise httpx.ConnectError("Connection failed")
            return successful_response

        with patch("src.services.emr.get_config", return_value=oauth_config):
            with patch.object(
                oauth_client,
                "_http_request_with_retry",
                side_effect=mock_request_with_failures,
            ):
                with patch("src.services.emr.set_config"):
                    with patch("asyncio.sleep"):  # Speed up test
                        result = await oauth_client.exchange_code_for_tokens(
                            authorization_code="test_code",
                            code_verifier="test_verifier",
                            state="test_state",
                            expected_state="test_state",
                        )

        # Verify successful result after retries
        assert result["access_token"] == "retry_success_token"
        assert retry_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_fhir_api_unauthorized_response(self, oauth_client, oauth_config):
        """Test FHIR API response when token is unauthorized."""
        # Mock valid-looking token that's actually unauthorized
        token_data = {
            "access_token": "unauthorized_token",
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        }

        # Mock 401 Unauthorized response from FHIR API
        mock_response = Mock()
        mock_response.status_code = 401

        with patch("src.services.emr.get_config", return_value=oauth_config):
            with patch.object(
                oauth_client, "get_stored_tokens", return_value=token_data
            ):
                with patch.object(oauth_client, "needs_refresh", return_value=False):
                    with patch.object(
                        oauth_client,
                        "_http_request_with_retry",
                        return_value=mock_response,
                    ):
                        result = await oauth_client.test_connection()

        # Verify appropriate error response
        assert result["status"] == "error"
        assert result["error"] == "unauthorized"
        assert "Access token is invalid or expired" in result["message"]

    @pytest.mark.asyncio
    async def test_state_parameter_csrf_protection(self, oauth_client, oauth_config):
        """Test CSRF protection via state parameter validation."""
        with patch("src.services.emr.get_config", return_value=oauth_config):
            with pytest.raises(OAuthError) as exc_info:
                await oauth_client.exchange_code_for_tokens(
                    authorization_code="test_code",
                    code_verifier="test_verifier",
                    state="attacker_state",
                    expected_state="legitimate_state",
                )

        assert "State parameter mismatch" in str(exc_info.value)
        assert "CSRF attack" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__])
