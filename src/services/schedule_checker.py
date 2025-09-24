"""
Schedule Checker Service

This module provides efficient schedule checking and availability queries
with caching and optimized EMR integration for conflict detection.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..audit import log_audit_event
from .emr import EMROAuthClient
from .provider_schedule import ProviderScheduleService

logger = logging.getLogger(__name__)


class ScheduleCheckerError(Exception):
    """Base exception for schedule checker operations."""

    pass


class AvailabilityQueryError(ScheduleCheckerError):
    """Error during availability query operations."""

    pass


class ScheduleChecker:
    """
    Optimized service for checking provider schedule availability.

    Provides efficient schedule queries with caching for real-time
    conflict detection during voice call processing.
    """

    def __init__(
        self,
        emr_client: EMROAuthClient,
        schedule_service: ProviderScheduleService,
    ):
        """
        Initialize schedule checker.

        Args:
            emr_client: EMR OAuth client for API access
            schedule_service: Provider schedule service
        """
        self.emr_client = emr_client
        self.schedule_service = schedule_service
        self._schedule_cache = {}
        self._cache_ttl_minutes = 5

    async def is_time_available(
        self,
        provider_id: str,
        start_time: datetime,
        end_time: datetime,
        exclude_appointment_id: Optional[str] = None,
    ) -> bool:
        """
        Check if a specific time slot is available for booking.

        Args:
            provider_id: Provider identifier
            start_time: Slot start time
            end_time: Slot end time
            exclude_appointment_id: Appointment ID to exclude from conflict check

        Returns:
            True if time slot is available, False otherwise

        Raises:
            AvailabilityQueryError: If availability check fails
        """
        try:
            # Get schedule for the day
            date = start_time.date()
            schedule = await self._get_cached_schedule(provider_id, date)

            # Check each slot in the schedule
            for slot in schedule.get("slots", []):
                # Skip the appointment we're excluding (for rescheduling)
                if (
                    exclude_appointment_id
                    and slot.get("appointment_id") == exclude_appointment_id
                ):
                    continue

                # Skip free slots
                if slot.get("status") == "free":
                    continue

                slot_start = datetime.fromisoformat(slot["start"])
                slot_end = datetime.fromisoformat(slot["end"])

                # Check for overlap
                if self._times_overlap(start_time, end_time, slot_start, slot_end):
                    return False

            return True

        except Exception as e:
            logger.error(f"Failed to check time availability: {str(e)}")
            raise AvailabilityQueryError(f"Availability check failed: {str(e)}")

    async def get_next_available_slot(
        self,
        provider_id: str,
        start_from: datetime,
        duration_minutes: int,
        within_days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the next available appointment slot.

        Args:
            provider_id: Provider identifier
            start_from: Start searching from this time
            duration_minutes: Required appointment duration
            within_days: Search within this many days

        Returns:
            Dict with slot info or None if no slots available

        Raises:
            AvailabilityQueryError: If search fails
        """
        try:
            duration = timedelta(minutes=duration_minutes)
            current_date = start_from.date()
            end_date = current_date + timedelta(days=within_days)

            while current_date <= end_date:
                # Get schedule for current date
                schedule = await self._get_cached_schedule(provider_id, current_date)

                # Find available slots
                available_slots = self._find_available_slots_in_day(
                    schedule,
                    duration,
                    start_from if current_date == start_from.date() else None,
                )

                if available_slots:
                    # Return first available slot
                    return available_slots[0]

                current_date += timedelta(days=1)

            return None

        except Exception as e:
            logger.error(f"Failed to find next available slot: {str(e)}")
            raise AvailabilityQueryError(f"Next slot search failed: {str(e)}")

    async def get_available_slots(
        self, provider_id: str, date: datetime.date, duration_minutes: int
    ) -> List[Dict[str, Any]]:
        """
        Get all available slots for a specific date.

        Args:
            provider_id: Provider identifier
            date: Date to check
            duration_minutes: Required appointment duration

        Returns:
            List of available slot dictionaries

        Raises:
            AvailabilityQueryError: If slot retrieval fails
        """
        try:
            duration = timedelta(minutes=duration_minutes)
            schedule = await self._get_cached_schedule(provider_id, date)

            return self._find_available_slots_in_day(schedule, duration)

        except Exception as e:
            logger.error(f"Failed to get available slots: {str(e)}")
            raise AvailabilityQueryError(f"Slot retrieval failed: {str(e)}")

    async def check_bulk_availability(
        self, provider_id: str, time_slots: List[Dict[str, datetime]]
    ) -> Dict[str, bool]:
        """
        Check availability for multiple time slots efficiently.

        Args:
            provider_id: Provider identifier
            time_slots: List of dicts with 'start' and 'end' datetime keys

        Returns:
            Dict mapping slot index to availability boolean

        Raises:
            AvailabilityQueryError: If bulk check fails
        """
        try:
            results = {}

            # Group slots by date for efficient cache usage
            slots_by_date = {}
            for i, slot in enumerate(time_slots):
                date = slot["start"].date()
                if date not in slots_by_date:
                    slots_by_date[date] = []
                slots_by_date[date].append((i, slot))

            # Check each date's slots
            for date, date_slots in slots_by_date.items():
                schedule = await self._get_cached_schedule(provider_id, date)

                for slot_index, slot in date_slots:
                    is_available = await self._check_slot_in_schedule(
                        schedule, slot["start"], slot["end"]
                    )
                    results[str(slot_index)] = is_available

            return results

        except Exception as e:
            logger.error(f"Failed bulk availability check: {str(e)}")
            raise AvailabilityQueryError(f"Bulk availability check failed: {str(e)}")

    async def _get_cached_schedule(
        self, provider_id: str, date: datetime.date
    ) -> Dict[str, Any]:
        """Get provider schedule with caching."""
        cache_key = f"{provider_id}_{date.isoformat()}"

        # Check cache
        if cache_key in self._schedule_cache:
            cached_data = self._schedule_cache[cache_key]
            cache_time = cached_data["timestamp"]
            cache_age = (datetime.now() - cache_time).total_seconds() / 60

            if cache_age < self._cache_ttl_minutes:
                return cached_data["schedule"]

        # Fetch fresh schedule
        try:
            schedules = await self.schedule_service.get_provider_schedules(
                provider_id, date, date
            )
            schedule = schedules[0] if schedules else {"slots": []}

            # Cache the result
            self._schedule_cache[cache_key] = {
                "schedule": schedule,
                "timestamp": datetime.now(),
            }

            # Clean old cache entries (keep only last hour)
            await self._cleanup_cache()

            return schedule

        except Exception as e:
            # If we have stale cached data, use it as fallback
            if cache_key in self._schedule_cache:
                logger.warning(
                    f"Using stale schedule cache due to fetch error: {str(e)}"
                )
                return self._schedule_cache[cache_key]["schedule"]
            raise

    async def _cleanup_cache(self):
        """Remove old cache entries."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=1)
            keys_to_remove = []

            for key, data in self._schedule_cache.items():
                if data["timestamp"] < cutoff_time:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._schedule_cache[key]

        except Exception as e:
            logger.warning(f"Cache cleanup failed: {str(e)}")

    def _find_available_slots_in_day(
        self,
        schedule: Dict[str, Any],
        duration: timedelta,
        earliest_start: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Find all available slots in a day's schedule."""
        available_slots = []

        # Get operational hours for the day
        schedule_info = schedule.get("schedule", {})
        if not schedule_info:
            return available_slots

        # Parse working hours
        start_time_str = schedule_info.get("start_time", "09:00")
        end_time_str = schedule_info.get("end_time", "17:00")

        try:
            # Assume schedule date from first slot or use today
            schedule_date = datetime.now().date()
            if schedule.get("slots"):
                first_slot = schedule["slots"][0]
                schedule_date = datetime.fromisoformat(first_slot["start"]).date()

            day_start = datetime.combine(
                schedule_date,
                datetime.strptime(start_time_str, "%H:%M").time(),
            )
            day_end = datetime.combine(
                schedule_date, datetime.strptime(end_time_str, "%H:%M").time()
            )

            # Use earliest_start if specified and later than day_start
            if earliest_start and earliest_start > day_start:
                day_start = earliest_start

            # Get busy periods from slots
            busy_periods = []
            for slot in schedule.get("slots", []):
                if slot.get("status") != "free":
                    busy_periods.append(
                        {
                            "start": datetime.fromisoformat(slot["start"]),
                            "end": datetime.fromisoformat(slot["end"]),
                        }
                    )

            # Sort busy periods by start time
            busy_periods.sort(key=lambda x: x["start"])

            # Find gaps between busy periods
            current_time = day_start

            for busy_period in busy_periods:
                # Check gap before this busy period
                gap_end = busy_period["start"]
                if current_time + duration <= gap_end:
                    # We have a gap that can fit the appointment
                    slot_start = current_time
                    slot_end = slot_start + duration

                    available_slots.append(
                        {
                            "start": slot_start.isoformat(),
                            "end": slot_end.isoformat(),
                            "duration_minutes": int(duration.total_seconds() / 60),
                        }
                    )

                # Move current time to end of busy period
                current_time = max(current_time, busy_period["end"])

            # Check gap after last busy period
            if current_time + duration <= day_end:
                slot_start = current_time
                slot_end = slot_start + duration

                available_slots.append(
                    {
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat(),
                        "duration_minutes": int(duration.total_seconds() / 60),
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to parse schedule times: {str(e)}")

        return available_slots

    async def _check_slot_in_schedule(
        self,
        schedule: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Check if a specific slot is available in the schedule."""
        for slot in schedule.get("slots", []):
            if slot.get("status") == "free":
                continue

            slot_start = datetime.fromisoformat(slot["start"])
            slot_end = datetime.fromisoformat(slot["end"])

            if self._times_overlap(start_time, end_time, slot_start, slot_end):
                return False

        return True

    def _times_overlap(
        self,
        start1: datetime,
        end1: datetime,
        start2: datetime,
        end2: datetime,
    ) -> bool:
        """Check if two time periods overlap."""
        return start1 < end2 and end1 > start2

    async def invalidate_cache(
        self, provider_id: str, date: Optional[datetime.date] = None
    ):
        """
        Invalidate cached schedule data.

        Args:
            provider_id: Provider to invalidate cache for
            date: Specific date to invalidate, or None for all dates
        """
        try:
            if date:
                cache_key = f"{provider_id}_{date.isoformat()}"
                if cache_key in self._schedule_cache:
                    del self._schedule_cache[cache_key]
            else:
                # Remove all entries for this provider
                keys_to_remove = [
                    key
                    for key in self._schedule_cache.keys()
                    if key.startswith(f"{provider_id}_")
                ]
                for key in keys_to_remove:
                    del self._schedule_cache[key]

            await log_audit_event(
                "schedule_cache_invalidated",
                {
                    "provider_id_hash": self._hash_identifier(provider_id),
                    "date": date.isoformat() if date else "all_dates",
                },
            )

        except Exception as e:
            logger.warning(f"Cache invalidation failed: {str(e)}")

    def _hash_identifier(self, identifier: str) -> str:
        """Create SHA256 hash of identifier for audit logging."""
        import hashlib

        return hashlib.sha256(identifier.encode()).hexdigest()[:16]
