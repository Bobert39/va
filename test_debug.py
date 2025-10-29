#!/usr/bin/env python3
"""Debug script to see actual error"""
import os
import traceback
import logging
from unittest.mock import AsyncMock, Mock

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Set environment variables
os.environ["ALLOW_DEV_DEFAULTS"] = "true"
os.environ["DASHBOARD_USERNAME"] = "test_user"
os.environ["DASHBOARD_PASSWORD"] = "test_password_123"

# Import app and dependencies
from src.main import (
    app,
    get_appointment_service,
    get_oauth_client,
    get_patient_service,
    get_provider_schedule_service,
)
from src.services.appointment import FHIRAppointmentService, Appointment
from fastapi.testclient import TestClient

# Create mocks
mock_appointment_service = Mock(spec=FHIRAppointmentService)
sample_appointment = Appointment({
    "id": "appointment-123",
    "status": "booked",
    "start": "2025-09-21T09:00:00Z",
    "end": "2025-09-21T10:00:00Z",
    "description": "Regular checkup",
    "participant": [
        {"actor": {"reference": "Patient/456", "display": "John Doe"}},
        {"actor": {"reference": "Practitioner/789", "display": "Dr. Smith"}},
    ],
})
mock_appointment_service.get_appointments_today = AsyncMock(return_value=[sample_appointment])

# Set up dependency overrides
app.dependency_overrides[get_appointment_service] = lambda: mock_appointment_service

# Create client and make request with raise_server_exceptions to see the actual error
try:
    client = TestClient(app, raise_server_exceptions=True)
    response = client.get("/api/v1/appointments/today")

    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    print(f"\nFull Response Text: {response.text}")
except Exception as e:
    print(f"Exception occurred: {e}")
    traceback.print_exc()
