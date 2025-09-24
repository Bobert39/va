"""
Appointment Creator Service for OpenEMR integration.

Handles appointment creation with robust error handling, retry logic,
and comprehensive audit trail for HIPAA compliance.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..audit import SecurityAndAuditService
from ..config import get_config

logger = logging.getLogger(__name__)


class AppointmentStatus(Enum):
    """Appointment creation status enum."""

    CREATED = "created"
    FAILED = "failed"
    PENDING_RETRY = "pending_retry"
    VALIDATION_ERROR = "validation_error"


class CircuitBreakerState(Enum):
    """Circuit breaker states for EMR availability."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures detected, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class AppointmentCreationError(Exception):
    """Base exception for appointment creation errors."""

    pass


class ValidationError(AppointmentCreationError):
    """Appointment data validation error."""

    pass


class EMRConnectionError(AppointmentCreationError):
    """EMR connection or API error."""

    pass


class CircuitBreakerOpen(AppointmentCreationError):
    """Circuit breaker is open, EMR unavailable."""

    pass


class AppointmentCreator:
    """
    Service for creating appointments in OpenEMR with robust error handling.

    Implements:
    - Retry logic with exponential backoff
    - Circuit breaker pattern for EMR availability
    - Data validation and mapping
    - Comprehensive audit logging
    """

    def __init__(
        self, emr_client=None, audit_service: Optional[SecurityAndAuditService] = None
    ):
        """
        Initialize appointment creator service.

        Args:
            emr_client: EMR OAuth client instance
            audit_service: Audit service for logging
        """
        self.emr_client = emr_client
        self.audit_service = audit_service or SecurityAndAuditService()

        # Retry configuration
        config = get_config("emr_integration", {})
        retry_config = config.get("retry_configuration", {})
        self.max_retry_attempts = retry_config.get("max_attempts", 3)
        self.initial_delay = retry_config.get("initial_delay_seconds", 1)
        self.backoff_multiplier = retry_config.get("backoff_multiplier", 2)
        self.max_delay = retry_config.get("max_delay_seconds", 30)

        # Circuit breaker configuration
        circuit_config = config.get("circuit_breaker", {})
        self.failure_threshold = circuit_config.get("failure_threshold", 5)
        self.recovery_timeout = circuit_config.get("recovery_timeout_seconds", 60)
        self.half_open_max_calls = circuit_config.get("half_open_max_calls", 3)

        # Circuit breaker state
        self.circuit_state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

        # API endpoint
        self.appointment_endpoint = config.get(
            "appointment_api_endpoint", "/api/appointments"
        )

    def validate_appointment_data(
        self, appointment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate and normalize appointment data.

        Args:
            appointment_data: Raw appointment data

        Returns:
            Validated and normalized appointment data

        Raises:
            ValidationError: If data validation fails
        """
        required_fields = [
            "patient_id",
            "provider_id",
            "start_time",
            "appointment_type",
            "duration_minutes",
        ]

        # Check required fields
        missing_fields = [f for f in required_fields if f not in appointment_data]
        if missing_fields:
            raise ValidationError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )

        # Validate patient ID
        if not appointment_data["patient_id"]:
            raise ValidationError("Patient ID cannot be empty")

        # Validate provider ID
        if not appointment_data["provider_id"]:
            raise ValidationError("Provider ID cannot be empty")

        # Validate start time
        try:
            start_time = appointment_data["start_time"]
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time)
            appointment_data["start_time"] = start_time
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid start_time format: {e}")

        # Validate duration
        duration = appointment_data["duration_minutes"]
        if not isinstance(duration, int) or duration <= 0:
            raise ValidationError(f"Invalid duration: {duration}")

        # Calculate end time
        appointment_data["end_time"] = start_time + timedelta(minutes=duration)

        # Set defaults for optional fields
        appointment_data.setdefault("reason", "")
        appointment_data.setdefault("notes", "")
        appointment_data.setdefault("status", "scheduled")

        return appointment_data

    def map_to_emr_format(self, appointment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map appointment data to OpenEMR API format.

        Args:
            appointment_data: Validated appointment data

        Returns:
            EMR-formatted appointment data
        """
        # OpenEMR appointment format
        emr_appointment = {
            "pc_pid": appointment_data["patient_id"],
            "pc_aid": appointment_data["provider_id"],
            "pc_eventDate": appointment_data["start_time"].strftime("%Y-%m-%d"),
            "pc_startTime": appointment_data["start_time"].strftime("%H:%M:00"),
            "pc_endTime": appointment_data["end_time"].strftime("%H:%M:00"),
            "pc_duration": appointment_data["duration_minutes"]
            * 60,  # OpenEMR uses seconds
            "pc_catid": self._map_appointment_type(
                appointment_data["appointment_type"]
            ),
            "pc_title": appointment_data.get("reason", "Appointment"),
            "pc_hometext": appointment_data.get("notes", ""),
            "pc_apptstatus": appointment_data.get("status", "scheduled"),
            "pc_facility": appointment_data.get("facility_id", "1"),  # Default facility
        }

        return emr_appointment

    def _map_appointment_type(self, appointment_type: str) -> str:
        """
        Map appointment type to OpenEMR category ID.

        Args:
            appointment_type: Appointment type string

        Returns:
            OpenEMR category ID
        """
        # Map common appointment types to OpenEMR categories
        type_mapping = {
            "new_patient": "5",
            "follow_up": "9",
            "routine": "10",
            "urgent": "11",
            "physical": "12",
            "consultation": "13",
            "procedure": "14",
            "lab": "15",
            "imaging": "16",
            "vaccination": "17",
            "telehealth": "18",
            "default": "9",  # Default to follow-up
        }

        return type_mapping.get(appointment_type.lower(), type_mapping["default"])

    async def check_circuit_breaker(self) -> bool:
        """
        Check circuit breaker state and update if necessary.

        Returns:
            True if requests can proceed, False if circuit is open
        """
        if self.circuit_state == CircuitBreakerState.CLOSED:
            return True

        if self.circuit_state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                time_since_failure = (
                    datetime.utcnow() - self.last_failure_time
                ).total_seconds()
                if time_since_failure >= self.recovery_timeout:
                    logger.info("Circuit breaker moving to HALF_OPEN state")
                    self.circuit_state = CircuitBreakerState.HALF_OPEN
                    self.half_open_calls = 0
                    return True
            return False

        if self.circuit_state == CircuitBreakerState.HALF_OPEN:
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        return False

    def record_success(self):
        """Record successful API call."""
        if self.circuit_state == CircuitBreakerState.HALF_OPEN:
            logger.info("Circuit breaker recovering, moving to CLOSED state")
            self.circuit_state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.last_failure_time = None

    def record_failure(self):
        """Record failed API call and update circuit breaker."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        if self.circuit_state == CircuitBreakerState.HALF_OPEN:
            logger.warning("Circuit breaker test failed, moving back to OPEN state")
            self.circuit_state = CircuitBreakerState.OPEN
        elif self.failure_count >= self.failure_threshold:
            logger.error(f"Circuit breaker opening after {self.failure_count} failures")
            self.circuit_state = CircuitBreakerState.OPEN

    async def create_appointment_with_retry(
        self, appointment_data: Dict[str, Any], session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create appointment with retry logic and circuit breaker.

        Args:
            appointment_data: Appointment data to create
            session_id: Optional session ID for audit trail

        Returns:
            Creation result with appointment details

        Raises:
            AppointmentCreationError: If creation fails after all retries
        """
        # Validate appointment data
        try:
            validated_data = self.validate_appointment_data(appointment_data)
            emr_data = self.map_to_emr_format(validated_data)
        except ValidationError as e:
            self.audit_service.log_appointment_event(
                event_type="appointment_creation_validation_error",
                session_id=session_id,
                details={"error": str(e), "data": appointment_data},
            )
            return {
                "status": AppointmentStatus.VALIDATION_ERROR.value,
                "error": str(e),
                "appointment_data": appointment_data,
            }

        attempt = 0
        last_error = None
        delay = self.initial_delay

        while attempt < self.max_retry_attempts:
            attempt += 1

            # Check circuit breaker
            if not await self.check_circuit_breaker():
                self.audit_service.log_appointment_event(
                    event_type="appointment_creation_circuit_open",
                    session_id=session_id,
                    details={"attempt": attempt, "state": self.circuit_state.value},
                )

                if attempt == self.max_retry_attempts:
                    raise CircuitBreakerOpen(
                        "EMR service unavailable, circuit breaker open"
                    )

                # Wait before next attempt
                await asyncio.sleep(delay)
                delay = min(delay * self.backoff_multiplier, self.max_delay)
                continue

            try:
                # Attempt to create appointment
                result = await self._create_appointment_api_call(emr_data, session_id)

                # Record success
                self.record_success()

                # Log successful creation
                self.audit_service.log_appointment_event(
                    event_type="appointment_created",
                    session_id=session_id,
                    details={
                        "appointment_id": result.get("id"),
                        "patient_id": validated_data["patient_id"],
                        "provider_id": validated_data["provider_id"],
                        "start_time": validated_data["start_time"].isoformat(),
                        "attempt": attempt,
                    },
                )

                return {
                    "status": AppointmentStatus.CREATED.value,
                    "emr_appointment_id": result.get("id"),
                    "appointment_data": validated_data,
                    "retry_count": attempt - 1,
                }

            except Exception as e:
                last_error = e
                self.record_failure()

                # Log failure attempt
                self.audit_service.log_appointment_event(
                    event_type="appointment_creation_attempt_failed",
                    session_id=session_id,
                    details={
                        "attempt": attempt,
                        "error": str(e),
                        "patient_id": validated_data["patient_id"],
                        "provider_id": validated_data["provider_id"],
                    },
                )

                if attempt < self.max_retry_attempts:
                    logger.warning(
                        f"Appointment creation attempt {attempt} failed: {e}"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * self.backoff_multiplier, self.max_delay)
                else:
                    logger.error(f"All appointment creation attempts failed: {e}")

        # All retries exhausted
        self.audit_service.log_appointment_event(
            event_type="appointment_creation_failed",
            session_id=session_id,
            details={
                "error": str(last_error),
                "retry_count": attempt,
                "patient_id": validated_data["patient_id"],
                "provider_id": validated_data["provider_id"],
            },
        )

        return {
            "status": AppointmentStatus.FAILED.value,
            "error": str(last_error),
            "appointment_data": validated_data,
            "retry_count": attempt,
        }

    async def _create_appointment_api_call(
        self, emr_data: Dict[str, Any], session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Make actual API call to create appointment in EMR.

        Args:
            emr_data: EMR-formatted appointment data
            session_id: Optional session ID for logging

        Returns:
            API response with created appointment details

        Raises:
            EMRConnectionError: If API call fails
        """
        if not self.emr_client:
            raise EMRConnectionError("EMR client not configured")

        try:
            # Get valid access token
            access_token = await self.emr_client.ensure_valid_token()

            # Prepare request
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            # Get EMR base URL
            config = get_config("emr_integration", {})
            base_url = config.get("base_url", "")

            if not base_url:
                raise EMRConnectionError("EMR base URL not configured")

            # Make API request
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{base_url}{self.appointment_endpoint}",
                    json=emr_data,
                    headers=headers,
                )

                if response.status_code == 201:
                    return response.json()
                elif response.status_code == 401:
                    raise EMRConnectionError("Authentication failed")
                elif response.status_code == 400:
                    error_detail = response.json() if response.content else {}
                    raise ValidationError(f"Invalid appointment data: {error_detail}")
                else:
                    raise EMRConnectionError(
                        f"API request failed with status {response.status_code}: {response.text}"
                    )

        except httpx.RequestError as e:
            raise EMRConnectionError(f"Network error: {e}")
        except Exception as e:
            if isinstance(e, (EMRConnectionError, ValidationError)):
                raise
            raise EMRConnectionError(f"Unexpected error: {e}")

    async def get_fallback_data(
        self, appointment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate fallback data when EMR is unavailable.

        Args:
            appointment_data: Original appointment request data

        Returns:
            Fallback appointment data for graceful degradation
        """
        return {
            "status": AppointmentStatus.PENDING_RETRY.value,
            "fallback": True,
            "appointment_data": appointment_data,
            "message": "Appointment will be created when EMR becomes available",
            "retry_after": datetime.utcnow() + timedelta(seconds=self.recovery_timeout),
        }
