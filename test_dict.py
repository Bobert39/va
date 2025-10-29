#!/usr/bin/env python3
"""Test appointment to_dict conversion"""
from src.services.appointment import Appointment

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

print("Appointment created successfully")
try:
    result = sample_appointment.to_dict()
    print("to_dict() result:")
    print(result)
except Exception as e:
    import traceback
    print(f"Error in to_dict(): {e}")
    traceback.print_exc()
