"""
Unit tests for Twilio Integration Service.

Tests Twilio Voice API integration, webhook handling,
phone number configuration, and call management.
"""

from unittest.mock import MagicMock, patch

import pytest
from twilio.twiml.voice_response import VoiceResponse

from src.services.twilio_integration import TwilioIntegrationService


class TestTwilioIntegrationService:
    """Test cases for Twilio Integration Service."""

    @pytest.fixture
    def service(self):
        """Create a fresh Twilio service instance for each test."""
        with patch("src.services.twilio_integration.get_config") as mock_config:
            mock_config.side_effect = lambda key: {
                "api_keys.twilio_account_sid": "test_account_sid",
                "api_keys.twilio_auth_token": "test_auth_token",
            }.get(key)
            return TwilioIntegrationService()

    @pytest.fixture
    def mock_twilio_client(self):
        """Mock Twilio client for testing."""
        client = MagicMock()
        return client

    def test_initialization_with_credentials(self):
        """Test service initialization with valid credentials."""
        with patch("src.services.twilio_integration.get_config") as mock_config:
            mock_config.side_effect = lambda key: {
                "api_keys.twilio_account_sid": "test_sid",
                "api_keys.twilio_auth_token": "test_token",
            }.get(key)

            with patch("src.services.twilio_integration.Client") as mock_client_class:
                service = TwilioIntegrationService()

                assert service.account_sid == "test_sid"
                assert service.auth_token == "test_token"
                mock_client_class.assert_called_once_with("test_sid", "test_token")

    def test_initialization_without_credentials(self):
        """Test service initialization without credentials."""
        with patch("src.services.twilio_integration.get_config", return_value=None):
            service = TwilioIntegrationService()

            assert service.account_sid is None
            assert service.auth_token is None
            assert service.client is None

    def test_configure_phone_number_success(self, service, mock_twilio_client):
        """Test successful phone number configuration."""
        service.client = mock_twilio_client

        # Mock phone number lookup
        mock_phone_number = MagicMock()
        mock_phone_number.sid = "test_phone_sid"
        mock_twilio_client.incoming_phone_numbers.list.return_value = [
            mock_phone_number
        ]

        # Mock update method
        mock_twilio_client.incoming_phone_numbers.return_value.update.return_value = (
            None
        )

        result = service.configure_phone_number(
            phone_number="+1234567890", webhook_url="https://example.com/webhook"
        )

        assert result is True
        assert service.phone_number == "+1234567890"

        # Verify API calls
        mock_twilio_client.incoming_phone_numbers.list.assert_called_once_with(
            phone_number="+1234567890"
        )

    def test_configure_phone_number_not_found(self, service, mock_twilio_client):
        """Test phone number configuration when number not found."""
        service.client = mock_twilio_client
        mock_twilio_client.incoming_phone_numbers.list.return_value = []

        result = service.configure_phone_number(
            phone_number="+9999999999", webhook_url="https://example.com/webhook"
        )

        assert result is False

    def test_configure_phone_number_no_client(self, service):
        """Test phone number configuration without client."""
        service.client = None

        result = service.configure_phone_number(
            phone_number="+1234567890", webhook_url="https://example.com/webhook"
        )

        assert result is False

    def test_hash_phone_number(self, service):
        """Test phone number hashing for privacy."""
        phone_number = "+1234567890"

        hash1 = service._hash_phone_number(phone_number)
        hash2 = service._hash_phone_number(phone_number)

        # Hash should be consistent
        assert hash1 == hash2
        assert len(hash1) == 16  # First 16 chars of SHA256
        assert phone_number not in hash1  # Original number not in hash

        # Different numbers should produce different hashes
        different_hash = service._hash_phone_number("+0987654321")
        assert hash1 != different_hash

    def test_handle_incoming_call_success(self, service):
        """Test successful incoming call handling."""
        call_sid = "test_call_123"
        from_number = "+1234567890"

        response = service.handle_incoming_call(call_sid, from_number)

        assert isinstance(response, VoiceResponse)

        # Convert to string to check content
        response_str = str(response)
        assert "Hello! Please state your appointment request" in response_str
        assert "Connect" in response_str
        assert "Stream" in response_str

    def test_handle_incoming_call_with_error(self, service):
        """Test incoming call handling with error."""
        # Force an error by passing None as call_sid
        with patch(
            "src.services.twilio_integration.audit_logger_instance"
        ) as mock_audit:
            response = service.handle_incoming_call(None, "+1234567890")

            assert isinstance(response, VoiceResponse)
            response_str = str(response)
            assert "technical difficulties" in response_str
            assert "Hangup" in response_str

    def test_create_conference_call(self, service):
        """Test conference call creation."""
        call_sid = "test_call_123"

        result = service.create_conference_call(call_sid)

        assert "conference_name" in result
        assert result["conference_name"] == f"voice_processing_{call_sid}"
        assert "twiml" in result
        assert "Conference" in result["twiml"]
        assert "Connecting you to our voice assistant" in result["twiml"]

    def test_create_conference_call_error(self, service):
        """Test conference call creation with error."""
        with patch(
            "src.services.twilio_integration.VoiceResponse",
            side_effect=Exception("TwiML Error"),
        ):
            result = service.create_conference_call("test_call")

            assert result == {}

    def test_end_call_success(self, service, mock_twilio_client):
        """Test successful call termination."""
        service.client = mock_twilio_client

        # Mock call update
        mock_call = MagicMock()
        mock_twilio_client.calls.return_value.update.return_value = mock_call

        result = service.end_call("test_call_123", "completed")

        assert result is True
        mock_twilio_client.calls.assert_called_once_with("test_call_123")

    def test_end_call_no_client(self, service):
        """Test call termination without client."""
        service.client = None

        result = service.end_call("test_call_123")

        assert result is False

    def test_end_call_api_error(self, service, mock_twilio_client):
        """Test call termination with API error."""
        service.client = mock_twilio_client
        mock_twilio_client.calls.return_value.update.side_effect = Exception(
            "API Error"
        )

        result = service.end_call("test_call_123")

        assert result is False

    def test_get_call_details_success(self, service, mock_twilio_client):
        """Test successful call details retrieval."""
        service.client = mock_twilio_client

        # Mock call details
        mock_call = MagicMock()
        mock_call.sid = "test_call_123"
        mock_call.status = "completed"
        mock_call.duration = 120
        mock_call.start_time = "2023-01-01T12:00:00Z"
        mock_call.end_time = "2023-01-01T12:02:00Z"
        mock_call.direction = "inbound"
        mock_call.from_ = "+1234567890"
        mock_call.to = "+0987654321"

        mock_twilio_client.calls.return_value.fetch.return_value = mock_call

        result = service.get_call_details("test_call_123")

        assert result is not None
        assert result["sid"] == "test_call_123"
        assert result["status"] == "completed"
        assert result["duration"] == 120
        assert result["direction"] == "inbound"
        assert "from_number_hash" in result
        assert "to_number_hash" in result
        # Verify original numbers are not in the result
        assert "+1234567890" not in str(result)
        assert "+0987654321" not in str(result)

    def test_get_call_details_not_found(self, service, mock_twilio_client):
        """Test call details retrieval for non-existent call."""
        service.client = mock_twilio_client
        mock_twilio_client.calls.return_value.fetch.side_effect = Exception(
            "Call not found"
        )

        result = service.get_call_details("non_existent_call")

        assert result is None

    def test_get_call_details_no_client(self, service):
        """Test call details retrieval without client."""
        service.client = None

        result = service.get_call_details("test_call_123")

        assert result is None

    def test_test_connection_success(self, service, mock_twilio_client):
        """Test successful connection test."""
        service.client = mock_twilio_client

        # Mock account fetch
        mock_account = MagicMock()
        mock_account.sid = "test_account_sid"
        mock_twilio_client.api.accounts.return_value.fetch.return_value = mock_account

        result = service.test_connection()

        assert result is True

    def test_test_connection_failure(self, service, mock_twilio_client):
        """Test failed connection test."""
        service.client = mock_twilio_client
        mock_twilio_client.api.accounts.return_value.fetch.side_effect = Exception(
            "Auth failed"
        )

        result = service.test_connection()

        assert result is False

    def test_test_connection_no_client(self, service):
        """Test connection test without client."""
        service.client = None

        result = service.test_connection()

        assert result is False

    def test_voice_response_contains_stream_url(self, service):
        """Test that voice response contains proper stream URL."""
        call_sid = "test_call_123"
        from_number = "+1234567890"

        response = service.handle_incoming_call(call_sid, from_number)
        response_str = str(response)

        # Should contain stream URL with call_sid
        assert f"wss://your-domain.com/voice/stream/{call_sid}" in response_str
        assert 'track="inbound"' in response_str

    def test_conference_call_settings(self, service):
        """Test conference call TwiML settings."""
        call_sid = "test_call_123"

        result = service.create_conference_call(call_sid)

        twiml = result["twiml"]

        # Verify conference settings
        assert 'startConferenceOnEnter="True"' in twiml
        assert 'endConferenceOnExit="True"' in twiml
        assert 'record="record-from-start"' in twiml
        assert f"voice_processing_{call_sid}" in twiml

    @patch("src.services.twilio_integration.audit_logger_instance")
    def test_audit_logging_on_call_handling(self, mock_audit, service):
        """Test that audit logging occurs for call handling."""
        call_sid = "test_call_123"
        from_number = "+1234567890"

        service.handle_incoming_call(call_sid, from_number)

        # Verify audit logging was called
        mock_audit.log_voice_call.assert_called()

        # Get the call arguments
        call_args = mock_audit.log_voice_call.call_args
        assert call_args[1]["action"] == "INCOMING_CALL_RECEIVED"
        assert call_args[1]["call_id"] == call_sid
        assert call_args[1]["result"] == "SUCCESS"

    @patch("src.services.twilio_integration.audit_logger_instance")
    def test_audit_logging_on_configuration(
        self, mock_audit, service, mock_twilio_client
    ):
        """Test audit logging for phone number configuration."""
        service.client = mock_twilio_client

        # Mock successful configuration
        mock_phone_number = MagicMock()
        mock_phone_number.sid = "test_phone_sid"
        mock_twilio_client.incoming_phone_numbers.list.return_value = [
            mock_phone_number
        ]

        service.configure_phone_number("+1234567890", "https://example.com/webhook")

        # Verify audit logging was called
        mock_audit.log_configuration_change.assert_called()
        call_args = mock_audit.log_configuration_change.call_args
        assert call_args[1]["action"] == "PHONE_NUMBER_CONFIGURED"
        assert call_args[1]["result"] == "SUCCESS"
