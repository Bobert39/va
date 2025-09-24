"""
Test Suite for Story 3.4: Manual Appointment Override and Management

Tests for the appointment management API endpoints and functionality
including manual appointment creation, editing, cancellation, and bulk operations.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


class TestManualAppointmentManagement:
    """Test manual appointment management functionality."""

    def setup_method(self):
        """Setup test client and mock data."""
        self.client = TestClient(app)

        # Sample appointment data
        self.sample_appointment = {
            "id": "test-appointment-123",
            "patient_name": "John Doe",
            "patient_id": "patient-456",
            "provider_id": "provider-789",
            "provider_name": "Dr. Smith",
            "start": "2025-09-23T14:00:00Z",
            "end": "2025-09-23T14:30:00Z",
            "status": "booked",
            "appointment_type": "consultation",
            "description": "Test appointment",
        }

        # Mock appointment request data
        self.update_request = {
            "time": "2025-09-23T15:00:00Z",
            "provider_id": "provider-789",
            "notes": "Updated appointment notes",
            "staff_member_id": "staff-001",
        }

        self.cancel_request = {
            "reason": "patient_request",
            "staff_member_id": "staff-001",
            "notes": "Patient requested cancellation",
        }

        self.manual_request = {
            "patient_id": "patient-456",
            "time": "2025-09-23T16:00:00Z",
            "provider_id": "provider-789",
            "appointment_type": "follow_up",
            "notes": "Manual appointment creation",
            "staff_member_id": "staff-001",
        }

        self.bulk_request = {
            "operation": "cancel",
            "appointment_ids": ["apt-1", "apt-2", "apt-3"],
            "new_params": {"reason": "provider_unavailable"},
            "staff_member_id": "staff-001",
        }

    @patch("src.main.appointment_service")
    @patch("src.main.log_audit_event")
    def test_update_appointment_success(self, mock_audit, mock_service):
        """Test successful appointment update."""
        # Mock appointment service
        mock_appointment = MagicMock()
        mock_appointment.to_dict.return_value = self.sample_appointment
        mock_service.update_appointment = AsyncMock(return_value=mock_appointment)

        # Make request
        response = self.client.put(
            "/api/v1/appointments/test-appointment-123", json=self.update_request
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert "appointment" in data
        assert "audit_id" in data

        # Verify service was called correctly
        mock_service.update_appointment.assert_called_once()
        call_args = mock_service.update_appointment.call_args
        assert call_args[1]["appointment_id"] == "test-appointment-123"

        # Verify audit logging
        mock_audit.assert_called()

    @patch("src.main.appointment_service")
    @patch("src.main.log_audit_event")
    def test_update_appointment_invalid_time(self, mock_audit, mock_service):
        """Test appointment update with invalid time format."""
        invalid_request = self.update_request.copy()
        invalid_request["time"] = "invalid-time-format"

        response = self.client.put(
            "/api/v1/appointments/test-appointment-123", json=invalid_request
        )

        assert response.status_code == 400
        assert "Invalid time format" in response.json()["detail"]

    @patch("src.main.appointment_service")
    @patch("src.main.dashboard_service")
    @patch("src.main.log_audit_event")
    def test_cancel_appointment_success(self, mock_audit, mock_dashboard, mock_service):
        """Test successful appointment cancellation."""
        # Mock services
        mock_service.cancel_appointment = AsyncMock(return_value=None)
        mock_dashboard.update_appointment_status = MagicMock()

        # Make request
        response = self.client.request(
            "DELETE",
            "/api/v1/appointments/test-appointment-123",
            json=self.cancel_request,
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert "audit_id" in data

        # Verify service calls
        mock_service.cancel_appointment.assert_called_once_with(
            appointment_id="test-appointment-123", reason="patient_request"
        )

        # Verify AI tracking update
        mock_dashboard.update_appointment_status.assert_called_once()

        # Verify audit logging
        mock_audit.assert_called()

    @patch("src.main.appointment_service")
    @patch("src.main.dashboard_service")
    @patch("src.main.log_audit_event")
    def test_create_manual_appointment_success(
        self, mock_audit, mock_dashboard, mock_service
    ):
        """Test successful manual appointment creation."""
        # Mock services
        mock_appointment = MagicMock()
        mock_appointment.id = "new-appointment-123"
        mock_service.create_appointment = AsyncMock(return_value=mock_appointment)
        mock_dashboard.track_ai_appointment = MagicMock()

        # Make request
        response = self.client.post(
            "/api/v1/appointments/manual", json=self.manual_request
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert data["appointment_id"] == "new-appointment-123"
        assert "audit_id" in data

        # Verify service calls
        mock_service.create_appointment.assert_called_once()
        call_args = mock_service.create_appointment.call_args[0][0]
        assert call_args["patient_reference"] == "Patient/patient-456"
        assert call_args["practitioner_reference"] == "Practitioner/provider-789"
        assert call_args["status"] == "booked"

        # Verify AI tracking
        mock_dashboard.track_ai_appointment.assert_called_once()
        track_args = mock_dashboard.track_ai_appointment.call_args[1]
        assert track_args["appointment_id"] == "new-appointment-123"
        assert (
            track_args["ai_confidence"] == 1.0
        )  # Manual appointments have 100% confidence

        # Verify audit logging
        mock_audit.assert_called()

    @patch("src.main.appointment_service")
    @patch("src.main.log_audit_event")
    def test_create_manual_appointment_invalid_time(self, mock_audit, mock_service):
        """Test manual appointment creation with invalid time."""
        invalid_request = self.manual_request.copy()
        invalid_request["time"] = "not-a-valid-time"

        response = self.client.post("/api/v1/appointments/manual", json=invalid_request)

        assert response.status_code == 400
        assert "Invalid time format" in response.json()["detail"]

    @patch("src.main.appointment_service")
    @patch("src.main.log_audit_event")
    def test_override_appointment_conflicts(self, mock_audit, mock_service):
        """Test appointment conflict override functionality."""
        # Mock service
        mock_appointment = MagicMock()
        mock_service.get_appointment_by_id = AsyncMock(return_value=mock_appointment)

        override_request = {
            "justification": "Emergency appointment needed",
            "staff_member_id": "staff-001",
            "override_type": "time_conflict",
        }

        # Make request
        response = self.client.post(
            "/api/v1/appointments/test-appointment-123/override", json=override_request
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "overridden"
        assert "time_conflict" in data["conflicts_ignored"]
        assert "audit_id" in data

        # Verify audit logging
        mock_audit.assert_called()

    @patch("src.main.appointment_service")
    @patch("src.main.log_audit_event")
    def test_bulk_cancel_appointments(self, mock_audit, mock_service):
        """Test bulk appointment cancellation."""
        # Mock service
        mock_service.cancel_appointment = AsyncMock(return_value=None)

        # Make request
        response = self.client.post("/api/v1/appointments/bulk", json=self.bulk_request)

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert len(data["results"]) == 3  # Should process all 3 appointments

        # Verify service was called for each appointment
        assert mock_service.cancel_appointment.call_count == 3

        # Verify audit logging
        mock_audit.assert_called()

    @patch("src.main.appointment_service")
    @patch("src.main.log_audit_event")
    def test_bulk_reschedule_appointments(self, mock_audit, mock_service):
        """Test bulk appointment rescheduling."""
        # Mock service
        mock_appointment = MagicMock()
        mock_service.update_appointment = AsyncMock(return_value=mock_appointment)

        reschedule_request = {
            "operation": "reschedule",
            "appointment_ids": ["apt-1", "apt-2"],
            "new_params": {"new_time": "2025-09-24T10:00:00Z"},
            "staff_member_id": "staff-001",
        }

        # Make request
        response = self.client.post(
            "/api/v1/appointments/bulk", json=reschedule_request
        )

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert len(data["results"]) == 2

        # Verify service was called for each appointment
        assert mock_service.update_appointment.call_count == 2

    def test_bulk_operations_invalid_operation(self):
        """Test bulk operations with invalid operation type."""
        invalid_request = self.bulk_request.copy()
        invalid_request["operation"] = "invalid_operation"

        response = self.client.post("/api/v1/appointments/bulk", json=invalid_request)

        assert response.status_code == 400
        assert "Operation must be 'reschedule' or 'cancel'" in response.json()["detail"]

    @patch("src.main.appointment_service")
    def test_bulk_reschedule_missing_new_time(self, mock_service):
        """Test bulk reschedule without required new_time parameter."""
        reschedule_request = {
            "operation": "reschedule",
            "appointment_ids": ["apt-1"],
            "new_params": {},  # Missing new_time
            "staff_member_id": "staff-001",
        }

        response = self.client.post(
            "/api/v1/appointments/bulk", json=reschedule_request
        )

        # Should complete but with errors for missing new_time
        assert response.status_code == 200
        data = response.json()
        assert len(data["failed_operations"]) == 1
        assert "new_time parameter required" in data["failed_operations"][0]["error"]


class TestAppointmentManagementIntegration:
    """Integration tests for appointment management with AI scheduling."""

    def setup_method(self):
        """Setup for integration tests."""
        self.client = TestClient(app)

    @patch("src.main.appointment_service")
    @patch("src.main.dashboard_service")
    def test_manual_appointment_ai_integration(self, mock_dashboard, mock_service):
        """Test that manual appointments are properly tracked in AI system."""
        # Mock services
        mock_appointment = MagicMock()
        mock_appointment.id = "ai-tracked-appointment"
        mock_service.create_appointment = AsyncMock(return_value=mock_appointment)
        mock_dashboard.track_ai_appointment = MagicMock()

        manual_request = {
            "patient_id": "patient-123",
            "time": "2025-09-23T14:00:00Z",
            "provider_id": "provider-456",
            "appointment_type": "consultation",
            "staff_member_id": "staff-001",
        }

        # Make request
        response = self.client.post("/api/v1/appointments/manual", json=manual_request)

        # Verify AI tracking was called with correct parameters
        assert response.status_code == 200
        mock_dashboard.track_ai_appointment.assert_called_once()

        # Verify AI tracking parameters
        call_kwargs = mock_dashboard.track_ai_appointment.call_args[1]
        assert call_kwargs["appointment_id"] == "ai-tracked-appointment"
        assert call_kwargs["ai_confidence"] == 1.0
        assert call_kwargs["appointment_type"] == "consultation"
        assert call_kwargs["provider_id"] == "provider-456"
        assert (
            call_kwargs["patient_phone_hash"] is None
        )  # Manual appointments don't have phone

    @patch("src.main.appointment_service")
    @patch("src.main.dashboard_service")
    def test_cancellation_ai_integration(self, mock_dashboard, mock_service):
        """Test that cancellations update AI tracking system."""
        # Mock services
        mock_service.cancel_appointment = AsyncMock(return_value=None)
        mock_dashboard.update_appointment_status = MagicMock()

        cancel_request = {"reason": "patient_request", "staff_member_id": "staff-001"}

        # Make request
        response = self.client.request(
            "DELETE", "/api/v1/appointments/test-appointment", json=cancel_request
        )

        # Verify AI tracking was updated
        assert response.status_code == 200
        mock_dashboard.update_appointment_status.assert_called_once()

        # Verify correct status update
        call_args = mock_dashboard.update_appointment_status.call_args
        assert call_args[1]["appointment_id"] == "test-appointment"
        # Should be marked as FAILED in AI system when cancelled


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
