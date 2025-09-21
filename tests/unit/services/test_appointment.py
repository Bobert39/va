"""
Unit tests for FHIR Appointment Service.

This module tests the appointment service functionality including creation,
retrieval, modification, and cancellation of appointments.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from src.services.appointment import (
    Appointment,
    AppointmentConflictError,
    AppointmentCreationError,
    AppointmentNotFoundError,
    AppointmentStatus,
    AppointmentValidationError,
    FHIRAppointmentError,
    FHIRAppointmentService,
    ParticipationStatus,
)
from src.services.emr import EMROAuthClient, NetworkError, OAuthError, TokenExpiredError


class TestAppointment:
    """Test the Appointment class."""

    def test_appointment_initialization(self):
        """Test appointment initialization with valid data."""
        appointment_data = {
            "id": "123",
            "resourceType": "Appointment",
            "status": "booked",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "description": "Follow-up appointment",
            "comment": "Patient requested morning slot",
            "participant": [
                {"actor": {"reference": "Patient/456"}, "status": "accepted"},
                {"actor": {"reference": "Practitioner/789"}, "status": "accepted"},
            ],
        }

        appointment = Appointment(appointment_data)

        assert appointment.id == "123"
        assert appointment.status == "booked"
        assert appointment.start == "2024-01-15T10:00:00Z"
        assert appointment.end == "2024-01-15T10:30:00Z"
        assert appointment.description == "Follow-up appointment"
        assert appointment.comment == "Patient requested morning slot"
        assert len(appointment.participants) == 2

    def test_get_patient_reference(self):
        """Test extracting patient reference from participants."""
        appointment_data = {
            "participant": [
                {"actor": {"reference": "Patient/456"}},
                {"actor": {"reference": "Practitioner/789"}},
            ]
        }

        appointment = Appointment(appointment_data)
        assert appointment.get_patient_reference() == "Patient/456"

    def test_get_practitioner_reference(self):
        """Test extracting practitioner reference from participants."""
        appointment_data = {
            "participant": [
                {"actor": {"reference": "Patient/456"}},
                {"actor": {"reference": "Practitioner/789"}},
            ]
        }

        appointment = Appointment(appointment_data)
        assert appointment.get_practitioner_reference() == "Practitioner/789"

    def test_to_dict(self):
        """Test converting appointment to dictionary."""
        appointment_data = {
            "id": "123",
            "status": "booked",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "description": "Follow-up",
            "participant": [
                {"actor": {"reference": "Patient/456"}},
                {"actor": {"reference": "Practitioner/789"}},
            ],
        }

        appointment = Appointment(appointment_data)
        result = appointment.to_dict()

        assert result["id"] == "123"
        assert result["status"] == "booked"
        assert result["start"] == "2024-01-15T10:00:00Z"
        assert result["end"] == "2024-01-15T10:30:00Z"
        assert result["description"] == "Follow-up"
        assert result["patient_reference"] == "Patient/456"
        assert result["practitioner_reference"] == "Practitioner/789"
        assert result["participants"] == 2


class TestFHIRAppointmentService:
    """Test the FHIRAppointmentService class."""

    @pytest.fixture
    def mock_oauth_client(self):
        """Create a mock OAuth client."""
        client = Mock(spec=EMROAuthClient)
        client._get_oauth_config.return_value = {
            "fhir_base_url": "https://test-emr.com/fhir"
        }
        client.get_valid_access_token = AsyncMock(return_value="test-token")
        return client

    @pytest.fixture
    def appointment_service(self, mock_oauth_client):
        """Create appointment service with mock OAuth client."""
        return FHIRAppointmentService(mock_oauth_client)

    def test_initialization(self, mock_oauth_client):
        """Test service initialization."""
        service = FHIRAppointmentService(mock_oauth_client)
        assert service.oauth_client == mock_oauth_client
        assert service.base_url == "https://test-emr.com/fhir"

    def test_validate_appointment_data_valid(self, appointment_service):
        """Test validation with valid appointment data."""
        appointment_data = {
            "resourceType": "Appointment",
            "status": "booked",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "participant": [{"actor": {"reference": "Patient/123"}}],
        }

        # Should not raise any exception
        appointment_service._validate_appointment_data(appointment_data)

    def test_validate_appointment_data_missing_required_field(
        self, appointment_service
    ):
        """Test validation with missing required field."""
        appointment_data = {
            "resourceType": "Appointment",
            "status": "booked",
            # Missing start, end, participant
        }

        with pytest.raises(AppointmentValidationError, match="Missing required field"):
            appointment_service._validate_appointment_data(appointment_data)

    def test_validate_appointment_data_invalid_resource_type(self, appointment_service):
        """Test validation with invalid resource type."""
        appointment_data = {
            "resourceType": "Patient",  # Wrong type
            "status": "booked",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "participant": [{"actor": {"reference": "Patient/123"}}],
        }

        with pytest.raises(
            AppointmentValidationError, match="resourceType must be 'Appointment'"
        ):
            appointment_service._validate_appointment_data(appointment_data)

    def test_validate_appointment_data_invalid_status(self, appointment_service):
        """Test validation with invalid status."""
        appointment_data = {
            "resourceType": "Appointment",
            "status": "invalid-status",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "participant": [{"actor": {"reference": "Patient/123"}}],
        }

        with pytest.raises(AppointmentValidationError, match="Invalid status"):
            appointment_service._validate_appointment_data(appointment_data)

    def test_validate_appointment_data_invalid_datetime(self, appointment_service):
        """Test validation with invalid datetime format."""
        appointment_data = {
            "resourceType": "Appointment",
            "status": "booked",
            "start": "invalid-datetime",
            "end": "2024-01-15T10:30:00Z",
            "participant": [{"actor": {"reference": "Patient/123"}}],
        }

        with pytest.raises(AppointmentValidationError, match="Invalid datetime format"):
            appointment_service._validate_appointment_data(appointment_data)

    def test_validate_appointment_data_end_before_start(self, appointment_service):
        """Test validation with end time before start time."""
        appointment_data = {
            "resourceType": "Appointment",
            "status": "booked",
            "start": "2024-01-15T10:30:00Z",
            "end": "2024-01-15T10:00:00Z",  # End before start
            "participant": [{"actor": {"reference": "Patient/123"}}],
        }

        with pytest.raises(
            AppointmentValidationError, match="End time must be after start time"
        ):
            appointment_service._validate_appointment_data(appointment_data)

    def test_validate_appointment_data_no_participants(self, appointment_service):
        """Test validation with no participants."""
        appointment_data = {
            "resourceType": "Appointment",
            "status": "booked",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "participant": [],  # Empty participants
        }

        with pytest.raises(
            AppointmentValidationError, match="At least one participant is required"
        ):
            appointment_service._validate_appointment_data(appointment_data)

    def test_create_appointment_resource(self, appointment_service):
        """Test creating appointment resource structure."""
        result = appointment_service.create_appointment_resource(
            patient_reference="Patient/123",
            practitioner_reference="Practitioner/456",
            start_time="2024-01-15T10:00:00Z",
            end_time="2024-01-15T10:30:00Z",
            appointment_type="Follow-up",
            service_type="General Practice",
            description="Routine check-up",
            comment="Patient prefers morning appointments",
        )

        assert result["resourceType"] == "Appointment"
        assert result["status"] == "booked"
        assert result["start"] == "2024-01-15T10:00:00Z"
        assert result["end"] == "2024-01-15T10:30:00Z"
        assert result["description"] == "Routine check-up"
        assert result["comment"] == "Patient prefers morning appointments"
        assert len(result["participant"]) == 2
        assert result["participant"][0]["actor"]["reference"] == "Patient/123"
        assert result["participant"][1]["actor"]["reference"] == "Practitioner/456"
        assert "appointmentType" in result
        assert "serviceType" in result

    @pytest.mark.asyncio
    async def test_create_appointment_success(
        self, appointment_service, mock_oauth_client
    ):
        """Test successful appointment creation."""
        # Mock API response
        api_response = {
            "id": "new-appointment-123",
            "resourceType": "Appointment",
            "status": "booked",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "participant": [
                {"actor": {"reference": "Patient/123"}},
                {"actor": {"reference": "Practitioner/456"}},
            ],
        }

        with patch.object(
            appointment_service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = api_response

            result = await appointment_service.create_appointment(
                patient_reference="Patient/123",
                practitioner_reference="Practitioner/456",
                start_time="2024-01-15T10:00:00Z",
                end_time="2024-01-15T10:30:00Z",
            )

            assert isinstance(result, Appointment)
            assert result.id == "new-appointment-123"
            assert result.status == "booked"
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_appointment_validation_error(self, appointment_service):
        """Test appointment creation with validation error."""
        with pytest.raises(AppointmentValidationError):
            await appointment_service.create_appointment(
                patient_reference="Patient/123",
                practitioner_reference="Practitioner/456",
                start_time="2024-01-15T10:30:00Z",
                end_time="2024-01-15T10:00:00Z",  # End before start
            )

    @pytest.mark.asyncio
    async def test_create_appointment_conflict_error(self, appointment_service):
        """Test appointment creation with conflict error."""
        with patch.object(
            appointment_service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = AppointmentConflictError(
                "Time slot already booked"
            )

            with pytest.raises(AppointmentConflictError):
                await appointment_service.create_appointment(
                    patient_reference="Patient/123",
                    practitioner_reference="Practitioner/456",
                    start_time="2024-01-15T10:00:00Z",
                    end_time="2024-01-15T10:30:00Z",
                )

    @pytest.mark.asyncio
    async def test_get_appointment_by_id_success(self, appointment_service):
        """Test successful appointment retrieval by ID."""
        api_response = {
            "id": "appointment-123",
            "resourceType": "Appointment",
            "status": "booked",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "participant": [{"actor": {"reference": "Patient/123"}}],
        }

        with patch.object(
            appointment_service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = api_response

            result = await appointment_service.get_appointment_by_id("appointment-123")

            assert isinstance(result, Appointment)
            assert result.id == "appointment-123"
            assert result.status == "booked"
            mock_request.assert_called_once_with("GET", "Appointment/appointment-123")

    @pytest.mark.asyncio
    async def test_get_appointment_by_id_not_found(self, appointment_service):
        """Test appointment retrieval when appointment not found."""
        with patch.object(
            appointment_service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = AppointmentNotFoundError("Appointment not found")

            with pytest.raises(AppointmentNotFoundError):
                await appointment_service.get_appointment_by_id("nonexistent-id")

    @pytest.mark.asyncio
    async def test_update_appointment_success(self, appointment_service):
        """Test successful appointment update."""
        appointment_data = {
            "id": "appointment-123",
            "resourceType": "Appointment",
            "status": "fulfilled",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "participant": [{"actor": {"reference": "Patient/123"}}],
        }

        api_response = appointment_data.copy()

        with patch.object(
            appointment_service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = api_response

            result = await appointment_service.update_appointment(
                "appointment-123", appointment_data
            )

            assert isinstance(result, Appointment)
            assert result.id == "appointment-123"
            assert result.status == "fulfilled"
            mock_request.assert_called_once_with(
                "PUT", "Appointment/appointment-123", appointment_data
            )

    @pytest.mark.asyncio
    async def test_cancel_appointment_success(self, appointment_service):
        """Test successful appointment cancellation."""
        # Mock the get_appointment_by_id call
        original_appointment = {
            "id": "appointment-123",
            "resourceType": "Appointment",
            "status": "booked",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "participant": [{"actor": {"reference": "Patient/123"}}],
        }

        cancelled_appointment = original_appointment.copy()
        cancelled_appointment["status"] = "cancelled"
        cancelled_appointment["comment"] = "Patient requested cancellation"

        with patch.object(
            appointment_service, "get_appointment_by_id", new_callable=AsyncMock
        ) as mock_get:
            with patch.object(
                appointment_service, "update_appointment", new_callable=AsyncMock
            ) as mock_update:
                mock_get.return_value = Appointment(original_appointment)
                mock_update.return_value = Appointment(cancelled_appointment)

                result = await appointment_service.cancel_appointment(
                    "appointment-123", reason="Patient requested cancellation"
                )

                assert result.status == "cancelled"
                mock_get.assert_called_once_with("appointment-123")
                mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_appointments_success(self, appointment_service):
        """Test successful appointment search."""
        api_response = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "id": "appointment-1",
                        "resourceType": "Appointment",
                        "status": "booked",
                        "start": "2024-01-15T10:00:00Z",
                        "end": "2024-01-15T10:30:00Z",
                        "participant": [{"actor": {"reference": "Patient/123"}}],
                    }
                },
                {
                    "resource": {
                        "id": "appointment-2",
                        "resourceType": "Appointment",
                        "status": "booked",
                        "start": "2024-01-15T11:00:00Z",
                        "end": "2024-01-15T11:30:00Z",
                        "participant": [{"actor": {"reference": "Patient/123"}}],
                    }
                },
            ],
        }

        with patch.object(
            appointment_service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = api_response

            results = await appointment_service.search_appointments(
                patient_reference="Patient/123", status="booked"
            )

            assert len(results) == 2
            assert all(isinstance(apt, Appointment) for apt in results)
            assert results[0].id == "appointment-1"
            assert results[1].id == "appointment-2"

    @pytest.mark.asyncio
    async def test_make_fhir_request_authentication_error(
        self, appointment_service, mock_oauth_client
    ):
        """Test FHIR request with authentication error."""
        mock_oauth_client.get_valid_access_token.side_effect = OAuthError(
            "token_expired", "Token expired"
        )

        with pytest.raises(FHIRAppointmentError, match="Authentication failed"):
            await appointment_service._make_fhir_request("GET", "Appointment/123")

    @pytest.mark.asyncio
    async def test_make_fhir_request_network_error(self, appointment_service):
        """Test FHIR request with network error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = (
                httpx.ConnectError("Connection failed")
            )

            with pytest.raises(NetworkError):
                await appointment_service._make_fhir_request("GET", "Appointment/123")

    @pytest.mark.asyncio
    async def test_make_fhir_request_http_status_errors(self, appointment_service):
        """Test FHIR request with various HTTP status errors."""
        # Mock the httpx client directly in the appointment service method
        with patch.object(
            appointment_service, "_retry_delays", []
        ):  # No retries to simplify test
            # Test 404 - Not Found
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 404
                mock_client.return_value.__aenter__.return_value.get.return_value = (
                    mock_response
                )

                with pytest.raises(AppointmentNotFoundError):
                    await appointment_service._make_fhir_request(
                        "GET", "Appointment/123"
                    )

            # Test 409 - Conflict
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 409
                mock_client.return_value.__aenter__.return_value.post.return_value = (
                    mock_response
                )

                with pytest.raises(AppointmentConflictError):
                    await appointment_service._make_fhir_request(
                        "POST", "Appointment", {}
                    )

            # Test 400 - Bad Request
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 400
                mock_response.text = "Invalid request"
                mock_client.return_value.__aenter__.return_value.post.return_value = (
                    mock_response
                )

                with pytest.raises(AppointmentValidationError):
                    await appointment_service._make_fhir_request(
                        "POST", "Appointment", {}
                    )

    def test_anonymize_for_logging(self, appointment_service):
        """Test PHI anonymization for logging."""
        result = appointment_service._anonymize_for_logging("sensitive-data")
        assert result.startswith("[REDACTED-")
        assert result.endswith("]")
        assert "sensitive-data" not in result

        # Test empty string
        result = appointment_service._anonymize_for_logging("")
        assert result == "[empty]"

    def test_log_phi_safe(self, appointment_service):
        """Test PHI-safe logging."""
        with patch.object(
            appointment_service, "_anonymize_for_logging"
        ) as mock_anonymize:
            mock_anonymize.return_value = "[REDACTED-12345678]"

            # Should anonymize PHI fields
            appointment_service._log_phi_safe(
                "info", "Test message", patient_id="123", other_field="safe"
            )

            # PHI field should be anonymized
            mock_anonymize.assert_called_with("123")


class TestAppointmentEnums:
    """Test appointment-related enums."""

    def test_appointment_status_enum(self):
        """Test AppointmentStatus enum values."""
        assert AppointmentStatus.PROPOSED.value == "proposed"
        assert AppointmentStatus.PENDING.value == "pending"
        assert AppointmentStatus.BOOKED.value == "booked"
        assert AppointmentStatus.ARRIVED.value == "arrived"
        assert AppointmentStatus.FULFILLED.value == "fulfilled"
        assert AppointmentStatus.CANCELLED.value == "cancelled"
        assert AppointmentStatus.NOSHOW.value == "noshow"
        assert AppointmentStatus.ENTERED_IN_ERROR.value == "entered-in-error"
        assert AppointmentStatus.CHECKED_IN.value == "checked-in"
        assert AppointmentStatus.WAITLIST.value == "waitlist"

    def test_participation_status_enum(self):
        """Test ParticipationStatus enum values."""
        assert ParticipationStatus.ACCEPTED.value == "accepted"
        assert ParticipationStatus.DECLINED.value == "declined"
        assert ParticipationStatus.TENTATIVE.value == "tentative"
        assert ParticipationStatus.NEEDS_ACTION.value == "needs-action"


class TestAppointmentExceptions:
    """Test appointment-related exceptions."""

    def test_fhir_appointment_error(self):
        """Test FHIRAppointmentError exception."""
        error = FHIRAppointmentError("Test error")
        assert str(error) == "Test error"

    def test_appointment_validation_error(self):
        """Test AppointmentValidationError exception."""
        error = AppointmentValidationError("Validation failed")
        assert str(error) == "Validation failed"
        assert isinstance(error, FHIRAppointmentError)

    def test_appointment_conflict_error(self):
        """Test AppointmentConflictError exception."""
        error = AppointmentConflictError("Conflict detected")
        assert str(error) == "Conflict detected"
        assert isinstance(error, FHIRAppointmentError)

    def test_appointment_not_found_error(self):
        """Test AppointmentNotFoundError exception."""
        error = AppointmentNotFoundError("Not found")
        assert str(error) == "Not found"
        assert isinstance(error, FHIRAppointmentError)

    def test_appointment_creation_error(self):
        """Test AppointmentCreationError exception."""
        error = AppointmentCreationError("Creation failed")
        assert str(error) == "Creation failed"
        assert isinstance(error, FHIRAppointmentError)
