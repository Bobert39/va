#!/usr/bin/env python3
"""Debug script to see actual error"""
import os
from unittest.mock import AsyncMock, Mock, patch

# Set environment variables
os.environ["ALLOW_DEV_DEFAULTS"] = "true"
os.environ["DASHBOARD_USERNAME"] = "test_user"
os.environ["DASHBOARD_PASSWORD"] = "test_password_123"

# Patch audit logger before importing main
with patch("src.audit.audit_logger"):
    from src.main import (
        app,
        get_appointment_service,
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

    # Remove SlowAPIMiddleware
    app.user_middleware = [m for m in app.user_middleware if m.cls.__name__ != "SlowAPIMiddleware"]
    app.middleware_stack = None
    app.build_middleware_stack()

    # Create client WITHOUT raise_server_exceptions to get response
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/appointments/today")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

    # Now test with mock verification
    print(f"\nMock called: {mock_appointment_service.get_appointments_today.called}")
    print(f"Mock call count: {mock_appointment_service.get_appointments_today.call_count}")
