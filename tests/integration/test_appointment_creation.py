"""
Integration tests for FHIR Appointment Creation.

This module tests the full appointment lifecycle including creation, retrieval,
modification, and cancellation against a real or mock OpenEMR instance.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.services.appointment import (
    Appointment,
    AppointmentConflictError,
    AppointmentNotFoundError,
    AppointmentStatus,
    FHIRAppointmentService,
)
from src.services.emr import EMROAuthClient


class TestAppointmentIntegration:
    """Integration tests for appointment workflow."""

    @pytest.fixture
    def mock_oauth_client(self):
        """Create a mock OAuth client for integration tests."""
        client = Mock(spec=EMROAuthClient)
        client._get_oauth_config.return_value = {
            "fhir_base_url": "https://test-emr.com/fhir"
        }
        client.get_valid_access_token = AsyncMock(return_value="test-token")
        client.refresh_access_token = AsyncMock()
        return client

    @pytest.fixture
    def appointment_service(self, mock_oauth_client):
        """Create appointment service for integration tests."""
        return FHIRAppointmentService(mock_oauth_client)

    def get_mock_appointment_response(
        self, appointment_id: str, status: str = "booked"
    ) -> dict:
        """Get a mock appointment response."""
        return {
            "id": appointment_id,
            "resourceType": "Appointment",
            "status": status,
            "start": "2024-02-15T10:00:00Z",
            "end": "2024-02-15T10:30:00Z",
            "description": "Integration test appointment",
            "participant": [
                {
                    "actor": {"reference": "Patient/123", "display": "John Doe"},
                    "status": "accepted",
                },
                {
                    "actor": {"reference": "Practitioner/456", "display": "Dr. Smith"},
                    "status": "accepted",
                },
            ],
            "appointmentType": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0276",
                        "code": "ROUTINE",
                        "display": "Follow-up",
                    }
                ]
            },
        }

    @pytest.mark.asyncio
    async def test_complete_appointment_lifecycle(self, appointment_service):
        """Test complete appointment lifecycle: create, read, update, cancel."""

        # Mock responses for each step of the lifecycle
        create_response = self.get_mock_appointment_response("apt-integration-123")
        get_response = create_response.copy()
        update_response = create_response.copy()
        update_response["status"] = "fulfilled"
        cancel_response = create_response.copy()
        cancel_response["status"] = "cancelled"

        with patch("httpx.AsyncClient") as mock_client:
            # Setup mock responses
            mock_client_instance = mock_client.return_value.__aenter__.return_value

            # Mock the API calls sequence
            mock_client_instance.post.return_value = Mock(
                status_code=201,
                json=lambda: create_response,
                content=b'{"id": "apt-integration-123"}',
            )

            mock_client_instance.get.side_effect = [
                Mock(
                    status_code=200,
                    json=lambda: get_response,
                    content=b'{"id": "apt-integration-123"}',
                ),
                Mock(
                    status_code=200,
                    json=lambda: get_response,
                    content=b'{"id": "apt-integration-123"}',
                ),
            ]

            mock_client_instance.put.return_value = Mock(
                status_code=200,
                json=lambda: update_response,
                content=b'{"id": "apt-integration-123"}',
            )

            # Step 1: Create appointment
            created_appointment = await appointment_service.create_appointment(
                patient_reference="Patient/123",
                practitioner_reference="Practitioner/456",
                start_time="2024-02-15T10:00:00Z",
                end_time="2024-02-15T10:30:00Z",
                appointment_type="Follow-up",
                description="Integration test appointment",
            )

            assert created_appointment.id == "apt-integration-123"
            assert created_appointment.status == "booked"
            assert created_appointment.description == "Integration test appointment"

            # Step 2: Retrieve appointment
            retrieved_appointment = await appointment_service.get_appointment_by_id(
                "apt-integration-123"
            )

            assert retrieved_appointment.id == "apt-integration-123"
            assert retrieved_appointment.status == "booked"

            # Step 3: Update appointment status
            update_data = retrieved_appointment.resource.copy()
            update_data["status"] = "fulfilled"

            updated_appointment = await appointment_service.update_appointment(
                "apt-integration-123", update_data
            )

            assert updated_appointment.status == "fulfilled"

            # Step 4: Cancel appointment
            # Mock the final cancel response
            mock_client_instance.put.return_value = Mock(
                status_code=200,
                json=lambda: cancel_response,
                content=b'{"id": "apt-integration-123"}',
            )

            cancelled_appointment = await appointment_service.cancel_appointment(
                "apt-integration-123", reason="Integration test completed"
            )

            assert cancelled_appointment.status == "cancelled"

    @pytest.mark.asyncio
    async def test_multiple_appointment_types(self, appointment_service):
        """Test creating appointments with different types and providers."""

        appointment_configs = [
            {
                "id": "apt-routine-123",
                "patient": "Patient/123",
                "practitioner": "Practitioner/456",
                "type": "Routine Check-up",
                "service": "General Practice",
                "start": "2024-02-15T09:00:00Z",
                "end": "2024-02-15T09:30:00Z",
            },
            {
                "id": "apt-followup-124",
                "patient": "Patient/124",
                "practitioner": "Practitioner/457",
                "type": "Follow-up",
                "service": "Cardiology",
                "start": "2024-02-15T10:00:00Z",
                "end": "2024-02-15T10:45:00Z",
            },
            {
                "id": "apt-consultation-125",
                "patient": "Patient/125",
                "practitioner": "Practitioner/458",
                "type": "Consultation",
                "service": "Dermatology",
                "start": "2024-02-15T11:00:00Z",
                "end": "2024-02-15T11:30:00Z",
            },
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = mock_client.return_value.__aenter__.return_value

            # Mock responses for each appointment type
            responses = []
            for config in appointment_configs:
                response = self.get_mock_appointment_response(config["id"])
                response["start"] = config["start"]
                response["end"] = config["end"]
                response["participant"][0]["actor"]["reference"] = config["patient"]
                response["participant"][1]["actor"]["reference"] = config[
                    "practitioner"
                ]
                response["appointmentType"]["coding"][0]["display"] = config["type"]
                responses.append(response)

            mock_client_instance.post.side_effect = [
                Mock(status_code=201, json=lambda r=resp: r, content=b'{"id": "test"}')
                for resp in responses
            ]

            # Create appointments of different types
            created_appointments = []
            for config in appointment_configs:
                appointment = await appointment_service.create_appointment(
                    patient_reference=config["patient"],
                    practitioner_reference=config["practitioner"],
                    start_time=config["start"],
                    end_time=config["end"],
                    appointment_type=config["type"],
                    service_type=config["service"],
                )
                created_appointments.append(appointment)

            # Verify all appointments were created with correct properties
            assert len(created_appointments) == 3

            for i, appointment in enumerate(created_appointments):
                config = appointment_configs[i]
                assert appointment.get_patient_reference() == config["patient"]
                assert (
                    appointment.get_practitioner_reference() == config["practitioner"]
                )
                assert appointment.start == config["start"]
                assert appointment.end == config["end"]

    @pytest.mark.asyncio
    async def test_appointment_conflict_detection(self, appointment_service):
        """Test double-booking conflict detection."""

        # First appointment creation succeeds
        success_response = self.get_mock_appointment_response("apt-success-123")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = mock_client.return_value.__aenter__.return_value

            # First appointment succeeds
            mock_client_instance.post.side_effect = [
                Mock(
                    status_code=201,
                    json=lambda: success_response,
                    content=b'{"id": "apt-success-123"}',
                ),
                Mock(status_code=409),  # Second appointment conflicts
            ]

            # Create first appointment successfully
            first_appointment = await appointment_service.create_appointment(
                patient_reference="Patient/123",
                practitioner_reference="Practitioner/456",
                start_time="2024-02-15T10:00:00Z",
                end_time="2024-02-15T10:30:00Z",
            )

            assert first_appointment.id == "apt-success-123"

            # Attempt to create conflicting appointment (same time slot)
            with pytest.raises(AppointmentConflictError):
                await appointment_service.create_appointment(
                    patient_reference="Patient/124",
                    practitioner_reference="Practitioner/456",  # Same practitioner
                    start_time="2024-02-15T10:00:00Z",  # Same time
                    end_time="2024-02-15T10:30:00Z",
                )

    @pytest.mark.asyncio
    async def test_appointment_search_functionality(self, appointment_service):
        """Test appointment search by various criteria."""

        # Mock search response bundle
        search_response = {
            "resourceType": "Bundle",
            "total": 2,
            "entry": [
                {
                    "resource": self.get_mock_appointment_response(
                        "apt-search-1", "booked"
                    )
                },
                {
                    "resource": self.get_mock_appointment_response(
                        "apt-search-2", "fulfilled"
                    )
                },
            ],
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = mock_client.return_value.__aenter__.return_value
            mock_client_instance.get.return_value = Mock(
                status_code=200,
                json=lambda: search_response,
                content=b'{"resourceType": "Bundle"}',
            )

            # Search by patient
            results = await appointment_service.search_appointments(
                patient_reference="Patient/123"
            )

            assert len(results) == 2
            assert results[0].id == "apt-search-1"
            assert results[1].id == "apt-search-2"
            assert results[0].status == "booked"
            assert results[1].status == "fulfilled"

            # Search by practitioner and date
            results = await appointment_service.search_appointments(
                practitioner_reference="Practitioner/456",
                date="2024-02-15",
                status="booked",
            )

            # Should return same mock results
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_appointment_modification_workflow(self, appointment_service):
        """Test appointment modification scenarios."""

        original_appointment = self.get_mock_appointment_response("apt-modify-123")

        # Different modification scenarios
        time_change_response = original_appointment.copy()
        time_change_response["start"] = "2024-02-15T14:00:00Z"
        time_change_response["end"] = "2024-02-15T14:30:00Z"

        status_change_response = original_appointment.copy()
        status_change_response["status"] = "fulfilled"

        details_change_response = original_appointment.copy()
        details_change_response["description"] = "Updated: Extended consultation"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = mock_client.return_value.__aenter__.return_value

            # Mock the sequence of GET and PUT calls
            mock_client_instance.get.side_effect = [
                Mock(
                    status_code=200,
                    json=lambda: original_appointment,
                    content=b'{"id": "apt-modify-123"}',
                ),
                Mock(
                    status_code=200,
                    json=lambda: original_appointment,
                    content=b'{"id": "apt-modify-123"}',
                ),
                Mock(
                    status_code=200,
                    json=lambda: original_appointment,
                    content=b'{"id": "apt-modify-123"}',
                ),
            ]

            mock_client_instance.put.side_effect = [
                Mock(
                    status_code=200,
                    json=lambda: time_change_response,
                    content=b'{"id": "apt-modify-123"}',
                ),
                Mock(
                    status_code=200,
                    json=lambda: status_change_response,
                    content=b'{"id": "apt-modify-123"}',
                ),
                Mock(
                    status_code=200,
                    json=lambda: details_change_response,
                    content=b'{"id": "apt-modify-123"}',
                ),
            ]

            # Test 1: Time change
            appointment = await appointment_service.get_appointment_by_id(
                "apt-modify-123"
            )
            appointment_data = appointment.resource.copy()
            appointment_data["start"] = "2024-02-15T14:00:00Z"
            appointment_data["end"] = "2024-02-15T14:30:00Z"

            updated_appointment = await appointment_service.update_appointment(
                "apt-modify-123", appointment_data
            )

            assert updated_appointment.start == "2024-02-15T14:00:00Z"
            assert updated_appointment.end == "2024-02-15T14:30:00Z"

            # Test 2: Status change
            appointment = await appointment_service.get_appointment_by_id(
                "apt-modify-123"
            )
            appointment_data = appointment.resource.copy()
            appointment_data["status"] = "fulfilled"

            updated_appointment = await appointment_service.update_appointment(
                "apt-modify-123", appointment_data
            )

            assert updated_appointment.status == "fulfilled"

            # Test 3: Details modification
            appointment = await appointment_service.get_appointment_by_id(
                "apt-modify-123"
            )
            appointment_data = appointment.resource.copy()
            appointment_data["description"] = "Updated: Extended consultation"

            updated_appointment = await appointment_service.update_appointment(
                "apt-modify-123", appointment_data
            )

            assert updated_appointment.description == "Updated: Extended consultation"

    @pytest.mark.asyncio
    async def test_appointment_error_handling(self, appointment_service):
        """Test comprehensive error handling scenarios."""

        with patch("httpx.AsyncClient") as mock_client:
            mock_client_instance = mock_client.return_value.__aenter__.return_value

            # Test 1: Network timeout
            mock_client_instance.post.side_effect = httpx.TimeoutException(
                "Request timed out"
            )

            with pytest.raises(
                Exception
            ):  # Should bubble up as NetworkError after retries
                await appointment_service.create_appointment(
                    patient_reference="Patient/123",
                    practitioner_reference="Practitioner/456",
                    start_time="2024-02-15T10:00:00Z",
                    end_time="2024-02-15T10:30:00Z",
                )

            # Test 2: Appointment not found
            mock_client_instance.get.return_value = Mock(status_code=404)

            with pytest.raises(AppointmentNotFoundError):
                await appointment_service.get_appointment_by_id(
                    "nonexistent-appointment"
                )

            # Test 3: Invalid appointment data (400 error)
            mock_client_instance.post.return_value = Mock(
                status_code=400, text="Invalid appointment data"
            )

            with pytest.raises(Exception):  # Should be caught as validation error
                await appointment_service.create_appointment(
                    patient_reference="Patient/123",
                    practitioner_reference="Practitioner/456",
                    start_time="invalid-date",  # Invalid format
                    end_time="2024-02-15T10:30:00Z",
                )

    @pytest.mark.asyncio
    async def test_appointment_data_validation(self, appointment_service):
        """Test appointment data validation edge cases."""

        # Test various invalid scenarios
        invalid_scenarios = [
            {
                "name": "End time before start time",
                "patient": "Patient/123",
                "practitioner": "Practitioner/456",
                "start": "2024-02-15T10:30:00Z",
                "end": "2024-02-15T10:00:00Z",  # End before start
                "expected_error": "End time must be after start time",
            },
            {
                "name": "Invalid status",
                "patient": "Patient/123",
                "practitioner": "Practitioner/456",
                "start": "2024-02-15T10:00:00Z",
                "end": "2024-02-15T10:30:00Z",
                "status": "invalid-status",
                "expected_error": "Invalid status",
            },
            {
                "name": "Missing participant reference",
                "patient": "",  # Empty patient reference
                "practitioner": "Practitioner/456",
                "start": "2024-02-15T10:00:00Z",
                "end": "2024-02-15T10:30:00Z",
                "expected_error": "Participant must have actor reference",
            },
        ]

        for scenario in invalid_scenarios:
            with pytest.raises(
                Exception, match=scenario.get("expected_error", "validation")
            ):
                await appointment_service.create_appointment(
                    patient_reference=scenario["patient"],
                    practitioner_reference=scenario["practitioner"],
                    start_time=scenario["start"],
                    end_time=scenario["end"],
                    status=scenario.get("status", "booked"),
                )

    @pytest.mark.asyncio
    async def test_appointment_audit_logging(self, appointment_service):
        """Test that appointment operations generate proper audit logs."""

        appointment_response = self.get_mock_appointment_response("apt-audit-123")

        with patch("httpx.AsyncClient") as mock_client:
            with patch("src.services.appointment.log_audit_event") as mock_audit:
                mock_client_instance = mock_client.return_value.__aenter__.return_value
                mock_client_instance.post.return_value = Mock(
                    status_code=201,
                    json=lambda: appointment_response,
                    content=b'{"id": "apt-audit-123"}',
                )

                # Create appointment
                await appointment_service.create_appointment(
                    patient_reference="Patient/123",
                    practitioner_reference="Practitioner/456",
                    start_time="2024-02-15T10:00:00Z",
                    end_time="2024-02-15T10:30:00Z",
                )

                # Verify audit events were logged
                assert (
                    mock_audit.call_count >= 2
                )  # At least attempt and completion events

                # Check that audit events contain appropriate information
                calls = mock_audit.call_args_list
                attempt_call = calls[0]
                completion_call = calls[1]

                assert "appointment_creation_attempted" in attempt_call[0]
                assert "appointment_creation_completed" in completion_call[0]


class TestAppointmentIntegrationFailures:
    """Test integration failure scenarios and recovery."""

    @pytest.fixture
    def appointment_service_with_auth_issues(self):
        """Create appointment service with authentication issues."""
        oauth_client = Mock(spec=EMROAuthClient)
        oauth_client._get_oauth_config.return_value = {
            "fhir_base_url": "https://test-emr.com/fhir"
        }
        # Simulate authentication failure
        oauth_client.get_valid_access_token = AsyncMock(
            side_effect=Exception("Token expired")
        )
        return FHIRAppointmentService(oauth_client)

    @pytest.mark.asyncio
    async def test_authentication_failure_recovery(
        self, appointment_service_with_auth_issues
    ):
        """Test handling of authentication failures."""

        with pytest.raises(Exception, match="Failed to create appointment"):
            await appointment_service_with_auth_issues.create_appointment(
                patient_reference="Patient/123",
                practitioner_reference="Practitioner/456",
                start_time="2024-02-15T10:00:00Z",
                end_time="2024-02-15T10:30:00Z",
            )

    @pytest.mark.asyncio
    async def test_service_unavailable_scenarios(self, appointment_service):
        """Test handling when EMR service is unavailable."""

        with patch("httpx.AsyncClient") as mock_client:
            # Simulate service unavailable
            mock_client.return_value.__aenter__.return_value.post.side_effect = (
                httpx.ConnectError("Connection failed")
            )

            with pytest.raises(Exception):  # Should become NetworkError after retries
                await appointment_service.create_appointment(
                    patient_reference="Patient/123",
                    practitioner_reference="Practitioner/456",
                    start_time="2024-02-15T10:00:00Z",
                    end_time="2024-02-15T10:30:00Z",
                )


@pytest.fixture
def appointment_service():
    """Global fixture for appointment service."""
    oauth_client = Mock(spec=EMROAuthClient)
    oauth_client._get_oauth_config.return_value = {
        "fhir_base_url": "https://test-emr.com/fhir"
    }
    oauth_client.get_valid_access_token = AsyncMock(return_value="test-token")
    oauth_client.refresh_access_token = AsyncMock()
    return FHIRAppointmentService(oauth_client)
