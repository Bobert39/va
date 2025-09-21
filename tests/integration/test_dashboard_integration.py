"""
Integration tests for dashboard appointment management functionality.

These tests validate the complete integration between the web interface,
API endpoints, and backend services.
"""

import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services.appointment import Appointment, FHIRAppointmentService
from src.services.emr import EMROAuthClient
from src.services.provider_schedule import Provider, ProviderScheduleService


@pytest.fixture
def test_client():
    """Test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_oauth_client():
    """Mock OAuth client for testing."""
    client = Mock(spec=EMROAuthClient)
    client.get_valid_access_token = AsyncMock(return_value="mock-access-token")
    client._get_oauth_config = Mock(
        return_value={
            "fhir_base_url": "https://test-emr.example.com/fhir",
            "client_id": "test-client-id",
        }
    )
    return client


@pytest.fixture
def sample_appointments():
    """Sample appointment data for integration testing."""
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    appointments = [
        {
            "id": "appointment-1",
            "status": "booked",
            "start": f"{today}T09:00:00Z",
            "end": f"{today}T10:00:00Z",
            "description": "Regular checkup",
            "participant": [
                {"actor": {"reference": "Patient/123", "display": "Alice Johnson"}},
                {"actor": {"reference": "Practitioner/789", "display": "Dr. Smith"}},
            ],
            "appointmentType": {"coding": [{"display": "Checkup"}]},
        },
        {
            "id": "appointment-2",
            "status": "arrived",
            "start": f"{today}T11:00:00Z",
            "end": f"{today}T12:00:00Z",
            "description": "Follow-up visit",
            "participant": [
                {"actor": {"reference": "Patient/456", "display": "Bob Wilson"}},
                {"actor": {"reference": "Practitioner/789", "display": "Dr. Smith"}},
            ],
            "appointmentType": {"coding": [{"display": "Follow-up"}]},
        },
        {
            "id": "appointment-3",
            "status": "booked",
            "start": f"{tomorrow}T14:00:00Z",
            "end": f"{tomorrow}T15:00:00Z",
            "description": "Consultation",
            "participant": [
                {"actor": {"reference": "Patient/789", "display": "Carol Davis"}},
                {"actor": {"reference": "Practitioner/456", "display": "Dr. Jones"}},
            ],
            "appointmentType": {"coding": [{"display": "Consultation"}]},
        },
    ]

    return [Appointment(data) for data in appointments]


@pytest.fixture
def sample_providers():
    """Sample provider data for integration testing."""
    providers_data = [
        {
            "id": "789",
            "active": True,
            "name": [{"given": ["John"], "family": "Smith"}],
            "qualification": [{"code": {"coding": [{"display": "MD"}]}}],
        },
        {
            "id": "456",
            "active": True,
            "name": [{"given": ["Jane"], "family": "Jones"}],
            "qualification": [{"code": {"coding": [{"display": "MD"}]}}],
        },
        {
            "id": "999",
            "active": False,
            "name": [{"given": ["Inactive"], "family": "Provider"}],
            "qualification": [],
        },
    ]

    return [Provider(data) for data in providers_data]


class TestDashboardAccess:
    """Test dashboard accessibility and basic functionality."""

    def test_dashboard_loads_successfully(self, test_client):
        """Test that dashboard page loads without errors."""
        response = test_client.get("/dashboard")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Check for key dashboard elements
        content = response.text
        assert "Appointment Management" in content
        assert "OAuth 2.0 Configuration" in content
        assert "providerFilter" in content
        assert "appointmentList" in content

    def test_dashboard_includes_required_resources(self, test_client):
        """Test that dashboard includes required CSS and JavaScript resources."""
        response = test_client.get("/dashboard")

        assert response.status_code == 200
        content = response.text

        # Check for Bootstrap CSS and JS
        assert "bootstrap@5.3.0/dist/css/bootstrap.min.css" in content
        assert "bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js" in content

        # Check for Font Awesome
        assert "font-awesome" in content

        # Check for appointment management JavaScript
        assert "AppointmentManager" in content
        assert "loadTodaysAppointments" in content


class TestAppointmentAPIIntegration:
    """Test appointment API integration with dashboard functionality."""

    @patch("src.main.appointment_service")
    def test_todays_appointments_integration(
        self, mock_appointment_service, test_client, sample_appointments
    ):
        """Test integration of today's appointments API with dashboard."""
        # Filter today's appointments
        today = datetime.now().date()
        todays_appointments = [
            apt
            for apt in sample_appointments
            if apt.start and apt.start.startswith(today.isoformat())
        ]

        mock_appointment_service.get_appointments_today.return_value = (
            todays_appointments
        )

        # Test API endpoint
        response = test_client.get("/api/v1/appointments/today")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 2  # Two appointments today

        # Verify appointment data structure for dashboard
        for appointment in data["appointments"]:
            assert "id" in appointment
            assert "status" in appointment
            assert "patient_name" in appointment
            assert "provider_name" in appointment
            assert "time_display" in appointment
            assert "date_display" in appointment

    @patch("src.main.appointment_service")
    def test_filtered_appointments_integration(
        self, mock_appointment_service, test_client, sample_appointments
    ):
        """Test filtered appointments API integration."""
        mock_appointment_service.get_appointments_by_date_range.return_value = (
            sample_appointments
        )

        # Test with date range filter
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        response = test_client.get(
            "/api/v1/appointments",
            params={"start_date": today.isoformat(), "end_date": tomorrow.isoformat()},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 3  # All three appointments

        # Verify service was called with correct parameters
        mock_appointment_service.get_appointments_by_date_range.assert_called_once_with(
            start_date=today.isoformat(),
            end_date=tomorrow.isoformat(),
            practitioner_reference=None,
            status=None,
        )

    @patch("src.main.provider_schedule_service")
    def test_providers_filter_integration(
        self, mock_provider_service, test_client, sample_providers
    ):
        """Test provider filter API integration."""
        mock_provider_service.get_providers.return_value = sample_providers

        response = test_client.get("/api/v1/providers")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 2  # Only active providers

        # Verify provider data structure for dashboard
        for provider in data["providers"]:
            assert "id" in provider
            assert "name" in provider
            assert "reference" in provider
            assert provider["reference"].startswith("Practitioner/")


class TestAppointmentFiltering:
    """Test appointment filtering functionality."""

    @patch("src.main.appointment_service")
    def test_provider_filtering(
        self, mock_appointment_service, test_client, sample_appointments
    ):
        """Test filtering appointments by provider."""
        # Filter appointments for Dr. Smith
        dr_smith_appointments = [
            apt
            for apt in sample_appointments
            if any(
                p.get("actor", {}).get("reference") == "Practitioner/789"
                for p in apt.participants
            )
        ]

        mock_appointment_service.search_appointments.return_value = (
            dr_smith_appointments
        )

        response = test_client.get(
            "/api/v1/appointments", params={"provider": "Practitioner/789"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 2  # Two appointments with Dr. Smith

        # Verify all returned appointments have Dr. Smith as provider
        for appointment in data["appointments"]:
            assert appointment["practitioner_reference"] == "Practitioner/789"

    @patch("src.main.appointment_service")
    def test_status_filtering(
        self, mock_appointment_service, test_client, sample_appointments
    ):
        """Test filtering appointments by status."""
        # Filter booked appointments
        booked_appointments = [
            apt for apt in sample_appointments if apt.status == "booked"
        ]

        mock_appointment_service.search_appointments.return_value = booked_appointments

        response = test_client.get("/api/v1/appointments", params={"status": "booked"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 2  # Two booked appointments

        # Verify all returned appointments have booked status
        for appointment in data["appointments"]:
            assert appointment["status"] == "booked"

    @patch("src.main.appointment_service")
    def test_combined_filtering(
        self, mock_appointment_service, test_client, sample_appointments
    ):
        """Test combining multiple filters."""
        # Filter for Dr. Smith's booked appointments
        filtered_appointments = [
            apt
            for apt in sample_appointments
            if apt.status == "booked"
            and any(
                p.get("actor", {}).get("reference") == "Practitioner/789"
                for p in apt.participants
            )
        ]

        mock_appointment_service.search_appointments.return_value = (
            filtered_appointments
        )

        response = test_client.get(
            "/api/v1/appointments",
            params={"provider": "Practitioner/789", "status": "booked"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 1  # One booked appointment with Dr. Smith


class TestDateRangeHandling:
    """Test date range selection and handling."""

    @patch("src.main.appointment_service")
    def test_single_day_range(
        self, mock_appointment_service, test_client, sample_appointments
    ):
        """Test selecting a single day range."""
        today = datetime.now().date()
        todays_appointments = [
            apt
            for apt in sample_appointments
            if apt.start and apt.start.startswith(today.isoformat())
        ]

        mock_appointment_service.get_appointments_by_date_range.return_value = (
            todays_appointments
        )

        response = test_client.get(
            "/api/v1/appointments",
            params={"start_date": today.isoformat(), "end_date": today.isoformat()},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Verify service called with single day range
        mock_appointment_service.get_appointments_by_date_range.assert_called_once_with(
            start_date=today.isoformat(),
            end_date=today.isoformat(),
            practitioner_reference=None,
            status=None,
        )

    @patch("src.main.appointment_service")
    def test_week_range(
        self, mock_appointment_service, test_client, sample_appointments
    ):
        """Test selecting a week range."""
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=4)  # Friday

        mock_appointment_service.get_appointments_by_date_range.return_value = (
            sample_appointments
        )

        response = test_client.get(
            "/api/v1/appointments",
            params={
                "start_date": week_start.isoformat(),
                "end_date": week_end.isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_invalid_date_format_handling(self, test_client):
        """Test handling of invalid date formats."""
        response = test_client.get(
            "/api/v1/appointments",
            params={"start_date": "invalid-date", "end_date": "2025-09-21"},
        )

        assert response.status_code == 400
        assert "start_date must be in YYYY-MM-DD format" in response.json()["detail"]


class TestRealTimeUpdates:
    """Test real-time update functionality."""

    @patch("src.main.appointment_service")
    def test_appointment_data_freshness(
        self, mock_appointment_service, test_client, sample_appointments
    ):
        """Test that appointment data is fresh on each request."""
        # First request
        mock_appointment_service.get_appointments_today.return_value = (
            sample_appointments[:2]
        )
        response1 = test_client.get("/api/v1/appointments/today")

        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["total"] == 2

        # Second request with updated data
        mock_appointment_service.get_appointments_today.return_value = (
            sample_appointments
        )
        response2 = test_client.get("/api/v1/appointments/today")

        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["total"] == 3

        # Verify service called twice
        assert mock_appointment_service.get_appointments_today.call_count == 2


class TestResponsiveDesign:
    """Test responsive design elements in dashboard."""

    def test_dashboard_has_responsive_elements(self, test_client):
        """Test that dashboard includes responsive design elements."""
        response = test_client.get("/dashboard")

        assert response.status_code == 200
        content = response.text

        # Check for responsive grid classes
        assert "col-md-" in content
        assert "col-lg-" in content

        # Check for responsive viewport meta tag
        assert "viewport" in content
        assert "width=device-width" in content

        # Check for responsive appointment cards
        assert "card h-100" in content  # Equal height cards


class TestErrorHandling:
    """Test error handling in appointment management."""

    @patch("src.main.appointment_service")
    def test_appointment_service_error_handling(
        self, mock_appointment_service, test_client
    ):
        """Test handling of appointment service errors."""
        from src.services.appointment import FHIRAppointmentError

        mock_appointment_service.get_appointments_today.side_effect = (
            FHIRAppointmentError("FHIR server unavailable")
        )

        response = test_client.get("/api/v1/appointments/today")

        assert response.status_code == 200  # Error returned as JSON, not HTTP error
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "appointment_error"
        assert "FHIR server unavailable" in data["message"]

    @patch("src.main.provider_schedule_service")
    def test_provider_service_error_handling(self, mock_provider_service, test_client):
        """Test handling of provider service errors."""
        from src.services.provider_schedule import ProviderScheduleError

        mock_provider_service.get_providers.side_effect = ProviderScheduleError(
            "Provider service timeout"
        )

        response = test_client.get("/api/v1/providers")

        assert response.status_code == 200  # Error returned as JSON, not HTTP error
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "provider_error"
        assert "Provider service timeout" in data["message"]


class TestSessionManagement:
    """Test session management and security features."""

    def test_dashboard_requires_no_authentication_for_mvp(self, test_client):
        """Test that dashboard is accessible without authentication for MVP."""
        response = test_client.get("/dashboard")

        # For MVP, dashboard should be accessible without authentication
        assert response.status_code == 200
        assert "Appointment Management" in response.text

    def test_api_endpoints_accessible_for_mvp(self, test_client):
        """Test that API endpoints are accessible for MVP."""
        # For MVP, API endpoints should be accessible without authentication
        response = test_client.get("/api/v1/appointments/today")
        assert response.status_code in [
            200,
            401,
        ]  # 401 if OAuth not configured, 200 if mocked

        response = test_client.get("/api/v1/providers")
        assert response.status_code in [
            200,
            401,
        ]  # 401 if OAuth not configured, 200 if mocked


if __name__ == "__main__":
    pytest.main([__file__])
