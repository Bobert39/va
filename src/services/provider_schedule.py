"""
Provider Schedule Management Service

This module provides provider schedule and availability functionality
for OpenEMR integration with PHI protection and comprehensive error handling.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from ..audit import log_audit_event
from .emr import EMROAuthClient, NetworkError, OAuthError, TokenExpiredError

logger = logging.getLogger(__name__)


class ScheduleStatus(Enum):
    """FHIR R4 Schedule status values."""

    ACTIVE = "active"
    NOT_ACTIVE = "not-active"
    ENTERED_IN_ERROR = "entered-in-error"


class SlotStatus(Enum):
    """FHIR R4 Slot status values."""

    BUSY = "busy"
    FREE = "free"
    BUSY_UNAVAILABLE = "busy-unavailable"
    BUSY_TENTATIVE = "busy-tentative"
    ENTERED_IN_ERROR = "entered-in-error"


class ProviderScheduleError(Exception):
    """Base exception for provider schedule operations."""

    pass


class ScheduleValidationError(ProviderScheduleError):
    """Error during schedule data validation."""

    pass


class ScheduleNotFoundError(ProviderScheduleError):
    """Error when schedule is not found."""

    pass


class ProviderNotFoundError(ProviderScheduleError):
    """Error when provider is not found."""

    pass


class Schedule:
    """Represents a FHIR R4 Schedule resource."""

    def __init__(self, data: Dict[str, Any]):
        self.resource = data
        self.id = data.get("id")
        self.status = data.get("status")
        self.service_category = self._extract_service_category(data)
        self.service_type = self._extract_service_type(data)
        self.specialty = self._extract_specialty(data)
        self.actors = data.get("actor", [])
        self.planning_horizon = data.get("planningHorizon", {})
        self.comment = data.get("comment", "")

    def _extract_service_category(self, data: Dict) -> Optional[str]:
        """Extract service category from serviceCategory field."""
        categories = data.get("serviceCategory", [])
        if categories and categories[0].get("coding"):
            return categories[0]["coding"][0].get("display", "")
        return None

    def _extract_service_type(self, data: Dict) -> Optional[str]:
        """Extract service type from serviceType field."""
        service_types = data.get("serviceType", [])
        if service_types and service_types[0].get("coding"):
            return service_types[0]["coding"][0].get("display", "")
        return None

    def _extract_specialty(self, data: Dict) -> Optional[str]:
        """Extract specialty from specialty field."""
        specialties = data.get("specialty", [])
        if specialties and specialties[0].get("coding"):
            return specialties[0]["coding"][0].get("display", "")
        return None

    def get_practitioner_reference(self) -> Optional[str]:
        """Get practitioner reference from actors."""
        for actor in self.actors:
            reference = actor.get("reference", "")
            if reference.startswith("Practitioner/"):
                return reference
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "status": self.status,
            "service_category": self.service_category,
            "service_type": self.service_type,
            "specialty": self.specialty,
            "practitioner_reference": self.get_practitioner_reference(),
            "planning_horizon": self.planning_horizon,
            "comment": self.comment,
            "actors_count": len(self.actors),
        }


class Slot:
    """Represents a FHIR R4 Slot resource."""

    def __init__(self, data: Dict[str, Any]):
        self.resource = data
        self.id = data.get("id")
        self.status = data.get("status")
        self.start = data.get("start")
        self.end = data.get("end")
        self.service_category = self._extract_service_category(data)
        self.service_type = self._extract_service_type(data)
        self.schedule_reference = data.get("schedule", {}).get("reference", "")
        self.comment = data.get("comment", "")

    def _extract_service_category(self, data: Dict) -> Optional[str]:
        """Extract service category from serviceCategory field."""
        categories = data.get("serviceCategory", [])
        if categories and categories[0].get("coding"):
            return categories[0]["coding"][0].get("display", "")
        return None

    def _extract_service_type(self, data: Dict) -> Optional[str]:
        """Extract service type from serviceType field."""
        service_types = data.get("serviceType", [])
        if service_types and service_types[0].get("coding"):
            return service_types[0]["coding"][0].get("display", "")
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "status": self.status,
            "start": self.start,
            "end": self.end,
            "service_category": self.service_category,
            "service_type": self.service_type,
            "schedule_reference": self.schedule_reference,
            "comment": self.comment,
        }


class Provider:
    """Represents a FHIR R4 Practitioner resource."""

    def __init__(self, data: Dict[str, Any]):
        self.resource = data
        self.id = data.get("id")
        self.active = data.get("active", True)
        self.name = self._extract_name(data)
        self.qualification = self._extract_qualification(data)

    def _extract_name(self, data: Dict) -> str:
        """Extract practitioner name."""
        names = data.get("name", [])
        if names:
            name = names[0]
            given = " ".join(name.get("given", []))
            family = name.get("family", "")
            return f"{given} {family}".strip()
        return "Unknown Provider"

    def _extract_qualification(self, data: Dict) -> List[str]:
        """Extract qualifications."""
        qualifications = data.get("qualification", [])
        result = []
        for qual in qualifications:
            if qual.get("code", {}).get("coding"):
                result.append(qual["code"]["coding"][0].get("display", ""))
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "active": self.active,
            "name": self.name,
            "qualification": self.qualification,
        }


class ProviderScheduleService:
    """Service for FHIR R4 Schedule and Slot resource operations."""

    def __init__(self, oauth_client: EMROAuthClient):
        self.oauth_client = oauth_client
        self._config_cache: Optional[Dict[str, Any]] = None
        self._config_cache_time: float = 0
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._retry_delays = [0.5, 1.0, 2.0]  # Exponential backoff

        # Schedule data cache
        self._schedule_cache: Dict[str, List[Schedule]] = {}
        self._schedule_cache_time: Dict[str, float] = {}
        self._schedule_cache_ttl = 900  # 15 minutes cache TTL for schedules

        # Data quality tracking
        self._data_quality_issues: List[Dict[str, Any]] = []
        self._duplicate_count = 0
        self._validation_errors = 0

    def _get_oauth_config(self) -> Dict[str, Any]:
        """Get OAuth configuration with caching."""
        current_time = time.time()
        if (
            self._config_cache is None
            or current_time - self._config_cache_time > self._cache_ttl
        ):
            config = self.oauth_client._get_oauth_config()
            self._config_cache = config
            self._config_cache_time = current_time
        return self._config_cache or {}

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
        # Redact any provider-specific data in kwargs
        safe_kwargs = {}
        phi_fields = [
            "name",
            "given_name",
            "family_name",
            "id",
            "provider_id",
            "practitioner_id",
            "schedule_id",
            "slot_id",
            "comment",
            "qualification",
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
            raise ProviderScheduleError(f"Authentication failed: {e}")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }

        last_error: Optional[Exception] = None
        for attempt, delay in enumerate(self._retry_delays + [None], 1):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, params=params, headers=headers)
                    else:
                        response = await client.request(
                            method, url, json=data, headers=headers
                        )

                    # Handle authentication errors
                    if response.status_code == 401:
                        if attempt == 1:
                            # Try getting a fresh token (which includes refresh logic)
                            try:
                                access_token = (
                                    await self.oauth_client.get_valid_access_token()
                                )
                                headers["Authorization"] = f"Bearer {access_token}"
                                continue
                            except Exception:
                                pass
                        raise ProviderScheduleError(
                            "Authentication failed after token refresh"
                        )

                    # Handle specific errors
                    if response.status_code == 404:
                        if "Schedule" in endpoint or "schedule" in endpoint.lower():
                            raise ScheduleNotFoundError("Schedule not found")
                        elif (
                            "Practitioner" in endpoint
                            or "practitioner" in endpoint.lower()
                        ):
                            raise ProviderNotFoundError("Provider not found")
                        else:
                            raise ProviderScheduleError("Resource not found")
                    elif response.status_code == 400:
                        error_text = response.text
                        raise ScheduleValidationError(f"Invalid request: {error_text}")

                    response.raise_for_status()

                    # Return empty dict for responses without content
                    if response.status_code == 204 or not response.content:
                        return {}

                    return response.json()

            except (
                ScheduleNotFoundError,
                ProviderNotFoundError,
                ScheduleValidationError,
                ProviderScheduleError,
            ):
                # Don't retry these specific errors
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

    async def get_providers(self) -> List[Provider]:
        """
        Get list of active providers/practitioners.

        Returns:
            List of Provider objects

        Raises:
            ProviderScheduleError: If request fails
        """
        # Log provider access
        log_audit_event(
            "provider_list_requested",
            "FHIR provider list access requested",
            additional_data={},
        )

        try:
            # Search for active practitioners
            params = {"active": "true"}
            response = await self._make_fhir_request(
                "GET", "Practitioner", params=params
            )

            # Parse response bundle
            if response.get("resourceType") != "Bundle":
                raise ProviderScheduleError(
                    f"Expected Bundle, got {response.get('resourceType')}"
                )

            entries = response.get("entry", [])
            providers = []

            for entry in entries:
                practitioner_data = entry.get("resource", {})
                if practitioner_data.get("resourceType") == "Practitioner":
                    providers.append(Provider(practitioner_data))

            # Log successful access
            log_audit_event(
                "provider_list_completed",
                "FHIR provider list access completed",
                additional_data={"provider_count": len(providers)},
            )

            self._log_phi_safe(
                "info",
                f"Found {len(providers)} active providers",
                provider_count=len(providers),
            )

            return providers

        except (ProviderScheduleError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe("error", f"Error getting providers: {str(e)}")
            raise ProviderScheduleError(f"Failed to get providers: {str(e)}")

    async def get_provider_schedules(
        self,
        practitioner_reference: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Schedule]:
        """
        Get provider schedules for specified criteria.

        Args:
            practitioner_reference: Practitioner reference (e.g., "Practitioner/123")
            start_date: Start date for schedule lookup (ISO 8601)
            end_date: End date for schedule lookup (ISO 8601)

        Returns:
            List of Schedule objects

        Raises:
            ProviderScheduleError: If request fails
        """
        # Build cache key
        cache_key = f"{practitioner_reference}_{start_date}_{end_date}"
        current_time = time.time()

        # Check cache first
        if (
            cache_key in self._schedule_cache
            and current_time - self._schedule_cache_time.get(cache_key, 0)
            < self._schedule_cache_ttl
        ):
            self._log_phi_safe(
                "debug", "Returning cached schedule data", cache_key=cache_key
            )
            return self._schedule_cache[cache_key]

        # Log schedule access
        log_audit_event(
            "schedule_access_requested",
            "FHIR schedule access requested",
            additional_data={
                "has_practitioner": bool(practitioner_reference),
                "has_start_date": bool(start_date),
                "has_end_date": bool(end_date),
            },
        )

        try:
            # Build search parameters
            params = {"status": "active"}
            if practitioner_reference:
                params["actor"] = practitioner_reference
            if start_date and end_date:
                params["_lastUpdated"] = f"ge{start_date}&_lastUpdated=le{end_date}"

            response = await self._make_fhir_request("GET", "Schedule", params=params)

            # Parse response bundle
            if response.get("resourceType") != "Bundle":
                raise ProviderScheduleError(
                    f"Expected Bundle, got {response.get('resourceType')}"
                )

            entries = response.get("entry", [])
            schedules = []

            for entry in entries:
                schedule_data = entry.get("resource", {})
                if schedule_data.get("resourceType") == "Schedule":
                    schedules.append(Schedule(schedule_data))

            # Cache the results
            self._schedule_cache[cache_key] = schedules
            self._schedule_cache_time[cache_key] = current_time

            # Log successful access
            log_audit_event(
                "schedule_access_completed",
                "FHIR schedule access completed",
                additional_data={"schedule_count": len(schedules)},
            )

            self._log_phi_safe(
                "info",
                f"Found {len(schedules)} schedules",
                schedule_count=len(schedules),
                practitioner_ref=practitioner_reference,
            )

            return schedules

        except (ProviderScheduleError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe("error", f"Error getting schedules: {str(e)}")
            raise ProviderScheduleError(f"Failed to get schedules: {str(e)}")

    async def get_available_slots(
        self,
        schedule_reference: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: str = SlotStatus.FREE.value,
    ) -> List[Slot]:
        """
        Get available slots for specified criteria.

        Args:
            schedule_reference: Schedule reference (e.g., "Schedule/123")
            start_date: Start date for slot lookup (ISO 8601)
            end_date: End date for slot lookup (ISO 8601)
            status: Slot status to filter by (default: "free")

        Returns:
            List of Slot objects

        Raises:
            ProviderScheduleError: If request fails
        """
        # Log slot access
        log_audit_event(
            "slot_access_requested",
            "FHIR slot access requested",
            additional_data={
                "has_schedule": bool(schedule_reference),
                "has_start_date": bool(start_date),
                "has_end_date": bool(end_date),
                "status": status,
            },
        )

        try:
            # Build search parameters
            params = {"status": status}
            if schedule_reference:
                params["schedule"] = schedule_reference
            if start_date:
                params["start"] = f"ge{start_date}"
            if end_date:
                params["start"] = f"le{end_date}"

            response = await self._make_fhir_request("GET", "Slot", params=params)

            # Parse response bundle
            if response.get("resourceType") != "Bundle":
                raise ProviderScheduleError(
                    f"Expected Bundle, got {response.get('resourceType')}"
                )

            entries = response.get("entry", [])
            slots = []

            for entry in entries:
                slot_data = entry.get("resource", {})
                if slot_data.get("resourceType") == "Slot":
                    slots.append(Slot(slot_data))

            # Log successful access
            log_audit_event(
                "slot_access_completed",
                "FHIR slot access completed",
                additional_data={"slot_count": len(slots)},
            )

            self._log_phi_safe(
                "info",
                f"Found {len(slots)} available slots",
                slot_count=len(slots),
                schedule_ref=schedule_reference,
                status=status,
            )

            return slots

        except (ProviderScheduleError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe("error", f"Error getting slots: {str(e)}")
            raise ProviderScheduleError(f"Failed to get slots: {str(e)}")

    def clear_schedule_cache(self):
        """Clear the schedule data cache."""
        self._schedule_cache.clear()
        self._schedule_cache_time.clear()
        self._log_phi_safe("info", "Schedule cache cleared")

    def _validate_schedule_data(self, schedules: List[Schedule]) -> List[Schedule]:
        """
        Validate and clean schedule data for quality issues.

        Args:
            schedules: List of schedule objects to validate

        Returns:
            List of validated schedules with duplicates removed
        """
        if not schedules:
            return schedules

        # Track seen schedules to detect duplicates
        seen_schedules = set()
        validated_schedules = []
        duplicates_found = 0

        for schedule in schedules:
            # Create unique key for schedule
            schedule_key = (
                schedule.id,
                schedule.get_practitioner_reference(),
                schedule.status,
            )

            # Check for duplicates
            if schedule_key in seen_schedules:
                duplicates_found += 1
                self._data_quality_issues.append(
                    {
                        "type": "duplicate_schedule",
                        "schedule_id": schedule.id,
                        "practitioner_ref": schedule.get_practitioner_reference(),
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                continue

            # Validate schedule data
            if not self._is_valid_schedule(schedule):
                self._validation_errors += 1
                self._data_quality_issues.append(
                    {
                        "type": "invalid_schedule_data",
                        "schedule_id": schedule.id,
                        "issues": self._get_schedule_validation_issues(schedule),
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                continue

            seen_schedules.add(schedule_key)
            validated_schedules.append(schedule)

        # Update duplicate count
        self._duplicate_count += duplicates_found

        # Log data quality issues if found
        if duplicates_found > 0 or len(validated_schedules) < len(schedules):
            self._log_phi_safe(
                "warning",
                f"Data quality issues found: {duplicates_found} duplicates, "
                f"{len(schedules) - len(validated_schedules)} invalid schedules",
                duplicates=duplicates_found,
                validation_errors=len(schedules) - len(validated_schedules),
            )

        return validated_schedules

    def _is_valid_schedule(self, schedule: Schedule) -> bool:
        """Check if schedule data is valid."""
        # Check required fields
        if not schedule.id:
            return False

        if not schedule.status:
            return False

        # Check for valid practitioner reference
        practitioner_ref = schedule.get_practitioner_reference()
        if not practitioner_ref or not practitioner_ref.startswith("Practitioner/"):
            return False

        return True

    def _get_schedule_validation_issues(self, schedule: Schedule) -> List[str]:
        """Get list of validation issues for a schedule."""
        issues = []

        if not schedule.id:
            issues.append("Missing schedule ID")

        if not schedule.status:
            issues.append("Missing schedule status")

        practitioner_ref = schedule.get_practitioner_reference()
        if not practitioner_ref:
            issues.append("Missing practitioner reference")
        elif not practitioner_ref.startswith("Practitioner/"):
            issues.append("Invalid practitioner reference format")

        return issues

    def _validate_slot_data(self, slots: List[Slot]) -> List[Slot]:
        """
        Validate and clean slot data for quality issues.

        Args:
            slots: List of slot objects to validate

        Returns:
            List of validated slots
        """
        if not slots:
            return slots

        validated_slots = []

        for slot in slots:
            # Validate slot data
            if not self._is_valid_slot(slot):
                self._validation_errors += 1
                self._data_quality_issues.append(
                    {
                        "type": "invalid_slot_data",
                        "slot_id": slot.id,
                        "issues": self._get_slot_validation_issues(slot),
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                continue

            validated_slots.append(slot)

        return validated_slots

    def _is_valid_slot(self, slot: Slot) -> bool:
        """Check if slot data is valid."""
        # Check required fields
        if not slot.id or not slot.status or not slot.start or not slot.end:
            return False

        # Validate datetime format
        try:
            start_dt = datetime.fromisoformat(slot.start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(slot.end.replace("Z", "+00:00"))

            # Check that end is after start
            if end_dt <= start_dt:
                return False

        except ValueError:
            return False

        return True

    def _get_slot_validation_issues(self, slot: Slot) -> List[str]:
        """Get list of validation issues for a slot."""
        issues = []

        if not slot.id:
            issues.append("Missing slot ID")
        if not slot.status:
            issues.append("Missing slot status")
        if not slot.start:
            issues.append("Missing start time")
        if not slot.end:
            issues.append("Missing end time")

        # Validate datetime format
        try:
            if slot.start and slot.end:
                start_dt = datetime.fromisoformat(slot.start.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(slot.end.replace("Z", "+00:00"))
                if end_dt <= start_dt:
                    issues.append("End time must be after start time")
        except ValueError:
            issues.append("Invalid datetime format")

        return issues

    async def get_provider_availability(
        self,
        practitioner_reference: str,
        start_date: str,
        end_date: str,
        include_breaks: bool = True,
    ) -> Dict[str, Any]:
        """
        Get comprehensive provider availability including working hours and breaks.

        Args:
            practitioner_reference: Practitioner reference (e.g., "Practitioner/123")
            start_date: Start date (ISO 8601)
            end_date: End date (ISO 8601)
            include_breaks: Whether to identify break times

        Returns:
            Dictionary with availability data including working hours and breaks
        """
        # Get provider schedules
        schedules = await self.get_provider_schedules(
            practitioner_reference=practitioner_reference,
            start_date=start_date,
            end_date=end_date,
        )

        # Validate schedule data
        schedules = self._validate_schedule_data(schedules)

        breaks_list: Optional[List[Dict[str, Any]]] = [] if include_breaks else None
        availability_data: Dict[str, Any] = {
            "practitioner_reference": practitioner_reference,
            "period": {"start": start_date, "end": end_date},
            "schedules": [schedule.to_dict() for schedule in schedules],
            "availability_summary": {},
            "working_hours": {},
            "breaks": breaks_list,
            "data_quality": {
                "issues_found": len(self._data_quality_issues),
                "validation_errors": self._validation_errors,
                "duplicate_count": self._duplicate_count,
            },
        }

        # Get available slots for each schedule
        total_available_slots = 0
        all_working_hours = []

        for schedule in schedules:
            schedule_ref = f"Schedule/{schedule.id}"
            slots = await self.get_available_slots(
                schedule_reference=schedule_ref,
                start_date=start_date,
                end_date=end_date,
            )

            # Validate slot data
            slots = self._validate_slot_data(slots)
            total_available_slots += len(slots)

            # Extract working hours from slots
            if slots:
                working_hours = self._extract_working_hours(slots)
                all_working_hours.extend(working_hours)

                # Identify breaks if requested
                if include_breaks and breaks_list is not None:
                    breaks = self._identify_breaks(slots)
                    breaks_list.extend(breaks)

        # Summarize availability
        availability_data["availability_summary"] = {
            "total_schedules": len(schedules),
            "total_available_slots": total_available_slots,
            "has_availability": total_available_slots > 0,
        }

        # Consolidate working hours
        availability_data["working_hours"] = self._consolidate_working_hours(
            all_working_hours
        )

        return availability_data

    def _extract_working_hours(self, slots: List[Slot]) -> List[Dict[str, str]]:
        """Extract working hours from slots."""
        working_hours = []

        for slot in slots:
            if slot.start and slot.end:
                working_hours.append(
                    {
                        "start": slot.start,
                        "end": slot.end,
                        "date": slot.start[:10],  # Extract date part
                    }
                )

        return working_hours

    def _identify_breaks(self, slots: List[Slot]) -> List[Dict[str, Any]]:
        """Identify potential break times from slot gaps."""
        if len(slots) < 2:
            return []

        # Sort slots by start time
        sorted_slots = sorted(slots, key=lambda s: s.start or "")
        breaks = []

        for i in range(len(sorted_slots) - 1):
            current_slot = sorted_slots[i]
            next_slot = sorted_slots[i + 1]

            try:
                if not current_slot.end or not next_slot.start:
                    continue
                current_end = datetime.fromisoformat(
                    current_slot.end.replace("Z", "+00:00")
                )
                next_start = datetime.fromisoformat(
                    next_slot.start.replace("Z", "+00:00")
                )

                # Check for gap between slots (potential break)
                gap_duration = next_start - current_end
                if timedelta(minutes=15) <= gap_duration <= timedelta(hours=2):
                    breaks.append(
                        {
                            "start": current_slot.end,
                            "end": next_slot.start,
                            "duration_minutes": int(gap_duration.total_seconds() / 60),
                            "type": "identified_break",
                        }
                    )

            except ValueError:
                continue

        return breaks

    def _consolidate_working_hours(
        self, working_hours: List[Dict[str, str]]
    ) -> Dict[str, List[Dict[str, str]]]:
        """Consolidate working hours by date."""
        consolidated: Dict[str, List[Dict[str, str]]] = {}

        for hours in working_hours:
            date = hours["date"]
            if date not in consolidated:
                consolidated[date] = []

            consolidated[date].append({"start": hours["start"], "end": hours["end"]})

        # Sort hours by start time for each date
        for date in consolidated:
            consolidated[date].sort(key=lambda h: h["start"])

        return consolidated

    def get_data_quality_report(self) -> Dict[str, Any]:
        """Get comprehensive data quality report."""
        return {
            "total_issues": len(self._data_quality_issues),
            "duplicate_count": self._duplicate_count,
            "validation_errors": self._validation_errors,
            "recent_issues": self._data_quality_issues[-10:],  # Last 10 issues
            "issue_types": self._get_issue_type_summary(),
            "timestamp": datetime.now().isoformat(),
        }

    def _get_issue_type_summary(self) -> Dict[str, int]:
        """Get summary of issue types."""
        summary: Dict[str, int] = {}
        for issue in self._data_quality_issues:
            issue_type = issue.get("type", "unknown")
            summary[issue_type] = summary.get(issue_type, 0) + 1
        return summary

    def clear_data_quality_tracking(self):
        """Clear data quality tracking data."""
        self._data_quality_issues.clear()
        self._duplicate_count = 0
        self._validation_errors = 0

    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about current cache state."""
        current_time = time.time()
        cache_info = {
            "cache_size": len(self._schedule_cache),
            "cache_ttl": self._schedule_cache_ttl,
            "valid_entries": 0,
            "expired_entries": 0,
        }

        for key, cache_time in self._schedule_cache_time.items():
            if current_time - cache_time < self._schedule_cache_ttl:
                cache_info["valid_entries"] += 1
            else:
                cache_info["expired_entries"] += 1

        return cache_info
