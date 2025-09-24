"""
EMR Integration Service with OAuth 2.0 Authentication

This module provides secure OAuth 2.0 authentication for OpenEMR integration,
implementing authorization code flow with PKCE for enhanced security.
"""

import asyncio
import base64
import hashlib
import logging
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import httpx

from ..config import get_config, set_config

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """OAuth authentication error."""

    def __init__(self, error: str, description: str = "", error_uri: str = ""):
        self.error = error
        self.description = description
        self.error_uri = error_uri
        super().__init__(f"OAuth Error: {error} - {description}")


class TokenExpiredError(OAuthError):
    """Token has expired and needs refresh."""

    def __init__(self, message: str = "Access token has expired"):
        super().__init__("token_expired", message)


class ConfigurationError(OAuthError):
    """OAuth configuration is invalid or missing."""

    def __init__(self, message: str = "OAuth configuration error"):
        super().__init__("configuration_error", message)


class NetworkError(OAuthError):
    """Network connectivity error during OAuth operations."""

    def __init__(self, message: str = "Network connection failed"):
        super().__init__("network_error", message)


class AuthorizationError(OAuthError):
    """Authorization flow error (invalid code, state, etc.)."""

    def __init__(self, message: str = "Authorization flow error"):
        super().__init__("authorization_error", message)


class RefreshTokenError(OAuthError):
    """Refresh token operation failed."""

    def __init__(self, message: str = "Token refresh failed"):
        super().__init__("refresh_token_error", message)


class EMROAuthClient:
    """
    OAuth 2.0 client for OpenEMR integration.

    Implements secure authorization code flow with PKCE (Proof Key for Code Exchange)
    for enhanced security. Handles token storage, refresh, and automatic renewal.
    """

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        Initialize OAuth client.

        Args:
            timeout: HTTP request timeout in seconds
            max_retries: Maximum number of retry attempts for network errors
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self._config_cache = None
        self._config_cache_time = 0
        self._cache_ttl = 300  # 5 minutes cache TTL

    def _get_oauth_config(self) -> Dict[str, Any]:
        """Get OAuth configuration with caching."""
        current_time = time.time()

        if (
            self._config_cache is None
            or current_time - self._config_cache_time > self._cache_ttl
        ):
            self._config_cache = get_config("oauth_config", {})
            self._config_cache_time = current_time

        return self._config_cache

    def _clear_config_cache(self):
        """Clear configuration cache."""
        self._config_cache = None
        self._config_cache_time = 0

    async def _http_request_with_retry(
        self,
        method: str,
        url: str,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        retry_count: int = 0,
    ) -> httpx.Response:
        """
        Make HTTP request with exponential backoff retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            data: Request data for POST requests
            headers: Request headers
            retry_count: Current retry attempt

        Returns:
            HTTP response

        Raises:
            NetworkError: If all retry attempts fail
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if method.upper() == "POST":
                    response = await client.post(url, data=data, headers=headers)
                else:
                    response = await client.get(url, headers=headers)
                return response

        except httpx.ConnectError as e:
            if retry_count < self.max_retries:
                # Exponential backoff: 1s, 2s, 4s
                delay = 2**retry_count
                logger.warning(
                    f"Connection failed, retrying in {delay}s (attempt {retry_count + 1}/{self.max_retries})"
                )
                await asyncio.sleep(delay)
                return await self._http_request_with_retry(
                    method, url, data, headers, retry_count + 1
                )
            else:
                logger.error(
                    f"Connection failed after {self.max_retries} attempts: {e}"
                )
                raise NetworkError(
                    f"Failed to connect after {self.max_retries} attempts: {e}"
                )

        except httpx.TimeoutException as e:
            if retry_count < self.max_retries:
                delay = 2**retry_count
                logger.warning(
                    f"Request timeout, retrying in {delay}s (attempt {retry_count + 1}/{self.max_retries})"
                )
                await asyncio.sleep(delay)
                return await self._http_request_with_retry(
                    method, url, data, headers, retry_count + 1
                )
            else:
                logger.error(f"Request timeout after {self.max_retries} attempts: {e}")
                raise NetworkError(
                    f"Request timeout after {self.max_retries} attempts: {e}"
                )

        except httpx.RequestError as e:
            logger.error(f"HTTP request error: {e}")
            raise NetworkError(f"HTTP request failed: {e}")

    def _validate_oauth_config(self) -> Dict[str, Any]:
        """
        Validate OAuth configuration and return it.

        Returns:
            Valid OAuth configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        oauth_config = self._get_oauth_config()

        if not oauth_config.get("client_id"):
            raise ConfigurationError("OAuth client ID not configured")

        if not oauth_config.get("client_secret"):
            raise ConfigurationError("OAuth client secret not configured")

        return oauth_config

    def generate_pkce_pair(self) -> Tuple[str, str]:
        """
        Generate PKCE code verifier and challenge pair.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code verifier (43-128 characters, URL-safe)
        code_verifier = (
            base64.urlsafe_b64encode(secrets.token_bytes(32))
            .decode("utf-8")
            .rstrip("=")
        )

        # Generate code challenge (SHA256 hash of verifier)
        challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = (
            base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
        )

        return code_verifier, code_challenge

    def generate_state(self) -> str:
        """
        Generate OAuth state parameter for CSRF protection.

        Returns:
            Random state string
        """
        return (
            base64.urlsafe_b64encode(secrets.token_bytes(32))
            .decode("utf-8")
            .rstrip("=")
        )

    def build_authorization_url(
        self,
        state: Optional[str] = None,
        code_challenge: Optional[str] = None,
        scopes: Optional[list] = None,
    ) -> Tuple[str, str, str]:
        """
        Build OAuth authorization URL with PKCE.

        Args:
            state: OAuth state parameter (generated if not provided)
            code_challenge: PKCE code challenge (generated if not provided)
            scopes: OAuth scopes list (uses default if not provided)

        Returns:
            Tuple of (authorization_url, state, code_verifier)
        """
        oauth_config = self._get_oauth_config()

        if not oauth_config.get("client_id"):
            raise OAuthError("invalid_configuration", "OAuth client ID not configured")

        if not oauth_config.get("authorization_endpoint"):
            raise OAuthError(
                "invalid_configuration", "OAuth authorization endpoint not configured"
            )

        # Generate PKCE pair if challenge not provided
        if code_challenge is None:
            code_verifier, code_challenge = self.generate_pkce_pair()
        else:
            code_verifier = ""  # Will need to be provided separately

        # Generate state if not provided
        if state is None:
            state = self.generate_state()

        # Default scopes for FHIR R4 access
        if scopes is None:
            scopes = [
                "openid",
                "fhirUser",
                "patient/*.read",
                "patient/*.write",
                "Patient.read",
                "Encounter.read",
                "DiagnosticReport.read",
                "Medication.read",
            ]

        # Build authorization URL parameters
        auth_params = {
            "response_type": "code",
            "client_id": oauth_config["client_id"],
            "redirect_uri": oauth_config.get(
                "redirect_uri", "http://localhost:8000/oauth/callback"
            ),
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        # Build full authorization URL
        base_url = oauth_config["authorization_endpoint"]
        query_string = urllib.parse.urlencode(auth_params)
        authorization_url = f"{base_url}?{query_string}"

        logger.info(
            f"Generated OAuth authorization URL for client: {oauth_config['client_id']}"
        )

        return authorization_url, state, code_verifier

    async def exchange_code_for_tokens(
        self,
        authorization_code: str,
        code_verifier: str,
        state: str,
        expected_state: str,
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            authorization_code: Authorization code from callback
            code_verifier: PKCE code verifier
            state: State parameter from callback
            expected_state: Expected state value for validation

        Returns:
            Token response dictionary

        Raises:
            OAuthError: If token exchange fails
        """
        # Validate state parameter (CSRF protection)
        if state != expected_state:
            raise OAuthError(
                "invalid_state", "State parameter mismatch - possible CSRF attack"
            )

        oauth_config = self._get_oauth_config()

        if not oauth_config.get("token_endpoint"):
            raise OAuthError(
                "invalid_configuration", "OAuth token endpoint not configured"
            )

        # Prepare token exchange request
        token_data = {
            "grant_type": "authorization_code",
            "client_id": oauth_config["client_id"],
            "client_secret": oauth_config.get("client_secret", ""),
            "code": authorization_code,
            "redirect_uri": oauth_config.get(
                "redirect_uri", "http://localhost:8000/oauth/callback"
            ),
            "code_verifier": code_verifier,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    oauth_config["token_endpoint"], data=token_data, headers=headers
                )

                if response.status_code != 200:
                    error_data = (
                        response.json()
                        if response.headers.get("content-type", "").startswith(
                            "application/json"
                        )
                        else {}
                    )
                    error = error_data.get("error", "token_exchange_failed")
                    description = error_data.get(
                        "error_description", f"HTTP {response.status_code}"
                    )
                    raise OAuthError(error, description)

                token_response = response.json()

                # Validate required token fields
                if "access_token" not in token_response:
                    raise OAuthError(
                        "invalid_token_response", "No access token in response"
                    )

                # Calculate token expiration time
                expires_in = token_response.get("expires_in", 3600)  # Default 1 hour
                expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                token_response["expires_at"] = expires_at.isoformat()

                logger.info("Successfully exchanged authorization code for tokens")
                return token_response

        except httpx.RequestError as e:
            logger.error(f"Network error during token exchange: {e}")
            raise OAuthError(
                "network_error", f"Failed to connect to token endpoint: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during token exchange: {e}")
            raise OAuthError("token_exchange_failed", str(e))

    def store_tokens(self, token_response: Dict[str, Any]) -> None:
        """
        Store OAuth tokens in encrypted configuration.

        Args:
            token_response: Token response from OAuth server
        """
        token_data = {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token", ""),
            "token_type": token_response.get("token_type", "Bearer"),
            "expires_at": token_response["expires_at"],
            "scope": token_response.get("scope", ""),
        }

        set_config("oauth_tokens", token_data)
        logger.info("OAuth tokens stored successfully")

    def get_stored_tokens(self) -> Optional[Dict[str, Any]]:
        """
        Get stored OAuth tokens from configuration.

        Returns:
            Token data dictionary or None if no tokens stored
        """
        return get_config("oauth_tokens")

    def is_token_valid(self, token_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if stored access token is valid and not expired.

        Args:
            token_data: Token data (gets from config if not provided)

        Returns:
            True if token is valid and not expired
        """
        if token_data is None:
            token_data = self.get_stored_tokens()

        if not token_data or not token_data.get("access_token"):
            return False

        expires_at = token_data.get("expires_at")
        if not expires_at:
            return False

        try:
            expiry_time = datetime.fromisoformat(expires_at)
            # Consider token expired if it expires within 5 minutes
            buffer_time = timedelta(minutes=5)
            return datetime.utcnow() + buffer_time < expiry_time
        except (ValueError, TypeError):
            logger.warning("Invalid token expiration format")
            return False

    async def get_valid_access_token(self) -> str:
        """
        Get valid access token, refreshing if necessary.

        Returns:
            Valid access token

        Raises:
            TokenExpiredError: If token is expired and can't be refreshed
            OAuthError: If no tokens are stored or refresh fails
        """
        token_data = self.get_stored_tokens()

        if not token_data:
            raise OAuthError(
                "no_tokens",
                "No OAuth tokens stored. Please complete authorization flow.",
            )

        if self.is_token_valid(token_data):
            return token_data["access_token"]

        # Token is expired, need to refresh
        if not token_data.get("refresh_token"):
            raise TokenExpiredError(
                "Access token expired and no refresh token available"
            )

        # Attempt to refresh the token
        try:
            refreshed_tokens = await self.refresh_access_token(
                token_data["refresh_token"]
            )
            return refreshed_tokens["access_token"]
        except OAuthError as e:
            logger.error(f"Failed to refresh token: {e}")
            raise TokenExpiredError(
                f"Token expired and refresh failed: {e.description}"
            )

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Current refresh token

        Returns:
            New token response with refreshed tokens

        Raises:
            OAuthError: If token refresh fails
        """
        oauth_config = self._get_oauth_config()

        if not oauth_config.get("token_endpoint"):
            raise OAuthError(
                "invalid_configuration", "OAuth token endpoint not configured"
            )

        # Prepare token refresh request
        refresh_data = {
            "grant_type": "refresh_token",
            "client_id": oauth_config["client_id"],
            "client_secret": oauth_config.get("client_secret", ""),
            "refresh_token": refresh_token,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    oauth_config["token_endpoint"], data=refresh_data, headers=headers
                )

                if response.status_code != 200:
                    error_data = (
                        response.json()
                        if response.headers.get("content-type", "").startswith(
                            "application/json"
                        )
                        else {}
                    )
                    error = error_data.get("error", "token_refresh_failed")
                    description = error_data.get(
                        "error_description", f"HTTP {response.status_code}"
                    )

                    # Log refresh failure for audit
                    logger.warning(f"Token refresh failed: {error} - {description}")
                    raise OAuthError(error, description)

                token_response = response.json()

                # Validate required token fields
                if "access_token" not in token_response:
                    raise OAuthError(
                        "invalid_token_response", "No access token in refresh response"
                    )

                # Calculate token expiration time
                expires_in = token_response.get("expires_in", 3600)  # Default 1 hour
                expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                token_response["expires_at"] = expires_at.isoformat()

                # Preserve refresh token if not provided in response (some servers don't rotate)
                if "refresh_token" not in token_response:
                    token_response["refresh_token"] = refresh_token

                # Store the refreshed tokens
                self.store_tokens(token_response)

                logger.info("Successfully refreshed access token")
                return token_response

        except httpx.RequestError as e:
            logger.error(f"Network error during token refresh: {e}")
            raise OAuthError(
                "network_error", f"Failed to connect to token endpoint: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}")
            raise OAuthError("token_refresh_failed", str(e))

    def needs_refresh(
        self, token_data: Optional[Dict[str, Any]] = None, buffer_minutes: int = 5
    ) -> bool:
        """
        Check if token needs refreshing based on expiration time.

        Args:
            token_data: Token data (gets from config if not provided)
            buffer_minutes: Minutes before expiration to consider refresh needed

        Returns:
            True if token should be refreshed
        """
        if token_data is None:
            token_data = self.get_stored_tokens()

        if not token_data or not token_data.get("access_token"):
            return False

        expires_at = token_data.get("expires_at")
        if not expires_at:
            return True  # No expiration info, better refresh

        try:
            expiry_time = datetime.fromisoformat(expires_at)
            buffer_time = timedelta(minutes=buffer_minutes)
            return datetime.utcnow() + buffer_time >= expiry_time
        except (ValueError, TypeError):
            logger.warning("Invalid token expiration format")
            return True  # Invalid format, better refresh

    async def ensure_valid_token(self) -> str:
        """
        Ensure we have a valid access token, refreshing if necessary.

        Returns:
            Valid access token

        Raises:
            OAuthError: If no tokens are stored or authentication fails
            TokenExpiredError: If token refresh fails
        """
        token_data = self.get_stored_tokens()

        if not token_data:
            raise OAuthError(
                "no_tokens",
                "No OAuth tokens stored. Please complete authorization flow.",
            )

        # Check if refresh is needed
        if self.needs_refresh(token_data):
            if not token_data.get("refresh_token"):
                raise TokenExpiredError(
                    "Access token expired and no refresh token available"
                )

            try:
                refreshed_tokens = await self.refresh_access_token(
                    token_data["refresh_token"]
                )
                return refreshed_tokens["access_token"]
            except OAuthError as e:
                logger.error(f"Failed to refresh token: {e}")
                raise TokenExpiredError(
                    f"Token expired and refresh failed: {e.description}"
                )

        return token_data["access_token"]

    async def create_appointment(
        self, appointment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create appointment in OpenEMR.

        Args:
            appointment_data: Appointment data in EMR format

        Returns:
            Created appointment details

        Raises:
            OAuthError: If authentication fails
            httpx.RequestError: If network error occurs
        """
        try:
            access_token = await self.ensure_valid_token()
        except (OAuthError, TokenExpiredError) as e:
            logger.error(f"Authentication failed for appointment creation: {e}")
            raise

        oauth_config = self._get_oauth_config()
        base_url = oauth_config.get("base_url")

        if not base_url:
            raise ConfigurationError("EMR base URL not configured")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        appointment_endpoint = oauth_config.get(
            "appointment_endpoint", "/apis/default/api/appointment"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{base_url}{appointment_endpoint}",
                    json=appointment_data,
                    headers=headers,
                )

                if response.status_code == 201:
                    created_appointment = response.json()
                    logger.info(
                        f"Successfully created appointment: {created_appointment.get('id')}"
                    )
                    return created_appointment
                elif response.status_code == 401:
                    raise OAuthError("unauthorized", "Authentication failed")
                elif response.status_code == 400:
                    error_detail = response.json() if response.content else {}
                    raise OAuthError(
                        "bad_request", f"Invalid appointment data: {error_detail}"
                    )
                else:
                    raise OAuthError(
                        "api_error",
                        f"API request failed with status {response.status_code}: {response.text}",
                    )

        except httpx.RequestError as e:
            logger.error(f"Network error creating appointment: {e}")
            raise NetworkError(f"Failed to connect to EMR: {e}")

    async def update_appointment(
        self, appointment_id: str, update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update existing appointment in OpenEMR.

        Args:
            appointment_id: EMR appointment ID
            update_data: Updated appointment data

        Returns:
            Updated appointment details

        Raises:
            OAuthError: If authentication fails
            httpx.RequestError: If network error occurs
        """
        try:
            access_token = await self.ensure_valid_token()
        except (OAuthError, TokenExpiredError) as e:
            logger.error(f"Authentication failed for appointment update: {e}")
            raise

        oauth_config = self._get_oauth_config()
        base_url = oauth_config.get("base_url")

        if not base_url:
            raise ConfigurationError("EMR base URL not configured")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        appointment_endpoint = oauth_config.get(
            "appointment_endpoint", "/apis/default/api/appointment"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.put(
                    f"{base_url}{appointment_endpoint}/{appointment_id}",
                    json=update_data,
                    headers=headers,
                )

                if response.status_code == 200:
                    updated_appointment = response.json()
                    logger.info(f"Successfully updated appointment: {appointment_id}")
                    return updated_appointment
                elif response.status_code == 404:
                    raise OAuthError(
                        "not_found", f"Appointment {appointment_id} not found"
                    )
                elif response.status_code == 401:
                    raise OAuthError("unauthorized", "Authentication failed")
                else:
                    raise OAuthError(
                        "api_error",
                        f"API request failed with status {response.status_code}: {response.text}",
                    )

        except httpx.RequestError as e:
            logger.error(f"Network error updating appointment: {e}")
            raise NetworkError(f"Failed to connect to EMR: {e}")

    async def cancel_appointment(
        self, appointment_id: str, cancellation_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel appointment in OpenEMR.

        Args:
            appointment_id: EMR appointment ID
            cancellation_reason: Optional reason for cancellation

        Returns:
            Cancellation confirmation

        Raises:
            OAuthError: If authentication fails
            httpx.RequestError: If network error occurs
        """
        update_data = {"pc_apptstatus": "cancelled"}

        if cancellation_reason:
            update_data["pc_hometext"] = cancellation_reason

        result = await self.update_appointment(appointment_id, update_data)
        logger.info(f"Successfully cancelled appointment: {appointment_id}")
        return result

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test OAuth connection to OpenEMR FHIR API.

        Returns:
            Connection test results

        Raises:
            OAuthError: If connection test fails
        """
        try:
            access_token = await self.ensure_valid_token()
        except (OAuthError, TokenExpiredError) as e:
            return {
                "status": "error",
                "error": "authentication_required",
                "message": str(e),
            }

        oauth_config = self._get_oauth_config()
        fhir_base_url = oauth_config.get("fhir_base_url")

        if not fhir_base_url:
            return {
                "status": "error",
                "error": "configuration_error",
                "message": "FHIR base URL not configured",
            }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/fhir+json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Test with metadata endpoint (doesn't require patient access)
                response = await client.get(
                    f"{fhir_base_url}/metadata", headers=headers
                )

                if response.status_code == 200:
                    metadata = response.json()
                    fhir_version = metadata.get("fhirVersion", "unknown")
                    software_name = metadata.get("software", {}).get("name", "unknown")

                    return {
                        "status": "success",
                        "fhir_version": fhir_version,
                        "software": software_name,
                        "message": "OAuth connection successful",
                    }
                elif response.status_code == 401:
                    return {
                        "status": "error",
                        "error": "unauthorized",
                        "message": "Access token is invalid or expired",
                    }
                else:
                    return {
                        "status": "error",
                        "error": "api_error",
                        "message": f"FHIR API returned HTTP {response.status_code}",
                    }

        except httpx.RequestError as e:
            logger.error(f"Network error testing OAuth connection: {e}")
            return {
                "status": "error",
                "error": "network_error",
                "message": f"Failed to connect to FHIR API: {e}",
            }
        except Exception as e:
            logger.error(f"Unexpected error testing OAuth connection: {e}")
            return {"status": "error", "error": "unexpected_error", "message": str(e)}


# Global OAuth client instance
oauth_client = EMROAuthClient()
