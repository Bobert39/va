"""
Unit tests for AppointmentCreator service.

Tests appointment creation logic, retry mechanisms, circuit breaker,
and EMR integration for voice-scheduled appointments.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.services.appointment_creator import (
    AppointmentCreationError,
    AppointmentCreator,
    AppointmentStatus,
    CircuitBreakerOpen,
    CircuitBreakerState,
    EMRConnectionError,
    ValidationError,
)


class TestAppointmentCreator:
    """Test suite for AppointmentCreator."""

    @pytest.fixture
    def mock_emr_client(self):
        """Create mock EMR client."""
        client = MagicMock()
        client.ensure_valid_token = AsyncMock(return_value="test_token")
        client.create_appointment = AsyncMock(return_value={"id": "appt123"})
        return client

    @pytest.fixture
    def mock_audit_service(self):
        """Create mock audit service."""
        service = MagicMock()
        service.log_appointment_event = AsyncMock()
        service.log_appointment_creation = AsyncMock()
        service.log_appointment_retry = AsyncMock()
        service.log_appointment_failure = AsyncMock()
        return service

    @pytest.fixture
    def appointment_creator(self, mock_emr_client, mock_audit_service):
        """Create AppointmentCreator instance with mocks."""
        return AppointmentCreator(
            emr_client=mock_emr_client, audit_service=mock_audit_service
        )

    @pytest.fixture
    def valid_appointment_data(self):
        """Valid appointment data for testing."""
        return {
            "patient_id": "patient123",
            "provider_id": "provider456",
            "start_time": datetime.now(timezone.utc) + timedelta(days=1),
            "duration_minutes": 30,
            "appointment_type": "routine",
            "reason": "Annual checkup",
            "notes": "Patient requested morning appointment",
        }

    @pytest.mark.asyncio
    async def test_validate_appointment_data_success(
        self, appointment_creator, valid_appointment_data
    ):
        """Test successful appointment data validation."""
        result = appointment_creator.validate_appointment_data(valid_appointment_data)

        assert result["patient_id"] == "patient123"
        assert result["provider_id"] == "provider456"
        assert result["duration_minutes"] == 30
        assert "end_time" in result
        assert result["end_time"] == result["start_time"] + timedelta(minutes=30)

    @pytest.mark.asyncio
    async def test_validate_appointment_data_missing_fields(self, appointment_creator):
        """Test validation with missing required fields."""
        invalid_data = {
            "patient_id": "patient123",
            # Missing provider_id, start_time, etc.
        }

        with pytest.raises(ValidationError) as exc_info:
            appointment_creator.validate_appointment_data(invalid_data)

        assert "Missing required fields" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_appointment_data_invalid_duration(
        self, appointment_creator, valid_appointment_data
    ):
        """Test validation with invalid duration."""
        valid_appointment_data["duration_minutes"] = -15

        with pytest.raises(ValidationError) as exc_info:
            appointment_creator.validate_appointment_data(valid_appointment_data)

        assert "Invalid duration" in str(exc_info.value)

    def test_map_to_emr_format(self, appointment_creator, valid_appointment_data):
        """Test mapping appointment data to EMR format."""
        validated = appointment_creator.validate_appointment_data(
            valid_appointment_data
        )
        emr_format = appointment_creator.map_to_emr_format(validated)

        assert emr_format["pc_pid"] == "patient123"
        assert emr_format["pc_aid"] == "provider456"
        assert emr_format["pc_duration"] == 1800  # 30 minutes in seconds
        assert "pc_eventDate" in emr_format
        assert "pc_startTime" in emr_format
        assert "pc_endTime" in emr_format

    def test_map_appointment_type(self, appointment_creator):
        """Test appointment type mapping."""
        assert appointment_creator._map_appointment_type("new_patient") == "5"
        assert appointment_creator._map_appointment_type("follow_up") == "9"
        assert appointment_creator._map_appointment_type("urgent") == "11"
        assert appointment_creator._map_appointment_type("unknown") == "9"  # Default

    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_state(self, appointment_creator):
        """Test circuit breaker in closed state."""
        appointment_creator.circuit_state = CircuitBreakerState.CLOSED
        result = await appointment_creator.check_circuit_breaker()
        assert result is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_to_half_open_transition(
        self, appointment_creator
    ):
        """Test circuit breaker transition from open to half-open."""
        appointment_creator.circuit_state = CircuitBreakerState.OPEN
        appointment_creator.last_failure_time = datetime.utcnow() - timedelta(
            seconds=61
        )
        appointment_creator.recovery_timeout = 60

        result = await appointment_creator.check_circuit_breaker()
        assert result is True
        assert appointment_creator.circuit_state == CircuitBreakerState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_limit(self, appointment_creator):
        """Test circuit breaker half-open call limit."""
        appointment_creator.circuit_state = CircuitBreakerState.HALF_OPEN
        appointment_creator.half_open_calls = 0
        appointment_creator.half_open_max_calls = 3

        # First 3 calls should be allowed
        for i in range(3):
            result = await appointment_creator.check_circuit_breaker()
            assert result is True
            assert appointment_creator.half_open_calls == i + 1

        # Fourth call should be blocked
        result = await appointment_creator.check_circuit_breaker()
        assert result is False

    def test_record_success_closes_circuit(self, appointment_creator):
        """Test successful call closes circuit breaker."""
        appointment_creator.circuit_state = CircuitBreakerState.HALF_OPEN
        appointment_creator.failure_count = 3

        appointment_creator.record_success()

        assert appointment_creator.circuit_state == CircuitBreakerState.CLOSED
        assert appointment_creator.failure_count == 0
        assert appointment_creator.last_failure_time is None

    def test_record_failure_opens_circuit(self, appointment_creator):
        """Test failures open circuit breaker."""
        appointment_creator.circuit_state = CircuitBreakerState.CLOSED
        appointment_creator.failure_count = 4
        appointment_creator.failure_threshold = 5

        appointment_creator.record_failure()

        assert appointment_creator.failure_count == 5
        assert appointment_creator.circuit_state == CircuitBreakerState.OPEN
        assert appointment_creator.last_failure_time is not None

    @pytest.mark.asyncio
    async def test_create_appointment_with_retry_success(
        self, appointment_creator, valid_appointment_data, mock_audit_service
    ):
        """Test successful appointment creation with retry logic."""
        with patch.object(
            appointment_creator,
            "_create_appointment_api_call",
            AsyncMock(return_value={"id": "appt123"}),
        ):
            result = await appointment_creator.create_appointment_with_retry(
                appointment_data=valid_appointment_data, session_id="session123"
            )

            assert result["status"] == AppointmentStatus.CREATED.value
            assert result["emr_appointment_id"] == "appt123"
            assert result["retry_count"] == 0
            mock_audit_service.log_appointment_event.assert_called()

    @pytest.mark.asyncio
    async def test_create_appointment_with_retry_validation_error(
        self, appointment_creator, mock_audit_service
    ):
        """Test appointment creation with validation error."""
        invalid_data = {"patient_id": ""}  # Invalid data

        result = await appointment_creator.create_appointment_with_retry(
            appointment_data=invalid_data, session_id="session123"
        )

        assert result["status"] == AppointmentStatus.VALIDATION_ERROR.value
        assert "error" in result
        mock_audit_service.log_appointment_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_appointment_with_retry_all_attempts_fail(
        self, appointment_creator, valid_appointment_data, mock_audit_service
    ):
        """Test appointment creation when all retry attempts fail."""
        appointment_creator.max_retry_attempts = 2
        appointment_creator.initial_delay = 0.01  # Minimal delay for testing

        with patch.object(
            appointment_creator,
            "_create_appointment_api_call",
            AsyncMock(side_effect=EMRConnectionError("Connection failed")),
        ):
            result = await appointment_creator.create_appointment_with_retry(
                appointment_data=valid_appointment_data, session_id="session123"
            )

            assert result["status"] == AppointmentStatus.FAILED.value
            assert "Connection failed" in result["error"]
            assert result["retry_count"] == 2
            # Multiple calls for attempts and final failure
            assert mock_audit_service.log_appointment_event.call_count >= 3

    @pytest.mark.asyncio
    async def test_create_appointment_with_circuit_breaker_open(
        self, appointment_creator, valid_appointment_data
    ):
        """Test appointment creation when circuit breaker is open."""
        appointment_creator.circuit_state = CircuitBreakerState.OPEN
        appointment_creator.last_failure_time = datetime.utcnow()
        appointment_creator.recovery_timeout = 300  # 5 minutes
        appointment_creator.max_retry_attempts = 1

        with pytest.raises(CircuitBreakerOpen):
            await appointment_creator.create_appointment_with_retry(
                appointment_data=valid_appointment_data, session_id="session123"
            )

    @pytest.mark.asyncio
    async def test_create_appointment_api_call_success(
        self, appointment_creator, mock_emr_client
    ):
        """Test successful API call to create appointment."""
        emr_data = {
            "pc_pid": "patient123",
            "pc_aid": "provider456",
            "pc_eventDate": "2025-01-20",
            "pc_startTime": "10:00:00",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": "appt789"}

            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(return_value=mock_response)

            with patch("src.services.appointment_creator.get_config") as mock_config:
                mock_config.return_value = {
                    "base_url": "https://emr.example.com",
                    "appointment_api_endpoint": "/api/appointments",
                }

                result = await appointment_creator._create_appointment_api_call(
                    emr_data=emr_data, session_id="session123"
                )

                assert result["id"] == "appt789"
                mock_emr_client.ensure_valid_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_appointment_api_call_auth_failure(
        self, appointment_creator, mock_emr_client
    ):
        """Test API call with authentication failure."""
        emr_data = {"pc_pid": "patient123"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.content = b'{"error": "Unauthorized"}'

            mock_instance = mock_client.return_value.__aenter__.return_value
            mock_instance.post = AsyncMock(return_value=mock_response)

            with patch("src.services.appointment_creator.get_config") as mock_config:
                mock_config.return_value = {
                    "base_url": "https://emr.example.com",
                    "appointment_api_endpoint": "/api/appointments",
                }

                with pytest.raises(EMRConnectionError) as exc_info:
                    await appointment_creator._create_appointment_api_call(
                        emr_data=emr_data, session_id="session123"
                    )

                assert "Authentication failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_fallback_data(self, appointment_creator, valid_appointment_data):
        """Test fallback data generation when EMR unavailable."""
        fallback = await appointment_creator.get_fallback_data(valid_appointment_data)

        assert fallback["status"] == AppointmentStatus.PENDING_RETRY.value
        assert fallback["fallback"] is True
        assert "retry_after" in fallback
        assert fallback["appointment_data"] == valid_appointment_data
