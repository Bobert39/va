"""
Schedule Conflict Detection Service

This module provides real-time schedule conflict detection and resolution
for preventing double-booking and managing appointment scheduling conflicts.
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List

from ..audit import log_audit_event
from .emr import EMROAuthClient
from .provider_schedule import ProviderScheduleService, SlotStatus

logger = logging.getLogger(__name__)


class ConflictType(Enum):
    """Types of scheduling conflicts."""

    EXISTING_APPOINTMENT = "existing_appointment"
    BUFFER_TIME = "buffer_time"
    BREAK_TIME = "break_time"
    HOLIDAY = "holiday"
    OPERATIONAL_HOURS = "operational_hours"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class ConflictSeverity(Enum):
    """Severity levels for conflicts."""

    BLOCKING = "blocking"  # Cannot schedule appointment
    WARNING = "warning"  # Can schedule but not recommended


class ConflictDetectorError(Exception):
    """Base exception for conflict detection operations."""

    pass


class ScheduleConflictError(ConflictDetectorError):
    """Error during schedule conflict detection."""

    pass


class ConflictDetector:
    """
    Service for detecting and resolving appointment scheduling conflicts.

    Provides real-time conflict detection to prevent double-booking and
    ensure proper appointment scheduling according to practice rules.
    """

    def __init__(
        self,
        emr_client: EMROAuthClient,
        schedule_service: ProviderScheduleService,
        config: Dict[str, Any],
    ):
        """
        Initialize conflict detector.

        Args:
            emr_client: EMR OAuth client for API access
            schedule_service: Provider schedule service
            config: Configuration including scheduling rules
        """
        self.emr_client = emr_client
        self.schedule_service = schedule_service
        self.config = config
        self.scheduling_rules = config.get("scheduling_rules", {})

        # Default buffer time if not configured
        self.default_buffer_minutes = self.scheduling_rules.get(
            "default_buffer_minutes", 15
        )

    async def check_conflicts(
        self,
        provider_id: str,
        start_time: datetime,
        end_time: datetime,
        appointment_type: str = "standard",
    ) -> Dict[str, Any]:
        """
        Check for scheduling conflicts for a proposed appointment.

        Args:
            provider_id: Provider identifier
            start_time: Proposed appointment start time
            end_time: Proposed appointment end time
            appointment_type: Type of appointment (for specific rules)

        Returns:
            Dict containing conflicts and alternative suggestions

        Raises:
            ScheduleConflictError: If conflict detection fails
        """
        try:
            # Log conflict check request (anonymized)
            await log_audit_event(
                "conflict_check_requested",
                {
                    "provider_id_hash": self._hash_identifier(provider_id),
                    "start_time": start_time.isoformat(),
                    "duration_minutes": int(
                        (end_time - start_time).total_seconds() / 60
                    ),
                    "appointment_type": appointment_type,
                },
            )

            conflicts = []

            # Check existing appointments
            existing_conflicts = await self._check_existing_appointments(
                provider_id, start_time, end_time
            )
            conflicts.extend(existing_conflicts)

            # Check buffer time conflicts
            buffer_conflicts = await self._check_buffer_time_conflicts(
                provider_id, start_time, end_time, appointment_type
            )
            conflicts.extend(buffer_conflicts)

            # Check operational hours
            hours_conflicts = await self._check_operational_hours(
                provider_id, start_time, end_time
            )
            conflicts.extend(hours_conflicts)

            # Check holidays and breaks
            break_conflicts = await self._check_breaks_and_holidays(
                provider_id, start_time, end_time
            )
            conflicts.extend(break_conflicts)

            # Check provider-specific rules
            provider_conflicts = await self._check_provider_rules(
                provider_id, start_time, end_time, appointment_type
            )
            conflicts.extend(provider_conflicts)

            # Determine if any blocking conflicts exist
            has_blocking_conflicts = any(
                conflict["severity"] == ConflictSeverity.BLOCKING.value
                for conflict in conflicts
            )

            # Generate alternative suggestions if conflicts exist
            alternatives = []
            if conflicts:
                alternatives = await self._generate_alternative_times(
                    provider_id, start_time, end_time, appointment_type
                )

            result = {
                "has_conflicts": len(conflicts) > 0,
                "has_blocking_conflicts": has_blocking_conflicts,
                "conflicts": conflicts,
                "alternative_suggestions": alternatives,
                "can_schedule": not has_blocking_conflicts,
            }

            # Log conflict check result
            await log_audit_event(
                "conflict_check_completed",
                {
                    "provider_id_hash": self._hash_identifier(provider_id),
                    "conflicts_found": len(conflicts),
                    "blocking_conflicts": has_blocking_conflicts,
                    "can_schedule": not has_blocking_conflicts,
                    "alternatives_suggested": len(alternatives),
                },
            )

            return result

        except Exception as e:
            logger.error(f"Conflict detection failed: {str(e)}")
            await log_audit_event(
                "conflict_check_error",
                {
                    "provider_id_hash": self._hash_identifier(provider_id),
                    "error": str(e),
                },
            )
            raise ScheduleConflictError(f"Failed to check conflicts: {str(e)}")

    async def _check_existing_appointments(
        self, provider_id: str, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Check for conflicts with existing appointments."""
        conflicts = []

        try:
            # Get provider's schedule for the day
            date = start_time.date()
            schedules = await self.schedule_service.get_provider_schedules(
                provider_id, date, date
            )
            schedule = schedules[0] if schedules else {"slots": []}

            # Check each slot for conflicts
            for slot in schedule.get("slots", []):
                slot_start = datetime.fromisoformat(slot["start"])
                slot_end = datetime.fromisoformat(slot["end"])

                # Skip free slots
                if slot.get("status") == SlotStatus.FREE.value:
                    continue

                # Check for time overlap
                if self._times_overlap(start_time, end_time, slot_start, slot_end):
                    conflicts.append(
                        {
                            "conflict_type": ConflictType.EXISTING_APPOINTMENT.value,
                            "conflicting_appointment_id": slot.get("appointment_id"),
                            "conflict_start": slot_start.isoformat(),
                            "conflict_end": slot_end.isoformat(),
                            "severity": ConflictSeverity.BLOCKING.value,
                            "description": f"Existing appointment from {slot_start.strftime('%H:%M')} to {slot_end.strftime('%H:%M')}",
                        }
                    )

        except Exception as e:
            logger.warning(f"Failed to check existing appointments: {str(e)}")
            # Don't fail the entire conflict check, but log the issue

        return conflicts

    async def _check_buffer_time_conflicts(
        self,
        provider_id: str,
        start_time: datetime,
        end_time: datetime,
        appointment_type: str,
    ) -> List[Dict[str, Any]]:
        """Check for buffer time conflicts with adjacent appointments."""
        conflicts = []

        try:
            # Get buffer time for this appointment type
            buffer_minutes = self._get_buffer_time(provider_id, appointment_type)
            buffer_delta = timedelta(minutes=buffer_minutes)

            # Check for appointments within buffer time
            buffer_start = start_time - buffer_delta
            buffer_end = end_time + buffer_delta

            date = start_time.date()
            schedules = await self.schedule_service.get_provider_schedules(
                provider_id, date, date
            )
            schedule = schedules[0] if schedules else {"slots": []}

            for slot in schedule.get("slots", []):
                if slot.get("status") == SlotStatus.FREE.value:
                    continue

                slot_start = datetime.fromisoformat(slot["start"])
                slot_end = datetime.fromisoformat(slot["end"])

                # Check if adjacent appointment violates buffer time
                if (slot_end > buffer_start and slot_end <= start_time) or (
                    slot_start >= end_time and slot_start < buffer_end
                ):
                    conflicts.append(
                        {
                            "conflict_type": ConflictType.BUFFER_TIME.value,
                            "conflicting_appointment_id": slot.get("appointment_id"),
                            "conflict_start": slot_start.isoformat(),
                            "conflict_end": slot_end.isoformat(),
                            "severity": ConflictSeverity.WARNING.value,
                            "description": f"Buffer time conflict: {buffer_minutes} minutes required between appointments",
                        }
                    )

        except Exception as e:
            logger.warning(f"Failed to check buffer time conflicts: {str(e)}")

        return conflicts

    async def _check_operational_hours(
        self, provider_id: str, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Check if appointment is within operational hours."""
        conflicts = []

        try:
            operational_hours = self.scheduling_rules.get("operational_hours", {})
            day_name = start_time.strftime("%A").lower()

            day_hours = operational_hours.get(day_name)
            if not day_hours:
                # If no hours defined, assume practice is closed
                conflicts.append(
                    {
                        "conflict_type": ConflictType.OPERATIONAL_HOURS.value,
                        "conflict_start": start_time.isoformat(),
                        "conflict_end": end_time.isoformat(),
                        "severity": ConflictSeverity.BLOCKING.value,
                        "description": f"Practice is closed on {day_name.title()}",
                    }
                )
                return conflicts

            # Parse operational hours
            open_time = datetime.strptime(day_hours["open"], "%H:%M").time()
            close_time = datetime.strptime(day_hours["close"], "%H:%M").time()

            # Check if appointment is within hours
            if start_time.time() < open_time or end_time.time() > close_time:
                conflicts.append(
                    {
                        "conflict_type": ConflictType.OPERATIONAL_HOURS.value,
                        "conflict_start": start_time.isoformat(),
                        "conflict_end": end_time.isoformat(),
                        "severity": ConflictSeverity.BLOCKING.value,
                        "description": f"Outside operational hours ({open_time} - {close_time})",
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to check operational hours: {str(e)}")

        return conflicts

    async def _check_breaks_and_holidays(
        self, provider_id: str, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Check for conflicts with breaks and holidays."""
        conflicts = []

        try:
            # Check practice holidays
            holidays = self.scheduling_rules.get("practice_holidays", [])
            appointment_date = start_time.date().isoformat()

            if appointment_date in holidays:
                conflicts.append(
                    {
                        "conflict_type": ConflictType.HOLIDAY.value,
                        "conflict_start": start_time.isoformat(),
                        "conflict_end": end_time.isoformat(),
                        "severity": ConflictSeverity.BLOCKING.value,
                        "description": f"Practice holiday on {appointment_date}",
                    }
                )

            # Check provider-specific breaks
            provider_prefs = self.scheduling_rules.get("provider_preferences", {}).get(
                provider_id, {}
            )
            breaks = provider_prefs.get("breaks", [])

            for break_period in breaks:
                break_start = datetime.strptime(break_period["start"], "%H:%M").time()
                break_end = datetime.strptime(break_period["end"], "%H:%M").time()

                # Convert to datetime for comparison
                break_start_dt = datetime.combine(start_time.date(), break_start)
                break_end_dt = datetime.combine(start_time.date(), break_end)

                if self._times_overlap(
                    start_time, end_time, break_start_dt, break_end_dt
                ):
                    conflicts.append(
                        {
                            "conflict_type": ConflictType.BREAK_TIME.value,
                            "conflict_start": break_start_dt.isoformat(),
                            "conflict_end": break_end_dt.isoformat(),
                            "severity": ConflictSeverity.BLOCKING.value,
                            "description": f"Provider break time ({break_start} - {break_end})",
                        }
                    )

        except Exception as e:
            logger.warning(f"Failed to check breaks and holidays: {str(e)}")

        return conflicts

    async def _check_provider_rules(
        self,
        provider_id: str,
        start_time: datetime,
        end_time: datetime,
        appointment_type: str,
    ) -> List[Dict[str, Any]]:
        """Check provider-specific scheduling rules."""
        conflicts = []

        try:
            provider_prefs = self.scheduling_rules.get("provider_preferences", {}).get(
                provider_id, {}
            )

            # Check appointment type restrictions
            allowed_types = provider_prefs.get("allowed_appointment_types")
            if allowed_types and appointment_type not in allowed_types:
                conflicts.append(
                    {
                        "conflict_type": ConflictType.PROVIDER_UNAVAILABLE.value,
                        "conflict_start": start_time.isoformat(),
                        "conflict_end": end_time.isoformat(),
                        "severity": ConflictSeverity.BLOCKING.value,
                        "description": f"Provider does not accept {appointment_type} appointments",
                    }
                )

            # Check minimum/maximum appointment duration
            duration_minutes = int((end_time - start_time).total_seconds() / 60)
            min_duration = provider_prefs.get("min_appointment_minutes")
            max_duration = provider_prefs.get("max_appointment_minutes")

            if min_duration and duration_minutes < min_duration:
                conflicts.append(
                    {
                        "conflict_type": ConflictType.PROVIDER_UNAVAILABLE.value,
                        "conflict_start": start_time.isoformat(),
                        "conflict_end": end_time.isoformat(),
                        "severity": ConflictSeverity.WARNING.value,
                        "description": f"Appointment too short (minimum {min_duration} minutes)",
                    }
                )

            if max_duration and duration_minutes > max_duration:
                conflicts.append(
                    {
                        "conflict_type": ConflictType.PROVIDER_UNAVAILABLE.value,
                        "conflict_start": start_time.isoformat(),
                        "conflict_end": end_time.isoformat(),
                        "severity": ConflictSeverity.WARNING.value,
                        "description": f"Appointment too long (maximum {max_duration} minutes)",
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to check provider rules: {str(e)}")

        return conflicts

    async def _generate_alternative_times(
        self,
        provider_id: str,
        original_start: datetime,
        original_end: datetime,
        appointment_type: str,
        max_suggestions: int = 3,
    ) -> List[Dict[str, Any]]:
        """Generate alternative appointment time suggestions."""
        alternatives = []
        duration = original_end - original_start

        try:
            # Search within same day first
            current_date = original_start.date()

            # Get operational hours for the day
            operational_hours = self.scheduling_rules.get("operational_hours", {})
            day_name = current_date.strftime("%A").lower()
            day_hours = operational_hours.get(day_name)

            if day_hours:
                open_time = datetime.strptime(day_hours["open"], "%H:%M").time()
                close_time = datetime.strptime(day_hours["close"], "%H:%M").time()

                # Generate time slots throughout the day
                current_time = datetime.combine(current_date, open_time)
                end_of_day = datetime.combine(current_date, close_time)

                while (
                    current_time + duration <= end_of_day
                    and len(alternatives) < max_suggestions
                ):
                    proposed_end = current_time + duration

                    # Check if this time slot has conflicts
                    conflicts = await self.check_conflicts(
                        provider_id,
                        current_time,
                        proposed_end,
                        appointment_type,
                    )

                    if not conflicts["has_blocking_conflicts"]:
                        # Calculate ranking score based on proximity to original time
                        time_diff = abs((current_time - original_start).total_seconds())
                        ranking_score = max(
                            0, 1.0 - (time_diff / 86400)
                        )  # Score based on closeness to original

                        alternatives.append(
                            {
                                "suggested_start": current_time.isoformat(),
                                "suggested_end": proposed_end.isoformat(),
                                "ranking_score": ranking_score,
                                "reason": "Available slot on same day",
                            }
                        )

                    # Move to next 30-minute slot
                    current_time += timedelta(minutes=30)

            # If not enough suggestions on same day, check next few days
            if len(alternatives) < max_suggestions:
                for days_ahead in range(1, 8):  # Check next week
                    if len(alternatives) >= max_suggestions:
                        break

                    future_date = current_date + timedelta(days=days_ahead)
                    future_day_name = future_date.strftime("%A").lower()
                    future_day_hours = operational_hours.get(future_day_name)

                    if future_day_hours:
                        open_time = datetime.strptime(
                            future_day_hours["open"], "%H:%M"
                        ).time()

                        # Try same time on future day
                        future_start = datetime.combine(
                            future_date, original_start.time()
                        )
                        future_end = future_start + duration

                        conflicts = await self.check_conflicts(
                            provider_id,
                            future_start,
                            future_end,
                            appointment_type,
                        )

                        if not conflicts["has_blocking_conflicts"]:
                            ranking_score = max(
                                0, 0.8 - (days_ahead * 0.1)
                            )  # Lower score for future dates

                            alternatives.append(
                                {
                                    "suggested_start": future_start.isoformat(),
                                    "suggested_end": future_end.isoformat(),
                                    "ranking_score": ranking_score,
                                    "reason": f"Same time on {future_date.strftime('%A, %B %d')}",
                                }
                            )

            # Sort by ranking score (highest first)
            alternatives.sort(key=lambda x: x["ranking_score"], reverse=True)

        except Exception as e:
            logger.warning(f"Failed to generate alternative times: {str(e)}")

        return alternatives[:max_suggestions]

    def _times_overlap(
        self,
        start1: datetime,
        end1: datetime,
        start2: datetime,
        end2: datetime,
    ) -> bool:
        """Check if two time periods overlap."""
        return start1 < end2 and end1 > start2

    def _get_buffer_time(self, provider_id: str, appointment_type: str) -> int:
        """Get buffer time in minutes for provider and appointment type."""
        provider_prefs = self.scheduling_rules.get("provider_preferences", {}).get(
            provider_id, {}
        )

        # Check type-specific buffer time
        type_buffers = provider_prefs.get("buffer_times", {})
        if appointment_type in type_buffers:
            return type_buffers[appointment_type]

        # Check provider default buffer time
        if "default_buffer_minutes" in provider_prefs:
            return provider_prefs["default_buffer_minutes"]

        # Use system default
        return self.default_buffer_minutes

    def _hash_identifier(self, identifier: str) -> str:
        """Create SHA256 hash of identifier for audit logging."""
        import hashlib

        return hashlib.sha256(identifier.encode()).hexdigest()[:16]
