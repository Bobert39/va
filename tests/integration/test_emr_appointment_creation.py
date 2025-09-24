"""
Integration tests for EMR appointment creation workflow.

Tests the complete appointment creation flow from voice request
through EMR integration to confirmation generation.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from src.audit import SecurityAndAuditService
from src.services.appointment_creator import AppointmentCreator, AppointmentStatus
from src.services.confirmation_generator import ConfirmationGenerator
from src.services.emr import EMROAuthClient
from src.services.voice_handler import VoiceCallHandler


class TestEMRAppointmentCreationWorkflow:
    """Integration tests for appointment creation workflow."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing."""
        with patch("src.config.get_config") as mock_get, patch(
            "src.config.set_config"
        ) as mock_set:
            mock_get.return_value = {
                "oauth_config": {
                    "client_id": "test_client",
                    "client_secret": "test_secret",
                    "base_url": "https://emr.test.com",
                    "token_endpoint": "https://emr.test.com/oauth/token",
                    "appointment_endpoint": "/api/appointments",
                },
                "emr_integration": {
                    "base_url": "https://emr.test.com",
                    "appointment_api_endpoint": "/api/appointments",
                    "retry_configuration": {
                        "max_attempts": 2,
                        "initial_delay_seconds": 0.1,
                        "backoff_multiplier": 2,
                    },
                    "circuit_breaker": {
                        "failure_threshold": 3,
                        "recovery_timeout_seconds": 5,
                        "half_open_max_calls": 2,
                    },
                    "confirmation_format": "VA_{date}_{code}",
                    "practice_prefix": "VA",
                },
            }
            yield mock_get, mock_set

    @pytest.fixture
    def voice_handler(self, mock_config):
        """Create VoiceCallHandler with mocked dependencies."""
        with patch("src.services.voice_handler.openai_service"), patch(
            "src.services.voice_handler.twilio_service"
        ):
            handler = VoiceCallHandler()
            return handler

    @pytest.fixture
    def appointment_data(self):
        """Valid appointment data for testing."""
        return {
            "patient_id": "patient123",
            "provider_id": "provider456",
            "start_time": datetime.now(timezone.utc) + timedelta(days=1),
            "duration_minutes": 30,
            "appointment_type": "routine",
            "reason": "Annual checkup",
            "notes": "Voice appointment request",
        }

    @pytest.mark.asyncio
    async def test_complete_appointment_creation_success(
        self, voice_handler, appointment_data, mock_config
    ):
        """Test successful appointment creation from voice call."""
        call_sid = "call123"

        # Start call session
        session_result = await voice_handler.start_call_session(
            call_sid=call_sid, from_number="+1234567890", to_number="+0987654321"
        )
        assert session_result["success"] is True

        # Mock successful EMR API response
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "appt789"}

            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(return_value=mock_response)

            # Mock token retrieval
            with patch.object(
                voice_handler.emr_client,
                "ensure_valid_token",
                AsyncMock(return_value="test_token"),
            ):
                # Create appointment
                result = await voice_handler.create_appointment_from_voice(
                    call_sid=call_sid, appointment_data=appointment_data
                )

                assert result["success"] is True
                assert result["appointment_id"] == "appt789"
                assert "confirmation_number" in result
                assert result["confirmation_number"].startswith("VA_")
                assert "spoken_confirmation" in result
                assert result["status"] == "created"

                # Verify session updated
                session = voice_handler.active_calls[call_sid]
                assert session["appointment_data"] == appointment_data
                assert session["confirmation_number"] == result["confirmation_number"]

    @pytest.mark.asyncio
    async def test_appointment_creation_with_retry(
        self, voice_handler, appointment_data, mock_config
    ):
        """Test appointment creation with retry on failure."""
        call_sid = "call456"

        # Start session
        await voice_handler.start_call_session(
            call_sid=call_sid, from_number="+1234567890", to_number="+0987654321"
        )

        # Mock failed then successful response
        responses = [
            # First attempt fails
            MagicMock(status_code=500, text="Server error"),
            # Second attempt succeeds
            MagicMock(
                status_code=201, json=MagicMock(return_value={"id": "appt_retry"})
            ),
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(side_effect=responses)

            with patch.object(
                voice_handler.emr_client,
                "ensure_valid_token",
                AsyncMock(return_value="test_token"),
            ):
                # Small delay for retry testing
                voice_handler.appointment_creator.initial_delay = 0.01

                result = await voice_handler.create_appointment_from_voice(
                    call_sid=call_sid, appointment_data=appointment_data
                )

                # Should succeed after retry
                assert result["success"] is True
                assert result["appointment_id"] == "appt_retry"

    @pytest.mark.asyncio
    async def test_appointment_creation_validation_error(
        self, voice_handler, mock_config
    ):
        """Test appointment creation with validation error."""
        call_sid = "call789"

        # Start session
        await voice_handler.start_call_session(
            call_sid=call_sid, from_number="+1234567890", to_number="+0987654321"
        )

        # Invalid appointment data
        invalid_data = {
            "patient_id": "",  # Empty patient ID
            "provider_id": "provider456",
        }

        result = await voice_handler.create_appointment_from_voice(
            call_sid=call_sid, appointment_data=invalid_data
        )

        assert result["success"] is False
        assert result["status"] == "failed"
        assert "validation" in result["error"].lower()
        assert result["action"] == "human_handoff"

    @pytest.mark.asyncio
    async def test_appointment_creation_circuit_breaker(
        self, voice_handler, appointment_data, mock_config
    ):
        """Test circuit breaker behavior during repeated failures."""
        call_sid = "call_circuit"

        await voice_handler.start_call_session(
            call_sid=call_sid, from_number="+1234567890", to_number="+0987654321"
        )

        # Mock continuous failures
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock(status_code=500, text="Server error")
            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(return_value=mock_response)

            with patch.object(
                voice_handler.emr_client,
                "ensure_valid_token",
                AsyncMock(return_value="test_token"),
            ):
                # Set up for quick failure
                voice_handler.appointment_creator.max_retry_attempts = 2
                voice_handler.appointment_creator.initial_delay = 0.01

                # Multiple attempts to trigger circuit breaker
                for i in range(3):
                    result = await voice_handler.create_appointment_from_voice(
                        call_sid=f"call_circuit_{i}", appointment_data=appointment_data
                    )
                    assert result["success"] is False

                    # Start new session for each attempt
                    if i < 2:
                        await voice_handler.start_call_session(
                            call_sid=f"call_circuit_{i+1}",
                            from_number="+1234567890",
                            to_number="+0987654321",
                        )

    @pytest.mark.asyncio
    async def test_confirmation_number_generation_uniqueness(
        self, voice_handler, appointment_data, mock_config
    ):
        """Test uniqueness of generated confirmation numbers."""
        confirmations = set()

        # Generate multiple confirmations
        for i in range(10):
            confirmation = (
                voice_handler.confirmation_generator.generate_confirmation_number(
                    appointment_id=f"appt_{i}",
                    patient_id=f"patient_{i}",
                    provider_id="provider123",
                    appointment_time=appointment_data["start_time"],
                )
            )
            confirmations.add(confirmation)

        # All should be unique
        assert len(confirmations) == 10

    @pytest.mark.asyncio
    async def test_confirmation_validation_and_lookup(
        self, voice_handler, appointment_data, mock_config
    ):
        """Test confirmation number validation and lookup."""
        # Generate confirmation
        confirmation = (
            voice_handler.confirmation_generator.generate_confirmation_number(
                appointment_id="appt_test",
                patient_id="patient123",
                provider_id="provider456",
                appointment_time=appointment_data["start_time"],
            )
        )

        # Validate correct confirmation
        (
            is_valid,
            data,
        ) = voice_handler.confirmation_generator.validate_confirmation_number(
            confirmation
        )
        assert is_valid is True
        assert data["appointment_id"] == "appt_test"

        # Lookup by appointment ID
        retrieved = (
            voice_handler.confirmation_generator.get_confirmation_by_appointment(
                "appt_test"
            )
        )
        assert retrieved == confirmation

        # Test invalid confirmation
        is_valid, _ = voice_handler.confirmation_generator.validate_confirmation_number(
            "INVALID123"
        )
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_process_appointment_request_integration(
        self, voice_handler, mock_config
    ):
        """Test processing appointment request from transcribed text."""
        call_sid = "call_process"

        await voice_handler.start_call_session(
            call_sid=call_sid, from_number="+1234567890", to_number="+0987654321"
        )

        # Mock successful EMR response
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "appt_voice"}

            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(return_value=mock_response)

            with patch.object(
                voice_handler.emr_client,
                "ensure_valid_token",
                AsyncMock(return_value="test_token"),
            ):
                # Process appointment request
                result = await voice_handler.process_appointment_request(
                    call_sid=call_sid,
                    transcribed_text="I need to schedule an appointment with Dr. Smith next Tuesday at 2 PM",
                )

                assert result["success"] is True
                assert "appointment_id" in result
                assert "confirmation_number" in result

                # Check conversation state updated
                session = voice_handler.active_calls[call_sid]
                assert session["conversation_state"] == "appointment_confirmed"

    @pytest.mark.asyncio
    async def test_audit_logging_throughout_workflow(
        self, voice_handler, appointment_data, mock_config
    ):
        """Test comprehensive audit logging during appointment creation."""
        call_sid = "call_audit"

        # Mock audit service to track calls
        audit_calls = []
        with patch.object(
            voice_handler.audit_service,
            "log_appointment_event",
            AsyncMock(side_effect=lambda *args, **kwargs: audit_calls.append(kwargs)),
        ):
            with patch.object(
                voice_handler.audit_service,
                "log_appointment_creation",
                AsyncMock(
                    side_effect=lambda *args, **kwargs: audit_calls.append(kwargs)
                ),
            ):
                await voice_handler.start_call_session(
                    call_sid=call_sid,
                    from_number="+1234567890",
                    to_number="+0987654321",
                )

                # Mock successful EMR response
                with patch("httpx.AsyncClient") as mock_client:
                    mock_response = MagicMock()
                    mock_response.status_code = 201
                    mock_response.json.return_value = {"id": "appt_audit"}

                    mock_instance = mock_client.return_value.__aenter__.return_value
                    mock_instance.post = AsyncMock(return_value=mock_response)

                    with patch.object(
                        voice_handler.emr_client,
                        "ensure_valid_token",
                        AsyncMock(return_value="test_token"),
                    ):
                        result = await voice_handler.create_appointment_from_voice(
                            call_sid=call_sid, appointment_data=appointment_data
                        )

                        assert result["success"] is True

                        # Verify audit events were logged
                        assert len(audit_calls) > 0
                        # Check for appointment creation event
                        creation_events = [
                            e for e in audit_calls if "appointment_id" in e
                        ]
                        assert len(creation_events) > 0
