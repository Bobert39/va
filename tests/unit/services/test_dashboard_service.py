"""
Unit tests for Dashboard Service.

Tests the dashboard service functionality including appointment retrieval,
real-time updates, export features, and analytics.
"""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.dashboard_service import AppointmentStatus, DashboardService


class TestDashboardService:
    """Test cases for DashboardService."""

    @pytest.fixture
    def mock_emr_service(self):
        """Mock EMR service."""
        mock = AsyncMock()
        mock.get_appointments_range = AsyncMock()
        return mock

    @pytest.fixture
    def mock_system_monitoring(self):
        """Mock system monitoring service."""
        mock = Mock()
        mock.track_dashboard_view = Mock()
        mock.track_ai_appointment = Mock()
        return mock

    @pytest.fixture
    def mock_audit_service(self):
        """Mock audit service."""
        mock = Mock()
        mock.log_dashboard_access = Mock()
        mock.log_data_export = Mock()
        return mock

    @pytest.fixture
    def dashboard_service(
        self, mock_emr_service, mock_system_monitoring, mock_audit_service
    ):
        """Create dashboard service instance."""
        return DashboardService(
            emr_service=mock_emr_service,
            system_monitoring=mock_system_monitoring,
            audit_service=mock_audit_service,
        )

    @pytest.fixture
    def sample_emr_appointments(self):
        """Sample EMR appointment data."""
        return [
            {
                "id": "appt_1",
                "patient_name": "John Doe",
                "provider_name": "Dr. Smith",
                "provider_id": "provider_1",
                "appointment_datetime": datetime.now(),
                "appointment_type": "consultation",
                "status": "booked",
            },
            {
                "id": "appt_2",
                "patient_name": "Jane Smith",
                "provider_name": "Dr. Jones",
                "provider_id": "provider_2",
                "appointment_datetime": datetime.now() + timedelta(hours=1),
                "appointment_type": "follow_up",
                "status": "booked",
            },
        ]

    def test_initialization(self, dashboard_service):
        """Test dashboard service initialization."""
        assert dashboard_service.ai_appointments == {}
        assert dashboard_service.active_connections == []
        assert dashboard_service.config["max_appointments_display"] == 100

    def test_track_ai_appointment(self, dashboard_service):
        """Test tracking AI appointments."""
        appointment_id = "appt_1"
        voice_call_id = "call_123"
        status = AppointmentStatus.CONFIRMED
        ai_confidence = 0.85
        provider_id = "provider_1"
        appointment_type = "consultation"
        appointment_datetime = datetime.now()

        dashboard_service.track_ai_appointment(
            appointment_id=appointment_id,
            voice_call_id=voice_call_id,
            status=status,
            ai_confidence=ai_confidence,
            provider_id=provider_id,
            appointment_type=appointment_type,
            appointment_datetime=appointment_datetime,
        )

        # Verify appointment is tracked
        assert appointment_id in dashboard_service.ai_appointments
        tracked = dashboard_service.ai_appointments[appointment_id]
        assert tracked["status"] == status.value
        assert tracked["ai_confidence"] == ai_confidence
        assert tracked["voice_call_id"] == voice_call_id

    def test_update_appointment_status(self, dashboard_service):
        """Test updating appointment status."""
        appointment_id = "appt_1"

        # First track an appointment
        dashboard_service.track_ai_appointment(
            appointment_id=appointment_id,
            voice_call_id="call_123",
            status=AppointmentStatus.PENDING,
            ai_confidence=0.85,
            provider_id="provider_1",
            appointment_type="consultation",
            appointment_datetime=datetime.now(),
        )

        # Update status
        dashboard_service.update_appointment_status(
            appointment_id, AppointmentStatus.CONFIRMED
        )

        assert (
            dashboard_service.ai_appointments[appointment_id]["status"] == "confirmed"
        )

    @pytest.mark.asyncio
    async def test_get_ai_scheduled_appointments_no_data(
        self, dashboard_service, mock_emr_service
    ):
        """Test getting AI appointments when none exist."""
        mock_emr_service.get_appointments_range.return_value = []

        result = await dashboard_service.get_ai_scheduled_appointments()

        assert result["status"] == "success"
        assert result["appointments"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_get_ai_scheduled_appointments_with_data(
        self, dashboard_service, mock_emr_service, sample_emr_appointments
    ):
        """Test getting AI appointments with tracked data."""
        # Mock EMR return
        mock_emr_service.get_appointments_range.return_value = sample_emr_appointments

        # Track some AI appointments
        dashboard_service.track_ai_appointment(
            appointment_id="appt_1",
            voice_call_id="call_123",
            status=AppointmentStatus.CONFIRMED,
            ai_confidence=0.90,
            provider_id="provider_1",
            appointment_type="consultation",
            appointment_datetime=datetime.now(),
        )

        result = await dashboard_service.get_ai_scheduled_appointments()

        assert result["status"] == "success"
        assert len(result["appointments"]) == 1
        assert result["appointments"][0]["id"] == "appt_1"
        assert result["appointments"][0]["status"] == "confirmed"
        assert result["appointments"][0]["ai_confidence"] == 0.90

    @pytest.mark.asyncio
    async def test_get_ai_scheduled_appointments_with_filters(
        self, dashboard_service, mock_emr_service, sample_emr_appointments
    ):
        """Test filtering AI appointments."""
        mock_emr_service.get_appointments_range.return_value = sample_emr_appointments

        # Track appointments with different statuses
        dashboard_service.track_ai_appointment(
            appointment_id="appt_1",
            voice_call_id="call_123",
            status=AppointmentStatus.CONFIRMED,
            ai_confidence=0.90,
            provider_id="provider_1",
            appointment_type="consultation",
            appointment_datetime=datetime.now(),
        )

        dashboard_service.track_ai_appointment(
            appointment_id="appt_2",
            voice_call_id="call_124",
            status=AppointmentStatus.PENDING,
            ai_confidence=0.75,
            provider_id="provider_2",
            appointment_type="follow_up",
            appointment_datetime=datetime.now(),
        )

        # Filter by status
        result = await dashboard_service.get_ai_scheduled_appointments(
            status="confirmed"
        )

        assert result["status"] == "success"
        assert len(result["appointments"]) == 1
        assert result["appointments"][0]["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_export_appointments_csv(
        self, dashboard_service, mock_emr_service, sample_emr_appointments
    ):
        """Test CSV export functionality."""
        mock_emr_service.get_appointments_range.return_value = sample_emr_appointments

        dashboard_service.track_ai_appointment(
            appointment_id="appt_1",
            voice_call_id="call_123",
            status=AppointmentStatus.CONFIRMED,
            ai_confidence=0.90,
            provider_id="provider_1",
            appointment_type="consultation",
            appointment_datetime=datetime.now(),
        )

        result = await dashboard_service.export_appointments(format="csv")

        assert result["status"] == "success"
        assert result["format"] == "csv"
        assert "content" in result
        assert "filename" in result
        assert result["filename"].endswith(".csv")

    @pytest.mark.asyncio
    async def test_export_appointments_pdf(
        self, dashboard_service, mock_emr_service, sample_emr_appointments
    ):
        """Test PDF export functionality."""
        mock_emr_service.get_appointments_range.return_value = sample_emr_appointments

        dashboard_service.track_ai_appointment(
            appointment_id="appt_1",
            voice_call_id="call_123",
            status=AppointmentStatus.CONFIRMED,
            ai_confidence=0.90,
            provider_id="provider_1",
            appointment_type="consultation",
            appointment_datetime=datetime.now(),
        )

        result = await dashboard_service.export_appointments(format="pdf")

        assert result["status"] == "success"
        assert result["format"] == "pdf"
        assert "content" in result
        assert "filename" in result
        assert result["filename"].endswith(".pdf")

    @pytest.mark.asyncio
    async def test_export_appointments_invalid_format(self, dashboard_service):
        """Test export with invalid format."""
        result = await dashboard_service.export_appointments(format="xml")

        assert result["status"] == "error"
        assert "Unsupported export format" in result["error"]

    def test_get_appointment_analytics_no_data(self, dashboard_service):
        """Test analytics with no appointments."""
        analytics = dashboard_service.get_appointment_analytics()

        assert analytics["total_bookings"] == 0
        assert analytics["success_rate"] == 0
        assert analytics["status_breakdown"] == {}

    def test_get_appointment_analytics_with_data(self, dashboard_service):
        """Test analytics with appointment data."""
        # Track appointments with different statuses
        dashboard_service.track_ai_appointment(
            appointment_id="appt_1",
            voice_call_id="call_123",
            status=AppointmentStatus.CONFIRMED,
            ai_confidence=0.90,
            provider_id="provider_1",
            appointment_type="consultation",
            appointment_datetime=datetime.now(),
        )

        dashboard_service.track_ai_appointment(
            appointment_id="appt_2",
            voice_call_id="call_124",
            status=AppointmentStatus.FAILED,
            ai_confidence=0.50,
            provider_id="provider_2",
            appointment_type="follow_up",
            appointment_datetime=datetime.now(),
        )

        analytics = dashboard_service.get_appointment_analytics()

        assert analytics["total_bookings"] == 2
        assert analytics["success_rate"] == 50.0  # 1 confirmed out of 2
        assert analytics["status_breakdown"]["confirmed"] == 1
        assert analytics["status_breakdown"]["failed"] == 1

    def test_websocket_connection_management(self, dashboard_service):
        """Test WebSocket connection management."""
        mock_websocket = Mock()

        # Add connection
        dashboard_service.add_connection(mock_websocket)
        assert len(dashboard_service.active_connections) == 1

        # Remove connection
        dashboard_service.remove_connection(mock_websocket)
        assert len(dashboard_service.active_connections) == 0

    @pytest.mark.asyncio
    async def test_broadcast_appointment_update(self, dashboard_service):
        """Test broadcasting updates to WebSocket connections."""
        mock_websocket1 = AsyncMock()
        mock_websocket2 = AsyncMock()

        dashboard_service.add_connection(mock_websocket1)
        dashboard_service.add_connection(mock_websocket2)

        update_data = {
            "event": "appointment_created",
            "appointment_id": "appt_1",
            "status": "confirmed",
        }

        await dashboard_service.broadcast_appointment_update(update_data)

        # Verify both connections received the message
        mock_websocket1.send_text.assert_called_once()
        mock_websocket2.send_text.assert_called_once()

        # Verify correct message format
        sent_message = mock_websocket1.send_text.call_args[0][0]
        assert json.loads(sent_message) == update_data

    @pytest.mark.asyncio
    async def test_broadcast_update_failed_connection(self, dashboard_service):
        """Test broadcasting with a failed connection."""
        mock_websocket_good = AsyncMock()
        mock_websocket_bad = AsyncMock()
        mock_websocket_bad.send_text.side_effect = Exception("Connection failed")

        dashboard_service.add_connection(mock_websocket_good)
        dashboard_service.add_connection(mock_websocket_bad)

        update_data = {"event": "test"}

        await dashboard_service.broadcast_appointment_update(update_data)

        # Good connection should still be active
        assert len(dashboard_service.active_connections) == 1
        assert mock_websocket_good in dashboard_service.active_connections
        assert mock_websocket_bad not in dashboard_service.active_connections

    def test_csv_generation(self, dashboard_service):
        """Test CSV content generation."""
        appointments = [
            {
                "id": "appt_1",
                "patient_name": "John Doe",
                "provider_name": "Dr. Smith",
                "appointment_datetime": "2023-01-01T10:00:00",
                "appointment_type": "consultation",
                "status": "confirmed",
                "booking_source": "voice_ai",
                "ai_confidence": 0.90,
                "booking_timestamp": "2023-01-01T09:00:00",
            }
        ]

        csv_content = dashboard_service._generate_csv(appointments)

        assert "appointment_id,patient_name,provider_name" in csv_content
        assert "appt_1,John Doe,Dr. Smith" in csv_content

    @pytest.mark.asyncio
    async def test_pdf_generation(self, dashboard_service):
        """Test PDF report generation."""
        appointments = [
            {
                "id": "appt_1",
                "patient_name": "John Doe",
                "provider_name": "Dr. Smith",
                "appointment_datetime": "2023-01-01T10:00:00",
                "status": "confirmed",
            }
        ]

        pdf_content = await dashboard_service._generate_pdf_report(appointments)

        assert isinstance(pdf_content, bytes)
        assert b"AI-Scheduled Appointments Report" in pdf_content
        assert b"Total Appointments: 1" in pdf_content

    @pytest.mark.asyncio
    async def test_error_handling_emr_failure(
        self, dashboard_service, mock_emr_service
    ):
        """Test error handling when EMR service fails."""
        mock_emr_service.get_appointments_range.side_effect = Exception("EMR error")

        result = await dashboard_service.get_ai_scheduled_appointments()

        assert result["status"] == "error"
        assert "Failed to retrieve appointments" in result["error"]

    def test_audit_logging_verification(
        self, dashboard_service, mock_audit_service, mock_system_monitoring
    ):
        """Test that audit events are properly logged."""
        dashboard_service.track_ai_appointment(
            appointment_id="appt_1",
            voice_call_id="call_123",
            status=AppointmentStatus.CONFIRMED,
            ai_confidence=0.90,
            provider_id="provider_1",
            appointment_type="consultation",
            appointment_datetime=datetime.now(),
        )

        # Verify system monitoring was called
        mock_system_monitoring.track_ai_appointment.assert_called_once_with(
            status="confirmed", confidence=0.90
        )

    @pytest.mark.asyncio
    async def test_dashboard_view_tracking(
        self, dashboard_service, mock_emr_service, mock_system_monitoring
    ):
        """Test that dashboard views are tracked."""
        mock_emr_service.get_appointments_range.return_value = []

        await dashboard_service.get_ai_scheduled_appointments()

        # Verify dashboard view was tracked
        mock_system_monitoring.track_dashboard_view.assert_called_once_with(
            appointment_count=0
        )
