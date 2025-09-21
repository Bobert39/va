"""
Unit tests for appointment API endpoints.

These tests validate the appointment web interface API endpoints
with mocked FHIR appointment service responses.
"""

from datetime import date, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

# Mock the main app initialization to avoid OAuth client issues
with patch("src.main.oauth_client"), patch("src.main.fhir_patient_service"), patch(
    "src.main.provider_schedule_service"
), patch("src.main.appointment_service"):
    from src.main import app

from src.services.appointment import (
    Appointment,
    FHIRAppointmentError,
    FHIRAppointmentService,
)
from src.services.provider_schedule import (
    Provider,
    ProviderScheduleError,
    ProviderScheduleService,
)


@pytest.fixture
def test_client():
    """Test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_appointment_service():
    """Mock appointment service."""
    service = Mock(spec=FHIRAppointmentService)
    service.get_appointments_today = AsyncMock()
    service.get_appointments_by_date_range = AsyncMock()
    service.search_appointments = AsyncMock()
    return service


@pytest.fixture
def mock_provider_schedule_service():
    """Mock provider schedule service."""
    service = Mock(spec=ProviderScheduleService)
    service.get_providers = AsyncMock()
    return service


@pytest.fixture
def sample_appointment_data():
    """Sample appointment data for testing."""
    return {
        "id": "appointment-123",
        "status": "booked",
        "start": "2025-09-21T09:00:00Z",
        "end": "2025-09-21T10:00:00Z",
        "description": "Regular checkup",
        "comment": "Patient needs follow-up",
        "participant": [
            {"actor": {"reference": "Patient/456", "display": "John Doe"}},
            {"actor": {"reference": "Practitioner/789", "display": "Dr. Smith"}},
        ],
        "appointmentType": {"coding": [{"display": "Regular Checkup"}]},
    }


@pytest.fixture
def sample_appointment(sample_appointment_data):
    """Sample appointment object."""
    return Appointment(sample_appointment_data)


@pytest.fixture
def sample_provider_data():
    """Sample provider data for testing."""
    return {
        "id": "provider-789",
        "active": True,
        "name": [{"given": ["John"], "family": "Smith"}],
        "qualification": [{"code": {"coding": [{"display": "MD"}]}}],
    }


@pytest.fixture
def sample_provider(sample_provider_data):
    """Sample provider object."""
    return Provider(sample_provider_data)


class TestAppointmentTodayEndpoint:
    """Test GET /api/v1/appointments/today endpoint."""

    @patch("src.main.appointment_service")
    def test_get_appointments_today_success(
        self, mock_service, test_client, sample_appointment
    ):
        """Test successful retrieval of today's appointments."""
        # Setup mock
        mock_service.get_appointments_today.return_value = [sample_appointment]

        # Make request
        response = test_client.get("/api/v1/appointments/today")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 1
        assert len(data["appointments"]) == 1

        appointment = data["appointments"][0]
        assert appointment["id"] == "appointment-123"
        assert appointment["status"] == "booked"
        assert appointment["patient_name"] == "John Doe"
        assert appointment["provider_name"] == "Dr. Smith"

        # Verify service called
        mock_service.get_appointments_today.assert_called_once()

    @patch("src.main.appointment_service")
    def test_get_appointments_today_empty(self, mock_service, test_client):
        """Test retrieval when no appointments exist."""
        # Setup mock
        mock_service.get_appointments_today.return_value = []

        # Make request
        response = test_client.get("/api/v1/appointments/today")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 0
        assert len(data["appointments"]) == 0

    @patch("src.main.appointment_service")
    def test_get_appointments_today_service_error(self, mock_service, test_client):
        """Test handling of appointment service errors."""
        # Setup mock
        mock_service.get_appointments_today.side_effect = FHIRAppointmentError(
            "FHIR service unavailable"
        )

        # Make request
        response = test_client.get("/api/v1/appointments/today")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "appointment_error"
        assert "FHIR service unavailable" in data["message"]


class TestAppointmentsEndpoint:
    """Test GET /api/v1/appointments endpoint."""

    @patch("src.main.appointment_service")
    def test_get_appointments_with_date_range(
        self, mock_service, test_client, sample_appointment
    ):
        """Test appointment retrieval with date range filters."""
        # Setup mock
        mock_service.get_appointments_by_date_range.return_value = [sample_appointment]

        # Make request
        response = test_client.get(
            "/api/v1/appointments",
            params={
                "start_date": "2025-09-21",
                "end_date": "2025-09-21",
                "provider": "Practitioner/789",
            },
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 1

        # Verify service called with correct parameters
        mock_service.get_appointments_by_date_range.assert_called_once_with(
            start_date="2025-09-21",
            end_date="2025-09-21",
            practitioner_reference="Practitioner/789",
            status=None,
        )

    @patch("src.main.appointment_service")
    def test_get_appointments_with_status_filter(
        self, mock_service, test_client, sample_appointment
    ):
        """Test appointment retrieval with status filter."""
        # Setup mock
        mock_service.search_appointments.return_value = [sample_appointment]

        # Make request
        response = test_client.get(
            "/api/v1/appointments",
            params={"status": "booked", "provider": "Practitioner/789"},
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Verify service called with search_appointments (no date range)
        mock_service.search_appointments.assert_called_once_with(
            practitioner_reference="Practitioner/789", status="booked"
        )

    def test_get_appointments_invalid_date_format(self, test_client):
        """Test validation of date format."""
        # Make request with invalid date
        response = test_client.get(
            "/api/v1/appointments", params={"start_date": "invalid-date"}
        )

        # Verify response
        assert response.status_code == 400
        assert "start_date must be in YYYY-MM-DD format" in response.json()["detail"]

    @patch("src.main.appointment_service")
    def test_get_appointments_no_filters(
        self, mock_service, test_client, sample_appointment
    ):
        """Test appointment retrieval with no filters."""
        # Setup mock
        mock_service.search_appointments.return_value = [sample_appointment]

        # Make request
        response = test_client.get("/api/v1/appointments")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Verify service called with no filters
        mock_service.search_appointments.assert_called_once_with(
            practitioner_reference=None, status=None
        )


class TestProvidersEndpoint:
    """Test GET /api/v1/providers endpoint."""

    @patch("src.main.provider_schedule_service")
    def test_get_providers_success(self, mock_service, test_client, sample_provider):
        """Test successful retrieval of providers."""
        # Setup mock
        mock_service.get_providers.return_value = [sample_provider]

        # Make request
        response = test_client.get("/api/v1/providers")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 1
        assert len(data["providers"]) == 1

        provider = data["providers"][0]
        assert provider["id"] == "provider-789"
        assert provider["name"] == "John Smith"
        assert provider["reference"] == "Practitioner/provider-789"

        # Verify service called
        mock_service.get_providers.assert_called_once()

    @patch("src.main.provider_schedule_service")
    def test_get_providers_filters_inactive(self, mock_service, test_client):
        """Test that inactive providers are filtered out."""
        # Create inactive provider
        inactive_provider_data = {
            "id": "provider-999",
            "active": False,
            "name": [{"given": ["Jane"], "family": "Doe"}],
        }
        inactive_provider = Provider(inactive_provider_data)

        # Setup mock
        mock_service.get_providers.return_value = [inactive_provider]

        # Make request
        response = test_client.get("/api/v1/providers")

        # Verify response (inactive provider filtered out)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 0
        assert len(data["providers"]) == 0

    @patch("src.main.provider_schedule_service")
    def test_get_providers_service_error(self, mock_service, test_client):
        """Test handling of provider service errors."""
        # Setup mock
        mock_service.get_providers.side_effect = ProviderScheduleError(
            "Provider service unavailable"
        )

        # Make request
        response = test_client.get("/api/v1/providers")

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "provider_error"
        assert "Provider service unavailable" in data["message"]


class TestAppointmentDataModels:
    """Test appointment data model conversions."""

    def test_appointment_to_dict(self, sample_appointment):
        """Test appointment object to dictionary conversion."""
        appointment_dict = sample_appointment.to_dict()

        assert appointment_dict["id"] == "appointment-123"
        assert appointment_dict["status"] == "booked"
        assert appointment_dict["start"] == "2025-09-21T09:00:00Z"
        assert appointment_dict["end"] == "2025-09-21T10:00:00Z"
        assert appointment_dict["description"] == "Regular checkup"
        assert appointment_dict["patient_name"] == "John Doe"
        assert appointment_dict["provider_name"] == "Dr. Smith"
        assert appointment_dict["time_display"] == "9:00 AM - 10:00 AM"

    def test_appointment_time_display_formatting(self):
        """Test time display formatting."""
        appointment_data = {
            "id": "test-123",
            "status": "booked",
            "start": "2025-09-21T14:30:00Z",
            "end": "2025-09-21T15:45:00Z",
            "participant": [],
        }
        appointment = Appointment(appointment_data)

        assert appointment.get_time_display() == "2:30 PM - 3:45 PM"

    def test_appointment_date_display_formatting(self):
        """Test date display formatting."""
        appointment_data = {
            "id": "test-123",
            "status": "booked",
            "start": "2025-09-21T09:00:00Z",
            "participant": [],
        }
        appointment = Appointment(appointment_data)

        assert appointment.get_date_display() == "September 21, 2025"

    def test_appointment_patient_name_anonymization(self):
        """Test patient name anonymization for privacy."""
        appointment_data = {
            "id": "test-123",
            "status": "booked",
            "participant": [
                {
                    "actor": {
                        "reference": "Patient/123456789"
                        # No display name provided
                    }
                }
            ],
        }
        appointment = Appointment(appointment_data)

        # Should return last 4 chars of ID for privacy
        assert appointment.get_patient_name() == "Patient 6789"

    def test_appointment_missing_data_handling(self):
        """Test handling of missing appointment data."""
        appointment_data = {"id": "test-123", "status": "booked", "participant": []}
        appointment = Appointment(appointment_data)

        assert appointment.get_time_display() == "Time TBD"
        assert appointment.get_date_display() == "Date TBD"
        assert appointment.get_patient_name() == "Unknown Patient"
        assert appointment.get_provider_name() == "Unknown Provider"


class TestAppointmentAPIRateLimiting:
    """Test rate limiting on appointment API endpoints."""

    def test_rate_limiting_appointments_today(self, test_client):
        """Test rate limiting on today's appointments endpoint."""
        # Make multiple requests quickly to trigger rate limiting
        responses = []
        for i in range(35):  # Limit is 30/minute
            response = test_client.get("/api/v1/appointments/today")
            responses.append(response)

        # Check that some requests are rate limited
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes  # Too Many Requests

    def test_rate_limiting_appointments_filter(self, test_client):
        """Test rate limiting on filtered appointments endpoint."""
        # Make multiple requests quickly to trigger rate limiting
        responses = []
        for i in range(35):  # Limit is 30/minute
            response = test_client.get("/api/v1/appointments")
            responses.append(response)

        # Check that some requests are rate limited
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes  # Too Many Requests


class TestAppointmentAPIAuditLogging:
    """Test audit logging for appointment API endpoints."""

    @patch("src.main.audit_logger")
    @patch("src.main.appointment_service")
    def test_audit_logging_appointments_today(
        self, mock_service, mock_audit_logger, test_client, sample_appointment
    ):
        """Test audit logging for today's appointments endpoint."""
        # Setup mock
        mock_service.get_appointments_today.return_value = [sample_appointment]

        # Make request
        response = test_client.get("/api/v1/appointments/today")

        # Verify audit logging
        assert response.status_code == 200
        assert (
            mock_audit_logger.log_event.call_count >= 2
        )  # Request and completion events

        # Check that proper events were logged
        logged_events = [
            call.args[0] for call in mock_audit_logger.log_event.call_args_list
        ]
        assert "appointments_today_requested" in logged_events
        assert "appointments_today_completed" in logged_events

    @patch("src.main.audit_logger")
    @patch("src.main.provider_schedule_service")
    def test_audit_logging_providers(
        self, mock_service, mock_audit_logger, test_client, sample_provider
    ):
        """Test audit logging for providers endpoint."""
        # Setup mock
        mock_service.get_providers.return_value = [sample_provider]

        # Make request
        response = test_client.get("/api/v1/providers")

        # Verify audit logging
        assert response.status_code == 200
        assert (
            mock_audit_logger.log_event.call_count >= 2
        )  # Request and completion events

        # Check that proper events were logged
        logged_events = [
            call.args[0] for call in mock_audit_logger.log_event.call_args_list
        ]
        assert "providers_filter_requested" in logged_events
        assert "providers_filter_completed" in logged_events


if __name__ == "__main__":
    pytest.main([__file__])
