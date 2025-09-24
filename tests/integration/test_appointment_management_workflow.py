"""
Integration Tests for Story 3.4: Manual Appointment Management Workflow

Tests the complete workflow of manual appointment management including
UI integration, API endpoints, and EMR synchronization.
"""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


class TestAppointmentManagementWorkflow:
    """Test complete appointment management workflows."""

    def setup_method(self):
        """Setup test environment."""
        self.client = TestClient(app)

        # Test appointment data
        self.appointment_data = {
            "patient_id": "test-patient-001",
            "provider_id": "test-provider-001",
            "appointment_time": "2025-09-24T14:00:00Z",
            "appointment_type": "consultation",
            "duration_minutes": 30,
            "notes": "Initial consultation",
        }

    @patch("src.main.appointment_service")
    @patch("src.main.dashboard_service")
    @patch("src.main.oauth_client")
    async def test_complete_manual_appointment_lifecycle(
        self, mock_oauth, mock_dashboard, mock_service
    ):
        """Test complete lifecycle: create -> edit -> cancel."""

        # Mock appointment creation
        mock_appointment = MagicMock()
        mock_appointment.id = "lifecycle-test-001"
        mock_appointment.to_dict.return_value = {
            "id": "lifecycle-test-001",
            "patient_name": "Test Patient",
            "provider_name": "Dr. Test",
            "start": "2025-09-24T14:00:00Z",
            "status": "booked",
        }
        mock_service.create_appointment = AsyncMock(return_value=mock_appointment)
        mock_service.update_appointment = AsyncMock(return_value=mock_appointment)
        mock_service.cancel_appointment = AsyncMock(return_value=None)

        mock_dashboard.track_ai_appointment = MagicMock()
        mock_dashboard.update_appointment_status = MagicMock()

        # Step 1: Create manual appointment
        create_request = {
            "patient_id": "test-patient-001",
            "time": "2025-09-24T14:00:00Z",
            "provider_id": "test-provider-001",
            "appointment_type": "consultation",
            "notes": "Initial consultation",
            "staff_member_id": "test-staff",
        }

        create_response = self.client.post(
            "/api/v1/appointments/manual", json=create_request
        )

        assert create_response.status_code == 200
        create_data = create_response.json()
        assert create_data["status"] == "created"
        appointment_id = create_data["appointment_id"]

        # Verify AI tracking was called
        mock_dashboard.track_ai_appointment.assert_called_once()

        # Step 2: Edit appointment
        edit_request = {
            "time": "2025-09-24T15:00:00Z",
            "notes": "Updated consultation time",
            "staff_member_id": "test-staff",
        }

        edit_response = self.client.put(
            f"/api/v1/appointments/{appointment_id}", json=edit_request
        )

        assert edit_response.status_code == 200
        edit_data = edit_response.json()
        assert edit_data["status"] == "updated"

        # Step 3: Cancel appointment
        cancel_request = {
            "reason": "patient_request",
            "staff_member_id": "test-staff",
            "notes": "Patient requested cancellation",
        }

        cancel_response = self.client.request(
            "DELETE", f"/api/v1/appointments/{appointment_id}", json=cancel_request
        )

        assert cancel_response.status_code == 200
        cancel_data = cancel_response.json()
        assert cancel_data["status"] == "cancelled"

        # Verify AI tracking was updated
        mock_dashboard.update_appointment_status.assert_called_once()

    @patch("src.main.appointment_service")
    @patch("src.main.dashboard_service")
    def test_bulk_operations_workflow(self, mock_dashboard, mock_service):
        """Test bulk operations workflow."""

        # Mock services for bulk operations
        mock_service.cancel_appointment = AsyncMock(return_value=None)
        mock_service.update_appointment = AsyncMock(return_value=MagicMock())

        # Test bulk cancellation
        bulk_cancel_request = {
            "operation": "cancel",
            "appointment_ids": ["bulk-1", "bulk-2", "bulk-3"],
            "new_params": {"reason": "provider_unavailable"},
            "staff_member_id": "test-staff",
        }

        cancel_response = self.client.post(
            "/api/v1/appointments/bulk", json=bulk_cancel_request
        )

        assert cancel_response.status_code == 200
        cancel_data = cancel_response.json()
        assert cancel_data["status"] == "completed"
        assert len(cancel_data["results"]) == 3

        # Verify all appointments were processed
        assert mock_service.cancel_appointment.call_count == 3

        # Test bulk rescheduling
        bulk_reschedule_request = {
            "operation": "reschedule",
            "appointment_ids": ["reschedule-1", "reschedule-2"],
            "new_params": {"new_time": "2025-09-25T10:00:00Z"},
            "staff_member_id": "test-staff",
        }

        reschedule_response = self.client.post(
            "/api/v1/appointments/bulk", json=bulk_reschedule_request
        )

        assert reschedule_response.status_code == 200
        reschedule_data = reschedule_response.json()
        assert reschedule_data["status"] == "completed"
        assert len(reschedule_data["results"]) == 2

        # Verify all appointments were updated
        assert mock_service.update_appointment.call_count == 2

    @patch("src.main.appointment_service")
    def test_conflict_override_workflow(self, mock_service):
        """Test conflict override functionality."""

        # Mock appointment retrieval
        mock_appointment = MagicMock()
        mock_service.get_appointment_by_id = AsyncMock(return_value=mock_appointment)

        # Test conflict override
        override_request = {
            "justification": "Medical emergency requires immediate scheduling",
            "staff_member_id": "senior-staff-001",
            "override_type": "time_conflict",
        }

        response = self.client.post(
            "/api/v1/appointments/conflict-appointment/override", json=override_request
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "overridden"
        assert "time_conflict" in data["conflicts_ignored"]
        assert "audit_id" in data

        # Verify appointment was retrieved
        mock_service.get_appointment_by_id.assert_called_once_with(
            "conflict-appointment"
        )

    @patch("src.main.appointment_service")
    @patch("src.main.dashboard_service")
    def test_error_handling_workflow(self, mock_dashboard, mock_service):
        """Test error handling in appointment workflows."""

        # Test service failure during creation
        mock_service.create_appointment = AsyncMock(
            side_effect=Exception("EMR service unavailable")
        )

        create_request = {
            "patient_id": "error-patient",
            "time": "2025-09-24T14:00:00Z",
            "provider_id": "error-provider",
            "staff_member_id": "test-staff",
        }

        response = self.client.post("/api/v1/appointments/manual", json=create_request)

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]

        # Test invalid time format
        invalid_request = create_request.copy()
        invalid_request["time"] = "not-a-valid-time"

        response = self.client.post("/api/v1/appointments/manual", json=invalid_request)

        assert response.status_code == 400
        assert "Invalid time format" in response.json()["detail"]

    def test_api_rate_limiting(self):
        """Test rate limiting on appointment endpoints."""

        # Create a simple request that should trigger rate limiting
        test_request = {
            "patient_id": "rate-test",
            "time": "2025-09-24T14:00:00Z",
            "provider_id": "rate-provider",
            "staff_member_id": "rate-staff",
        }

        # Make multiple requests rapidly
        responses = []
        for i in range(25):  # Exceed the 20/minute limit
            response = self.client.post(
                "/api/v1/appointments/manual", json=test_request
            )
            responses.append(response.status_code)

        # Should eventually get rate limited (429 status)
        # Note: This test might be flaky in actual implementation
        # as it depends on the rate limiter state
        assert any(status == 429 for status in responses[-5:])

    @patch("src.main.appointment_service")
    @patch("src.main.dashboard_service")
    def test_ai_integration_workflow(self, mock_dashboard, mock_service):
        """Test AI scheduling integration throughout workflow."""

        # Wait to avoid rate limiting from previous tests
        time.sleep(2)

        # Mock AI tracking service
        mock_dashboard.track_ai_appointment = MagicMock()
        mock_dashboard.update_appointment_status = MagicMock()

        # Mock appointment service
        mock_appointment = MagicMock()
        mock_appointment.id = "ai-integration-test"
        mock_service.create_appointment = AsyncMock(return_value=mock_appointment)
        mock_service.cancel_appointment = AsyncMock(return_value=None)

        # Create manual appointment
        create_request = {
            "patient_id": "ai-test-patient",
            "time": "2025-09-24T16:00:00Z",
            "provider_id": "ai-test-provider",
            "appointment_type": "manual",
            "staff_member_id": "ai-test-staff",
        }

        create_response = self.client.post(
            "/api/v1/appointments/manual", json=create_request
        )

        assert create_response.status_code == 200

        # Verify AI tracking was called with correct parameters
        mock_dashboard.track_ai_appointment.assert_called_once()
        ai_call_args = mock_dashboard.track_ai_appointment.call_args[1]

        assert ai_call_args["appointment_id"] == "ai-integration-test"
        assert (
            ai_call_args["ai_confidence"] == 1.0
        )  # Manual appointments = 100% confidence
        assert ai_call_args["appointment_type"] == "manual"
        assert ai_call_args["provider_id"] == "ai-test-provider"
        assert ai_call_args["patient_phone_hash"] is None

        # Cancel appointment and verify AI tracking update
        cancel_request = {
            "reason": "test_cancellation",
            "staff_member_id": "ai-test-staff",
        }

        cancel_response = self.client.request(
            "DELETE", "/api/v1/appointments/ai-integration-test", json=cancel_request
        )

        assert cancel_response.status_code == 200

        # Verify AI status was updated
        mock_dashboard.update_appointment_status.assert_called_once()
        status_call_args = mock_dashboard.update_appointment_status.call_args
        assert status_call_args[1]["appointment_id"] == "ai-integration-test"

    def test_request_validation(self):
        """Test request validation for all endpoints."""

        # Test missing required fields
        incomplete_request = {
            "patient_id": "test-patient"
            # Missing required fields: time, provider_id, staff_member_id
        }

        response = self.client.post(
            "/api/v1/appointments/manual", json=incomplete_request
        )

        assert response.status_code == 422  # Unprocessable Entity

        # Test invalid field types
        invalid_types_request = {
            "patient_id": 123,  # Should be string
            "time": "2025-09-24T14:00:00Z",
            "provider_id": "test-provider",
            "staff_member_id": "test-staff",
        }

        response = self.client.post(
            "/api/v1/appointments/manual", json=invalid_types_request
        )

        assert response.status_code == 422

    @patch("src.main.appointment_service")
    def test_appointment_not_found_scenarios(self, mock_service):
        """Test scenarios where appointments are not found."""

        # Mock service to return None or raise exception
        mock_service.get_appointment_by_id = AsyncMock(
            side_effect=Exception("Appointment not found")
        )
        mock_service.update_appointment = AsyncMock(
            side_effect=Exception("Appointment not found")
        )
        mock_service.cancel_appointment = AsyncMock(
            side_effect=Exception("Appointment not found")
        )

        # Test update non-existent appointment
        update_request = {
            "time": "2025-09-24T15:00:00Z",
            "staff_member_id": "test-staff",
        }

        response = self.client.put(
            "/api/v1/appointments/non-existent-id", json=update_request
        )

        assert response.status_code == 400

        # Test cancel non-existent appointment
        cancel_request = {"reason": "test_reason", "staff_member_id": "test-staff"}

        response = self.client.request(
            "DELETE", "/api/v1/appointments/non-existent-id", json=cancel_request
        )

        assert response.status_code == 400

        # Test override non-existent appointment
        override_request = {
            "justification": "test justification",
            "staff_member_id": "test-staff",
            "override_type": "test_override",
        }

        response = self.client.post(
            "/api/v1/appointments/non-existent-id/override", json=override_request
        )

        assert response.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
