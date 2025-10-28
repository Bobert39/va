"""
Pytest configuration and fixtures for Voice AI Platform tests.

This module sets up the test environment, including environment variables
and common fixtures used across all test modules.
"""

import os
import sys
from pathlib import Path

import pytest

# Add src directory to Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


# Set environment variables for testing BEFORE any imports that need them
def pytest_configure(config):
    """
    Configure pytest and set environment variables needed for testing.

    This runs before any tests are collected or executed.
    """
    # Allow dev defaults for testing
    os.environ["ALLOW_DEV_DEFAULTS"] = "true"

    # Set test credentials
    os.environ["DASHBOARD_USERNAME"] = "test_user"
    os.environ["DASHBOARD_PASSWORD"] = "test_password_123"

    # Set other required environment variables for testing
    os.environ.setdefault("OPENAI_API_KEY", "test-key-12345")
    os.environ.setdefault("TWILIO_ACCOUNT_SID", "test-twilio-sid")
    os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-twilio-token")
    os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15555551234")

    # EMR configuration
    os.environ.setdefault("EMR_BASE_URL", "https://test-emr.example.com")
    os.environ.setdefault("EMR_CLIENT_ID", "test-client-id")
    os.environ.setdefault("EMR_CLIENT_SECRET", "test-client-secret")

    # Practice settings
    os.environ.setdefault("PRACTICE_NAME", "Test Medical Practice")
    os.environ.setdefault("PRACTICE_TIMEZONE", "America/New_York")


@pytest.fixture
def test_env():
    """Fixture to provide test environment variables."""
    return {
        "DASHBOARD_USERNAME": os.environ.get("DASHBOARD_USERNAME"),
        "DASHBOARD_PASSWORD": os.environ.get("DASHBOARD_PASSWORD"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "ALLOW_DEV_DEFAULTS": os.environ.get("ALLOW_DEV_DEFAULTS"),
    }


@pytest.fixture
def mock_openai_response():
    """Fixture for mocking OpenAI API responses."""
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Test response from GPT-4"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }


@pytest.fixture
def mock_patient_data():
    """Fixture for mock FHIR patient data."""
    return {
        "resourceType": "Patient",
        "id": "test-patient-123",
        "name": [
            {
                "use": "official",
                "family": "Smith",
                "given": ["John"]
            }
        ],
        "telecom": [
            {
                "system": "phone",
                "value": "+15555551234",
                "use": "mobile"
            }
        ],
        "gender": "male",
        "birthDate": "1980-01-15"
    }


@pytest.fixture
def mock_appointment_data():
    """Fixture for mock FHIR appointment data."""
    return {
        "resourceType": "Appointment",
        "id": "test-appointment-123",
        "status": "booked",
        "description": "Routine checkup",
        "start": "2025-11-01T10:00:00Z",
        "end": "2025-11-01T10:30:00Z",
        "participant": [
            {
                "actor": {
                    "reference": "Patient/test-patient-123",
                    "display": "John Smith"
                },
                "status": "accepted"
            }
        ]
    }
