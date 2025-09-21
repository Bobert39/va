"""
FHIR R4 Appointment Management Service

This module provides FHIR R4 compliant appointment management functionality
for OpenEMR integration with PHI protection and comprehensive error handling.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import httpx

from ..audit import log_audit_event
from .emr import EMROAuthClient, NetworkError, OAuthError, TokenExpiredError

logger = logging.getLogger(__name__)


class AppointmentStatus(Enum):
    """FHIR R4 Appointment status values."""

    PROPOSED = "proposed"
    PENDING = "pending"
    BOOKED = "booked"
    ARRIVED = "arrived"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    NOSHOW = "noshow"
    ENTERED_IN_ERROR = "entered-in-error"
    CHECKED_IN = "checked-in"
    WAITLIST = "waitlist"


class ParticipationStatus(Enum):
    """FHIR R4 Participation status values."""

    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"
    NEEDS_ACTION = "needs-action"


class FHIRAppointmentError(Exception):
    """Base exception for FHIR appointment operations."""

    pass


class AppointmentValidationError(FHIRAppointmentError):
    """Error during appointment data validation."""

    pass


class AppointmentConflictError(FHIRAppointmentError):
    """Error when appointment conflicts with existing appointments."""

    pass


class AppointmentNotFoundError(FHIRAppointmentError):
    """Error when appointment is not found."""

    pass


class AppointmentCreationError(FHIRAppointmentError):
    """Error during appointment creation."""

    pass


class Appointment:
    """Represents a FHIR R4 Appointment resource."""

    def __init__(self, data: Dict[str, Any]):
        self.resource = data
        self.id = data.get("id")
        self.status = data.get("status")
        self.start = data.get("start")
        self.end = data.get("end")
        self.description = data.get("description", "")
        self.comment = data.get("comment", "")
        self.participants = data.get("participant", [])
        self.appointment_type = self._extract_appointment_type(data)
        self.service_type = self._extract_service_type(data)

    def _extract_appointment_type(self, data: Dict) -> Optional[str]:
        """Extract appointment type from appointmentType field."""
        app_type = data.get("appointmentType")
        if app_type and app_type.get("coding"):
            return app_type["coding"][0].get("display", "")
        return None

    def _extract_service_type(self, data: Dict) -> Optional[str]:
        """Extract service type from serviceType field."""
        service_types = data.get("serviceType", [])
        if service_types and service_types[0].get("coding"):
            return service_types[0]["coding"][0].get("display", "")
        return None

    def get_patient_reference(self) -> Optional[str]:
        """Get patient reference from participants."""
        for participant in self.participants:
            actor = participant.get("actor", {})
            reference = actor.get("reference", "")
            if reference.startswith("Patient/"):
                return reference
        return None

    def get_practitioner_reference(self) -> Optional[str]:
        """Get practitioner reference from participants."""
        for participant in self.participants:
            actor = participant.get("actor", {})
            reference = actor.get("reference", "")
            if reference.startswith("Practitioner/"):
                return reference
        return None

    def get_patient_name(self) -> str:
        """Get patient name from participants."""
        for participant in self.participants:
            actor = participant.get("actor", {})
            reference = actor.get("reference", "")
            if reference.startswith("Patient/"):
                # Return display name if available, otherwise anonymized identifier
                display_name = actor.get("display", "")
                if display_name:
                    return display_name
                # For privacy, return anonymized patient identifier
                patient_id = reference.split("/")[-1] if "/" in reference else "Unknown"
                return f"Patient {patient_id[-4:]}"  # Last 4 chars only
        return "Unknown Patient"

    def get_provider_name(self) -> str:
        """Get provider name from participants."""
        for participant in self.participants:
            actor = participant.get("actor", {})
            reference = actor.get("reference", "")
            if reference.startswith("Practitioner/"):
                # Return display name if available
                display_name = actor.get("display", "")
                if display_name:
                    return display_name
                # Fallback to provider ID
                provider_id = (
                    reference.split("/")[-1] if "/" in reference else "Unknown"
                )
                return f"Provider {provider_id}"
        return "Unknown Provider"

    def get_time_display(self) -> str:
        """Get formatted time display for UI."""
        if not self.start or not self.end:
            return "Time TBD"

        try:
            start_dt = datetime.fromisoformat(self.start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(self.end.replace("Z", "+00:00"))

            # Format as "9:00 AM - 10:00 AM"
            start_time = start_dt.strftime("%I:%M %p").lstrip("0")
            end_time = end_dt.strftime("%I:%M %p").lstrip("0")

            return f"{start_time} - {end_time}"
        except ValueError:
            return "Time TBD"

    def get_date_display(self) -> str:
        """Get formatted date display for UI."""
        if not self.start:
            return "Date TBD"

        try:
            start_dt = datetime.fromisoformat(self.start.replace("Z", "+00:00"))
            return start_dt.strftime("%B %d, %Y")  # "January 15, 2025"
        except ValueError:
            return "Date TBD"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "status": self.status,
            "start": self.start,
            "end": self.end,
            "description": self.description,
            "comment": self.comment,
            "appointment_type": self.appointment_type,
            "service_type": self.service_type,
            "patient_reference": self.get_patient_reference(),
            "practitioner_reference": self.get_practitioner_reference(),
            "patient_name": self.get_patient_name(),
            "provider_name": self.get_provider_name(),
            "time_display": self.get_time_display(),
            "date_display": self.get_date_display(),
            "participants": len(self.participants),
        }


class FHIRAppointmentService:
    """Service for FHIR R4 Appointment resource operations."""

    def __init__(self, oauth_client: EMROAuthClient):
        self.oauth_client = oauth_client
        self._config_cache = None
        self._config_cache_time = 0
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._retry_delays = [0.5, 1.0, 2.0]  # Exponential backoff

    def _get_oauth_config(self) -> Dict[str, Any]:
        """Get OAuth configuration with caching."""
        current_time = time.time()
        if (
            self._config_cache is None
            or current_time - self._config_cache_time > self._cache_ttl
        ):
            self._config_cache = self.oauth_client._get_oauth_config()
            self._config_cache_time = current_time
        return self._config_cache

    @property
    def base_url(self) -> str:
        """Get FHIR base URL from OAuth configuration."""
        oauth_config = self._get_oauth_config()
        return oauth_config.get("fhir_base_url", "").rstrip("/")

    def _anonymize_for_logging(self, text: str) -> str:
        """Create anonymized version of text for logging."""
        if not text:
            return "[empty]"
        import hashlib

        return f"[REDACTED-{hashlib.sha256(text.encode()).hexdigest()[:8]}]"

    def _log_phi_safe(self, level: str, message: str, **kwargs):
        """Log message with PHI redacted."""
        # Redact any patient-specific data in kwargs
        safe_kwargs = {}
        phi_fields = [
            "name",
            "given_name",
            "family_name",
            "birth_date",
            "dob",
            "phone",
            "email",
            "address",
            "id",
            "patient_id",
            "appointment_id",
            "description",
            "comment",
        ]

        for key, value in kwargs.items():
            if any(field in key.lower() for field in phi_fields):
                safe_kwargs[key] = self._anonymize_for_logging(str(value))
            else:
                safe_kwargs[key] = value

        log_message = f"{message} | {safe_kwargs}" if safe_kwargs else message
        getattr(logger, level)(log_message)

    async def _make_fhir_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict:
        """Make authenticated FHIR API request with retry logic."""
        url = f"{self.base_url}/{endpoint}"

        # Get valid access token
        try:
            access_token = await self.oauth_client.get_valid_access_token()
        except (OAuthError, TokenExpiredError) as e:
            self._log_phi_safe("error", f"Authentication failed: {e}")
            raise FHIRAppointmentError(f"Authentication failed: {e}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }

        last_error = None
        for attempt, delay in enumerate(self._retry_delays + [None], 1):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    if method.upper() == "POST":
                        response = await client.post(url, json=data, headers=headers)
                    elif method.upper() == "PUT":
                        response = await client.put(url, json=data, headers=headers)
                    elif method.upper() == "DELETE":
                        response = await client.delete(url, headers=headers)
                    else:  # GET
                        response = await client.get(url, params=params, headers=headers)

                    # Handle authentication errors
                    if response.status_code == 401:
                        if attempt == 1:
                            # Try refreshing token once
                            try:
                                await self.oauth_client.refresh_access_token()
                                access_token = (
                                    await self.oauth_client.get_valid_access_token()
                                )
                                headers["Authorization"] = f"Bearer {access_token}"
                                continue
                            except Exception:
                                pass
                        raise FHIRAppointmentError(
                            "Authentication failed after token refresh"
                        )

                    # Handle specific appointment errors
                    if response.status_code == 404:
                        raise AppointmentNotFoundError("Appointment not found")
                    elif response.status_code == 409:
                        raise AppointmentConflictError("Appointment conflict detected")
                    elif response.status_code == 400:
                        error_text = response.text
                        raise AppointmentValidationError(
                            f"Invalid appointment data: {error_text}"
                        )

                    response.raise_for_status()

                    # Return empty dict for DELETE or responses without content
                    if response.status_code == 204 or not response.content:
                        return {}

                    return response.json()

            except (
                AppointmentNotFoundError,
                AppointmentConflictError,
                AppointmentValidationError,
                FHIRAppointmentError,
            ):
                # Don't retry these specific appointment errors
                raise

            except httpx.TimeoutException as e:
                last_error = e
                self._log_phi_safe(
                    "warning", f"FHIR request timeout (attempt {attempt}/4)"
                )

            except httpx.HTTPStatusError as e:
                last_error = e
                self._log_phi_safe(
                    "warning",
                    f"FHIR HTTP error (attempt {attempt}/4): {e.response.status_code}",
                )

            except Exception as e:
                last_error = e
                self._log_phi_safe(
                    "error", f"Unexpected FHIR error (attempt {attempt}/4): {str(e)}"
                )

            # Retry with backoff if not the last attempt
            if delay is not None:
                await asyncio.sleep(delay)

        # All retries exhausted
        raise NetworkError(
            f"FHIR request failed after {len(self._retry_delays) + 1} attempts: {str(last_error)}"
        )

    def _validate_appointment_data(self, appointment_data: Dict[str, Any]) -> None:
        """Validate appointment data structure."""
        required_fields = ["resourceType", "status", "start", "end", "participant"]

        for field in required_fields:
            if field not in appointment_data:
                raise AppointmentValidationError(f"Missing required field: {field}")

        # Validate resource type
        if appointment_data.get("resourceType") != "Appointment":
            raise AppointmentValidationError("resourceType must be 'Appointment'")

        # Validate status
        try:
            AppointmentStatus(appointment_data["status"])
        except ValueError:
            valid_statuses = [status.value for status in AppointmentStatus]
            raise AppointmentValidationError(
                f"Invalid status '{appointment_data['status']}'. "
                f"Valid statuses: {valid_statuses}"
            )

        # Validate datetime format
        for field in ["start", "end"]:
            try:
                datetime.fromisoformat(appointment_data[field].replace("Z", "+00:00"))
            except ValueError:
                raise AppointmentValidationError(
                    f"Invalid datetime format for {field}. Use ISO 8601 format."
                )

        # Validate that end is after start
        start_dt = datetime.fromisoformat(
            appointment_data["start"].replace("Z", "+00:00")
        )
        end_dt = datetime.fromisoformat(appointment_data["end"].replace("Z", "+00:00"))
        if end_dt <= start_dt:
            raise AppointmentValidationError("End time must be after start time")

        # Validate participants
        if not appointment_data.get("participant"):
            raise AppointmentValidationError("At least one participant is required")

        for participant in appointment_data["participant"]:
            if not participant.get("actor", {}).get("reference"):
                raise AppointmentValidationError(
                    "Participant must have actor reference"
                )

    def create_appointment_resource(
        self,
        patient_reference: str,
        practitioner_reference: str,
        start_time: str,
        end_time: str,
        status: str = AppointmentStatus.BOOKED.value,
        appointment_type: Optional[str] = None,
        service_type: Optional[str] = None,
        description: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a FHIR R4 Appointment resource structure.

        Args:
            patient_reference: Patient reference (e.g., "Patient/123")
            practitioner_reference: Practitioner reference (e.g., "Practitioner/456")
            start_time: Appointment start time (ISO 8601 format)
            end_time: Appointment end time (ISO 8601 format)
            status: Appointment status (default: "booked")
            appointment_type: Type of appointment
            service_type: Type of service
            description: Appointment description
            comment: Additional comments

        Returns:
            FHIR R4 Appointment resource dictionary
        """
        appointment = {
            "resourceType": "Appointment",
            "status": status,
            "start": start_time,
            "end": end_time,
            "participant": [
                {
                    "actor": {"reference": patient_reference},
                    "status": ParticipationStatus.ACCEPTED.value,
                },
                {
                    "actor": {"reference": practitioner_reference},
                    "status": ParticipationStatus.ACCEPTED.value,
                },
            ],
        }

        # Add optional fields
        if appointment_type:
            appointment["appointmentType"] = {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0276",
                        "code": "ROUTINE",
                        "display": appointment_type,
                    }
                ]
            }

        if service_type:
            appointment["serviceType"] = [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/service-type",
                            "code": "general",
                            "display": service_type,
                        }
                    ]
                }
            ]

        if description:
            appointment["description"] = description

        if comment:
            appointment["comment"] = comment

        return appointment

    async def create_appointment(
        self,
        patient_reference: str,
        practitioner_reference: str,
        start_time: str,
        end_time: str,
        status: str = AppointmentStatus.BOOKED.value,
        appointment_type: Optional[str] = None,
        service_type: Optional[str] = None,
        description: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Appointment:
        """
        Create a new appointment in OpenEMR.

        Args:
            patient_reference: Patient reference (e.g., "Patient/123")
            practitioner_reference: Practitioner reference (e.g., "Practitioner/456")
            start_time: Appointment start time (ISO 8601 format)
            end_time: Appointment end time (ISO 8601 format)
            status: Appointment status (default: "booked")
            appointment_type: Type of appointment
            service_type: Type of service
            description: Appointment description
            comment: Additional comments

        Returns:
            Created Appointment object

        Raises:
            AppointmentValidationError: If appointment data is invalid
            AppointmentConflictError: If appointment conflicts with existing appointments
            AppointmentCreationError: If appointment creation fails
        """
        # Create appointment resource
        appointment_data = self.create_appointment_resource(
            patient_reference=patient_reference,
            practitioner_reference=practitioner_reference,
            start_time=start_time,
            end_time=end_time,
            status=status,
            appointment_type=appointment_type,
            service_type=service_type,
            description=description,
            comment=comment,
        )

        # Validate appointment data
        self._validate_appointment_data(appointment_data)

        # Log appointment creation attempt (PHI-safe)
        log_audit_event(
            "appointment_creation_attempted",
            "FHIR appointment creation initiated",
            additional_data={
                "patient_ref": self._anonymize_for_logging(patient_reference),
                "practitioner_ref": self._anonymize_for_logging(practitioner_reference),
                "start_time": start_time,
                "status": status,
                "has_appointment_type": bool(appointment_type),
                "has_description": bool(description),
            },
        )

        try:
            # Create appointment via FHIR API
            response = await self._make_fhir_request(
                "POST", "Appointment", appointment_data
            )

            # Create Appointment object
            appointment = Appointment(response)

            # Log successful creation
            log_audit_event(
                "appointment_creation_completed",
                "FHIR appointment created successfully",
                additional_data={
                    "appointment_id": self._anonymize_for_logging(appointment.id or ""),
                    "status": appointment.status,
                    "start_time": appointment.start,
                },
            )

            self._log_phi_safe(
                "info",
                "Appointment created successfully",
                appointment_id=appointment.id,
                status=appointment.status,
            )

            return appointment

        except (FHIRAppointmentError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe(
                "error", f"Unexpected error creating appointment: {str(e)}"
            )
            raise AppointmentCreationError(f"Failed to create appointment: {str(e)}")

    async def get_appointment_by_id(self, appointment_id: str) -> Appointment:
        """
        Get an appointment by its ID.

        Args:
            appointment_id: FHIR Appointment resource ID

        Returns:
            Appointment object

        Raises:
            AppointmentNotFoundError: If appointment is not found
        """
        # Log appointment access
        log_audit_event(
            "appointment_access_requested",
            "FHIR appointment access by ID",
            additional_data={
                "appointment_id": self._anonymize_for_logging(appointment_id)
            },
        )

        try:
            response = await self._make_fhir_request(
                "GET", f"Appointment/{appointment_id}"
            )

            if response.get("resourceType") != "Appointment":
                raise FHIRAppointmentError(
                    f"Expected Appointment, got {response.get('resourceType')}"
                )

            appointment = Appointment(response)

            # Log successful access
            log_audit_event(
                "appointment_access_completed",
                "FHIR appointment access successful",
                additional_data={
                    "appointment_id": self._anonymize_for_logging(appointment_id),
                    "status": appointment.status,
                },
            )

            return appointment

        except (FHIRAppointmentError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe("error", f"Error getting appointment by ID: {str(e)}")
            raise FHIRAppointmentError(f"Failed to get appointment: {str(e)}")

    async def update_appointment(
        self, appointment_id: str, appointment_data: Dict[str, Any]
    ) -> Appointment:
        """
        Update an existing appointment.

        Args:
            appointment_id: FHIR Appointment resource ID
            appointment_data: Updated appointment data

        Returns:
            Updated Appointment object

        Raises:
            AppointmentValidationError: If appointment data is invalid
            AppointmentNotFoundError: If appointment is not found
        """
        # Ensure ID is set in the data
        appointment_data["id"] = appointment_id

        # Validate appointment data
        self._validate_appointment_data(appointment_data)

        # Log update attempt
        log_audit_event(
            "appointment_update_attempted",
            "FHIR appointment update initiated",
            additional_data={
                "appointment_id": self._anonymize_for_logging(appointment_id),
                "status": appointment_data.get("status", "unknown"),
            },
        )

        try:
            response = await self._make_fhir_request(
                "PUT", f"Appointment/{appointment_id}", appointment_data
            )

            appointment = Appointment(response)

            # Log successful update
            log_audit_event(
                "appointment_update_completed",
                "FHIR appointment updated successfully",
                additional_data={
                    "appointment_id": self._anonymize_for_logging(appointment_id),
                    "status": appointment.status,
                },
            )

            self._log_phi_safe(
                "info",
                "Appointment updated successfully",
                appointment_id=appointment_id,
                status=appointment.status,
            )

            return appointment

        except (FHIRAppointmentError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe("error", f"Error updating appointment: {str(e)}")
            raise FHIRAppointmentError(f"Failed to update appointment: {str(e)}")

    async def cancel_appointment(
        self, appointment_id: str, reason: Optional[str] = None
    ) -> Appointment:
        """
        Cancel an appointment by setting status to 'cancelled'.

        Args:
            appointment_id: FHIR Appointment resource ID
            reason: Optional cancellation reason

        Returns:
            Updated Appointment object with cancelled status

        Raises:
            AppointmentNotFoundError: If appointment is not found
        """
        # Get current appointment
        appointment = await self.get_appointment_by_id(appointment_id)

        # Update status to cancelled
        appointment_data = appointment.resource.copy()
        appointment_data["status"] = AppointmentStatus.CANCELLED.value

        if reason:
            appointment_data["comment"] = reason

        # Log cancellation attempt
        log_audit_event(
            "appointment_cancellation_attempted",
            "FHIR appointment cancellation initiated",
            additional_data={
                "appointment_id": self._anonymize_for_logging(appointment_id),
                "has_reason": bool(reason),
            },
        )

        # Update the appointment
        cancelled_appointment = await self.update_appointment(
            appointment_id, appointment_data
        )

        # Log successful cancellation
        log_audit_event(
            "appointment_cancellation_completed",
            "FHIR appointment cancelled successfully",
            additional_data={
                "appointment_id": self._anonymize_for_logging(appointment_id)
            },
        )

        return cancelled_appointment

    async def search_appointments(
        self,
        patient_reference: Optional[str] = None,
        practitioner_reference: Optional[str] = None,
        date: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Appointment]:
        """
        Search for appointments by criteria.

        Args:
            patient_reference: Patient reference to filter by
            practitioner_reference: Practitioner reference to filter by
            date: Date to filter by (YYYY-MM-DD format)
            status: Status to filter by

        Returns:
            List of matching Appointment objects
        """
        # Build search parameters
        params = {}
        if patient_reference:
            params["patient"] = patient_reference
        if practitioner_reference:
            params["practitioner"] = practitioner_reference
        if date:
            params["date"] = date
        if status:
            params["status"] = status

        # Log search attempt
        log_audit_event(
            "appointment_search_requested",
            "FHIR appointment search initiated",
            additional_data={
                "has_patient": bool(patient_reference),
                "has_practitioner": bool(practitioner_reference),
                "has_date": bool(date),
                "has_status": bool(status),
            },
        )

        try:
            response = await self._make_fhir_request(
                "GET", "Appointment", params=params
            )

            # Parse response bundle
            if response.get("resourceType") != "Bundle":
                raise FHIRAppointmentError(
                    f"Expected Bundle, got {response.get('resourceType')}"
                )

            entries = response.get("entry", [])
            appointments = []

            for entry in entries:
                appointment_data = entry.get("resource", {})
                if appointment_data.get("resourceType") == "Appointment":
                    appointments.append(Appointment(appointment_data))

            # Log search results
            log_audit_event(
                "appointment_search_completed",
                "FHIR appointment search completed",
                additional_data={"result_count": len(appointments)},
            )

            self._log_phi_safe(
                "info",
                f"Found {len(appointments)} appointments",
                result_count=len(appointments),
            )

            return appointments

        except (FHIRAppointmentError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe("error", f"Error searching appointments: {str(e)}")
            raise FHIRAppointmentError(f"Failed to search appointments: {str(e)}")

    async def get_appointments_today(self) -> List[Appointment]:
        """
        Get today's appointments.

        Returns:
            List of Appointment objects for today

        Raises:
            FHIRAppointmentError: If request fails
        """
        today = datetime.now().date()
        date_str = today.isoformat()

        return await self.search_appointments(date=date_str)

    async def get_appointments_by_date_range(
        self,
        start_date: str,
        end_date: str,
        practitioner_reference: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Appointment]:
        """
        Get appointments within a date range.

        Args:
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            practitioner_reference: Optional provider filter
            status: Optional status filter

        Returns:
            List of Appointment objects within the date range

        Raises:
            FHIRAppointmentError: If request fails
        """
        # Build search parameters with date range
        params = {}
        params["date"] = f"ge{start_date}&date=le{end_date}"

        if practitioner_reference:
            params["practitioner"] = practitioner_reference
        if status:
            params["status"] = status

        # Log search attempt
        log_audit_event(
            "appointment_date_range_search_requested",
            "FHIR appointment date range search initiated",
            additional_data={
                "start_date": start_date,
                "end_date": end_date,
                "has_practitioner": bool(practitioner_reference),
                "has_status": bool(status),
            },
        )

        try:
            response = await self._make_fhir_request(
                "GET", "Appointment", params=params
            )

            # Parse response bundle
            if response.get("resourceType") != "Bundle":
                raise FHIRAppointmentError(
                    f"Expected Bundle, got {response.get('resourceType')}"
                )

            entries = response.get("entry", [])
            appointments = []

            for entry in entries:
                appointment_data = entry.get("resource", {})
                if appointment_data.get("resourceType") == "Appointment":
                    appointment = Appointment(appointment_data)
                    # Additional date filtering for edge cases
                    if appointment.start:
                        appointment_date = appointment.start[:10]  # Extract date part
                        if start_date <= appointment_date <= end_date:
                            appointments.append(appointment)

            # Sort by start time
            appointments.sort(key=lambda a: a.start or "")

            # Log search results
            log_audit_event(
                "appointment_date_range_search_completed",
                "FHIR appointment date range search completed",
                additional_data={
                    "result_count": len(appointments),
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )

            self._log_phi_safe(
                "info",
                f"Found {len(appointments)} appointments in date range",
                result_count=len(appointments),
                start_date=start_date,
                end_date=end_date,
            )

            return appointments

        except (FHIRAppointmentError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe(
                "error", f"Error getting appointments by date range: {str(e)}"
            )
            raise FHIRAppointmentError(
                f"Failed to get appointments by date range: {str(e)}"
            )
