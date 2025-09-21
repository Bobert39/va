"""
Unit tests for EMROAuthClient class.

Tests PKCE generation, authorization URL building, token management,
and error handling without external dependencies.
"""

import base64
import hashlib
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.services.emr import (
    AuthorizationError,
    ConfigurationError,
    EMROAuthClient,
    NetworkError,
    OAuthError,
    RefreshTokenError,
    TokenExpiredError,
)


class TestEMROAuthClient:
    """Test cases for EMROAuthClient."""

    @pytest.fixture
    def oauth_client(self):
        """Create OAuth client instance for testing."""
        return EMROAuthClient(timeout=10, max_retries=2)

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

    def test_pkce_code_generation(self, oauth_client):
        """Test PKCE code verifier and challenge generation."""
        code_verifier, code_challenge = oauth_client.generate_pkce_pair()

        # Verify code verifier length (RFC 7636 requirement)
        assert len(code_verifier) >= 43
        assert len(code_verifier) <= 128

        # Verify code challenge is properly generated
        challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        expected_challenge = (
            base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
        )
        assert code_challenge == expected_challenge

        # Verify URL-safe characters only
        url_safe_chars = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )
        assert all(c in url_safe_chars for c in code_verifier)
        assert all(c in url_safe_chars for c in code_challenge)

    def test_oauth_state_generation(self, oauth_client):
        """Test OAuth state parameter generation."""
        state1 = oauth_client.generate_state()
        state2 = oauth_client.generate_state()

        # Verify states are different
        assert state1 != state2

        # Verify length and URL-safe characters
        assert len(state1) >= 40  # Should be reasonable length
        url_safe_chars = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )
        assert all(c in url_safe_chars for c in state1)

    @patch("src.services.emr.get_config")
    def test_build_authorization_url(
        self, mock_get_config, oauth_client, mock_oauth_config
    ):
        """Test authorization URL building with PKCE."""
        mock_get_config.return_value = mock_oauth_config

        authorization_url, state, code_verifier = oauth_client.build_authorization_url()

        # Verify URL structure
        assert authorization_url.startswith(mock_oauth_config["authorization_endpoint"])
        assert "response_type=code" in authorization_url
        assert f"client_id={mock_oauth_config['client_id']}" in authorization_url
        assert "code_challenge=" in authorization_url
        assert "code_challenge_method=S256" in authorization_url
        assert f"state={state}" in authorization_url

        # Verify scopes are included (check URL-encoded format)
        expected_scopes = "openid+fhirUser+patient%2F%2A.read"
        assert expected_scopes in authorization_url

    @patch("src.services.emr.get_config")
    def test_build_authorization_url_missing_config(
        self, mock_get_config, oauth_client
    ):
        """Test authorization URL building with missing configuration."""
        mock_get_config.return_value = {}

        with pytest.raises(OAuthError) as exc_info:
            oauth_client.build_authorization_url()

        assert "client ID not configured" in str(exc_info.value)

    @patch("src.services.emr.get_config")
    def test_token_validation_valid(
        self, mock_get_config, oauth_client, mock_token_data
    ):
        """Test token validation with valid token."""
        # Token expires in 1 hour (from fixture)
        assert oauth_client.is_token_valid(mock_token_data) is True

    @patch("src.services.emr.get_config")
    def test_token_validation_expired(self, mock_get_config, oauth_client):
        """Test token validation with expired token."""
        expired_token = {
            "access_token": "test_access_token",
            "expires_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        }

        assert oauth_client.is_token_valid(expired_token) is False

    @patch("src.services.emr.get_config")
    def test_token_validation_near_expiry(self, mock_get_config, oauth_client):
        """Test token validation with token near expiry."""
        # Token expires in 2 minutes (within 5-minute buffer)
        near_expiry_token = {
            "access_token": "test_access_token",
            "expires_at": (datetime.utcnow() + timedelta(minutes=2)).isoformat(),
        }

        assert oauth_client.is_token_valid(near_expiry_token) is False

    @patch("src.services.emr.get_config")
    def test_token_validation_no_expiry(self, mock_get_config, oauth_client):
        """Test token validation with missing expiry information."""
        token_no_expiry = {"access_token": "test_access_token"}

        assert oauth_client.is_token_valid(token_no_expiry) is False

    @patch("src.services.emr.get_config")
    def test_needs_refresh(self, mock_get_config, oauth_client, mock_token_data):
        """Test token refresh need detection."""
        # Valid token (expires in 1 hour)
        assert oauth_client.needs_refresh(mock_token_data) is False

        # Token expiring in 2 minutes
        near_expiry_token = {
            "access_token": "test_access_token",
            "expires_at": (datetime.utcnow() + timedelta(minutes=2)).isoformat(),
        }
        assert oauth_client.needs_refresh(near_expiry_token) is True

        # Expired token
        expired_token = {
            "access_token": "test_access_token",
            "expires_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        }
        assert oauth_client.needs_refresh(expired_token) is True

    @patch("src.services.emr.set_config")
    def test_store_tokens(self, mock_set_config, oauth_client, mock_token_data):
        """Test token storage."""
        oauth_client.store_tokens(mock_token_data)

        mock_set_config.assert_called_once_with(
            "oauth_tokens",
            {
                "access_token": mock_token_data["access_token"],
                "refresh_token": mock_token_data["refresh_token"],
                "token_type": mock_token_data["token_type"],
                "expires_at": mock_token_data["expires_at"],
                "scope": mock_token_data["scope"],
            },
        )

    @pytest.mark.asyncio
    @patch("src.services.emr.get_config")
    async def test_exchange_code_for_tokens_success(
        self, mock_get_config, oauth_client, mock_oauth_config
    ):
        """Test successful authorization code exchange."""
        mock_get_config.return_value = mock_oauth_config

        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await oauth_client.exchange_code_for_tokens(
                authorization_code="test_code",
                code_verifier="test_verifier",
                state="test_state",
                expected_state="test_state",
            )

        assert result["access_token"] == "new_access_token"
        assert result["refresh_token"] == "new_refresh_token"
        assert "expires_at" in result

    @pytest.mark.asyncio
    @patch("src.services.emr.get_config")
    async def test_exchange_code_invalid_state(
        self, mock_get_config, oauth_client, mock_oauth_config
    ):
        """Test authorization code exchange with invalid state."""
        mock_get_config.return_value = mock_oauth_config

        with pytest.raises(OAuthError) as exc_info:
            await oauth_client.exchange_code_for_tokens(
                authorization_code="test_code",
                code_verifier="test_verifier",
                state="wrong_state",
                expected_state="correct_state",
            )

        assert "State parameter mismatch" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.services.emr.get_config")
    async def test_exchange_code_http_error(
        self, mock_get_config, oauth_client, mock_oauth_config
    ):
        """Test authorization code exchange with HTTP error."""
        mock_get_config.return_value = mock_oauth_config

        # Mock HTTP error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Authorization code is invalid",
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            with pytest.raises(OAuthError) as exc_info:
                await oauth_client.exchange_code_for_tokens(
                    authorization_code="invalid_code",
                    code_verifier="test_verifier",
                    state="test_state",
                    expected_state="test_state",
                )

        assert exc_info.value.error == "token_exchange_failed"
        assert "Authorization code is invalid" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.services.emr.get_config")
    async def test_refresh_access_token_success(
        self, mock_get_config, oauth_client, mock_oauth_config
    ):
        """Test successful token refresh."""
        mock_get_config.return_value = mock_oauth_config

        # Mock successful refresh response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed_access_token",
            "refresh_token": "new_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            with patch.object(oauth_client, "store_tokens") as mock_store:
                result = await oauth_client.refresh_access_token("old_refresh_token")

        assert result["access_token"] == "refreshed_access_token"
        assert "expires_at" in result
        mock_store.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.emr.get_config")
    async def test_refresh_token_preserve_old_refresh(
        self, mock_get_config, oauth_client, mock_oauth_config
    ):
        """Test token refresh preserves old refresh token if not provided."""
        mock_get_config.return_value = mock_oauth_config

        # Mock response without new refresh token
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            with patch.object(oauth_client, "store_tokens") as mock_store:
                result = await oauth_client.refresh_access_token("old_refresh_token")

        assert result["refresh_token"] == "old_refresh_token"

    @pytest.mark.asyncio
    async def test_http_request_retry_on_connection_error(self, oauth_client):
        """Test HTTP request retry mechanism on connection error."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # First two calls raise ConnectError, third succeeds
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.post.side_effect = [
                httpx.ConnectError("Connection failed"),
                httpx.ConnectError("Connection failed"),
                mock_response,
            ]

            with patch("asyncio.sleep"):  # Mock sleep to speed up test
                result = await oauth_client._http_request_with_retry(
                    "POST", "https://test.com", data={"test": "data"}
                )

            assert result == mock_response
            assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_http_request_max_retries_exceeded(self, oauth_client):
        """Test HTTP request failure after max retries."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # All calls raise ConnectError
            mock_client.post.side_effect = httpx.ConnectError("Connection failed")

            with patch("asyncio.sleep"):  # Mock sleep to speed up test
                with pytest.raises(NetworkError) as exc_info:
                    await oauth_client._http_request_with_retry(
                        "POST", "https://test.com", data={"test": "data"}
                    )

            assert "Failed to connect after 2 attempts" in str(exc_info.value)
            assert mock_client.post.call_count == 3  # Initial attempt + 2 retries

    @patch("src.services.emr.get_config")
    def test_validate_oauth_config_success(
        self, mock_get_config, oauth_client, mock_oauth_config
    ):
        """Test OAuth configuration validation success."""
        mock_get_config.return_value = mock_oauth_config

        result = oauth_client._validate_oauth_config()
        assert result == mock_oauth_config

    @patch("src.services.emr.get_config")
    def test_validate_oauth_config_missing_client_id(
        self, mock_get_config, oauth_client
    ):
        """Test OAuth configuration validation with missing client ID."""
        mock_get_config.return_value = {"client_secret": "secret"}

        with pytest.raises(ConfigurationError) as exc_info:
            oauth_client._validate_oauth_config()

        assert "client ID not configured" in str(exc_info.value)

    @patch("src.services.emr.get_config")
    def test_validate_oauth_config_missing_client_secret(
        self, mock_get_config, oauth_client
    ):
        """Test OAuth configuration validation with missing client secret."""
        mock_get_config.return_value = {"client_id": "test_id"}

        with pytest.raises(ConfigurationError) as exc_info:
            oauth_client._validate_oauth_config()

        assert "client secret not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.services.emr.get_config")
    async def test_ensure_valid_token_no_tokens(self, mock_get_config, oauth_client):
        """Test ensure_valid_token with no stored tokens."""
        mock_get_config.return_value = None

        with pytest.raises(OAuthError) as exc_info:
            await oauth_client.ensure_valid_token()

        assert "No OAuth tokens stored" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.services.emr.get_config")
    async def test_ensure_valid_token_valid_token(
        self, mock_get_config, oauth_client, mock_token_data
    ):
        """Test ensure_valid_token with valid token."""
        with patch.object(
            oauth_client, "get_stored_tokens", return_value=mock_token_data
        ):
            with patch.object(oauth_client, "needs_refresh", return_value=False):
                token = await oauth_client.ensure_valid_token()

        assert token == mock_token_data["access_token"]

    @pytest.mark.asyncio
    @patch("src.services.emr.get_config")
    async def test_ensure_valid_token_refresh_needed(
        self, mock_get_config, oauth_client, mock_token_data
    ):
        """Test ensure_valid_token with refresh needed."""
        refreshed_token = "new_access_token"

        with patch.object(
            oauth_client, "get_stored_tokens", return_value=mock_token_data
        ):
            with patch.object(oauth_client, "needs_refresh", return_value=True):
                with patch.object(
                    oauth_client,
                    "refresh_access_token",
                    return_value={"access_token": refreshed_token},
                ) as mock_refresh:
                    token = await oauth_client.ensure_valid_token()

        assert token == refreshed_token
        mock_refresh.assert_called_once_with(mock_token_data["refresh_token"])


if __name__ == "__main__":
    pytest.main([__file__])
