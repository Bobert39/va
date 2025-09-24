"""
Unit tests for ScheduleChecker service.

Tests schedule checking, availability queries, caching behavior,
and bulk availability operations.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.emr import EMROAuthClient
from src.services.provider_schedule import ProviderScheduleService
from src.services.schedule_checker import AvailabilityQueryError, ScheduleChecker


@pytest.fixture
def mock_emr_client():
    """Create mock EMR client."""
    return AsyncMock(spec=EMROAuthClient)


@pytest.fixture
def mock_schedule_service():
    """Create mock schedule service."""
    return AsyncMock(spec=ProviderScheduleService)


@pytest.fixture
def schedule_checker(mock_emr_client, mock_schedule_service):
    """Create ScheduleChecker instance."""
    return ScheduleChecker(mock_emr_client, mock_schedule_service)


@pytest.fixture
def sample_schedule():
    """Sample schedule data for testing."""
    return {
        "schedule": {"start_time": "08:00", "end_time": "17:00"},
        "slots": [
            {
                "start": "2025-09-22T09:00:00",
                "end": "2025-09-22T09:30:00",
                "status": "busy",
                "appointment_id": "appt1",
            },
            {
                "start": "2025-09-22T09:30:00",
                "end": "2025-09-22T10:00:00",
                "status": "free",
            },
            {
                "start": "2025-09-22T10:00:00",
                "end": "2025-09-22T10:30:00",
                "status": "free",
            },
            {
                "start": "2025-09-22T11:00:00",
                "end": "2025-09-22T11:30:00",
                "status": "busy",
                "appointment_id": "appt2",
            },
            {
                "start": "2025-09-22T14:00:00",
                "end": "2025-09-22T15:00:00",
                "status": "busy",
                "appointment_id": "appt3",
            },
        ],
    }


class TestScheduleChecker:
    """Test ScheduleChecker functionality."""

    @pytest.mark.asyncio
    async def test_is_time_available_free_slot(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test checking availability for a free time slot."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        start_time = datetime(2025, 9, 22, 9, 30)  # Free slot
        end_time = datetime(2025, 9, 22, 10, 0)

        result = await schedule_checker.is_time_available(
            "provider123", start_time, end_time
        )

        assert result is True
        mock_schedule_service.get_provider_schedules.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_time_available_busy_slot(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test checking availability for a busy time slot."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        start_time = datetime(2025, 9, 22, 9, 15)  # Overlaps with busy slot
        end_time = datetime(2025, 9, 22, 9, 45)

        result = await schedule_checker.is_time_available(
            "provider123", start_time, end_time
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_is_time_available_partial_overlap(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test checking availability with partial overlap."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        start_time = datetime(
            2025, 9, 22, 8, 45
        )  # Starts before but overlaps with busy slot
        end_time = datetime(2025, 9, 22, 9, 15)

        result = await schedule_checker.is_time_available(
            "provider123", start_time, end_time
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_is_time_available_exclude_appointment(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test checking availability excluding specific appointment."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        # Time that conflicts with appt1 but we exclude it
        start_time = datetime(2025, 9, 22, 9, 0)
        end_time = datetime(2025, 9, 22, 9, 30)

        result = await schedule_checker.is_time_available(
            "provider123", start_time, end_time, exclude_appointment_id="appt1"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_get_next_available_slot_found(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test finding next available slot."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        start_from = datetime(2025, 9, 22, 8, 0)
        duration_minutes = 30

        result = await schedule_checker.get_next_available_slot(
            "provider123", start_from, duration_minutes, within_days=1
        )

        assert result is not None
        assert "start" in result
        assert "end" in result
        assert "duration_minutes" in result

        # Should find the first available 30-minute slot
        slot_start = datetime.fromisoformat(result["start"])
        slot_end = datetime.fromisoformat(result["end"])
        duration = slot_end - slot_start
        assert duration.total_seconds() / 60 == 30

    @pytest.mark.asyncio
    async def test_get_next_available_slot_not_found(
        self, schedule_checker, mock_schedule_service
    ):
        """Test when no available slot is found."""
        # Schedule with all slots busy
        busy_schedule = {
            "schedule": {"start_time": "08:00", "end_time": "17:00"},
            "slots": [
                {
                    "start": "2025-09-22T08:00:00",
                    "end": "2025-09-22T17:00:00",
                    "status": "busy",
                    "appointment_id": "all_day_busy",
                }
            ],
        }
        mock_schedule_service.get_provider_schedules.return_value = [busy_schedule]

        start_from = datetime(2025, 9, 22, 8, 0)
        duration_minutes = 30

        result = await schedule_checker.get_next_available_slot(
            "provider123", start_from, duration_minutes, within_days=1
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_available_slots(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test getting all available slots for a date."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        date = datetime(2025, 9, 22).date()
        duration_minutes = 30

        slots = await schedule_checker.get_available_slots(
            "provider123", date, duration_minutes
        )

        assert len(slots) > 0
        for slot in slots:
            assert "start" in slot
            assert "end" in slot
            assert "duration_minutes" in slot
            assert slot["duration_minutes"] == duration_minutes

    @pytest.mark.asyncio
    async def test_check_bulk_availability(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test bulk availability checking."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        time_slots = [
            {
                "start": datetime(2025, 9, 22, 9, 30),  # Free slot
                "end": datetime(2025, 9, 22, 10, 0),
            },
            {
                "start": datetime(2025, 9, 22, 9, 0),  # Busy slot
                "end": datetime(2025, 9, 22, 9, 30),
            },
            {
                "start": datetime(2025, 9, 22, 10, 0),  # Free slot
                "end": datetime(2025, 9, 22, 10, 30),
            },
        ]

        results = await schedule_checker.check_bulk_availability(
            "provider123", time_slots
        )

        assert len(results) == 3
        assert results["0"] is True  # First slot is free
        assert results["1"] is False  # Second slot is busy
        assert results["2"] is True  # Third slot is free

    @pytest.mark.asyncio
    async def test_schedule_caching(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test schedule caching behavior."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        date = datetime(2025, 9, 22).date()

        # First call should fetch from service
        await schedule_checker._get_cached_schedule("provider123", date)
        assert mock_schedule_service.get_provider_schedules.call_count == 1

        # Second call should use cache
        await schedule_checker._get_cached_schedule("provider123", date)
        assert (
            mock_schedule_service.get_provider_schedules.call_count == 1
        )  # Still 1, no additional call

    @pytest.mark.asyncio
    async def test_cache_expiration(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test cache expiration behavior."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        date = datetime(2025, 9, 22).date()
        cache_key = f"provider123_{date.isoformat()}"

        # Manually set expired cache entry
        schedule_checker._schedule_cache[cache_key] = {
            "schedule": sample_schedule,
            "timestamp": datetime.now()
            - timedelta(minutes=10),  # Expired (TTL is 5 minutes)
        }

        # Should fetch fresh data
        await schedule_checker._get_cached_schedule("provider123", date)
        assert mock_schedule_service.get_provider_schedules.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_invalidation(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test manual cache invalidation."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        date = datetime(2025, 9, 22).date()

        # Populate cache
        await schedule_checker._get_cached_schedule("provider123", date)

        # Invalidate specific date
        with patch(
            "src.services.schedule_checker.log_audit_event", new_callable=AsyncMock
        ):
            await schedule_checker.invalidate_cache("provider123", date)

        # Next call should fetch fresh data
        await schedule_checker._get_cached_schedule("provider123", date)
        assert mock_schedule_service.get_provider_schedules.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_invalidation_all_dates(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test invalidating all dates for a provider."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        date1 = datetime(2025, 9, 22).date()
        date2 = datetime(2025, 9, 23).date()

        # Populate cache for multiple dates
        await schedule_checker._get_cached_schedule("provider123", date1)
        await schedule_checker._get_cached_schedule("provider123", date2)

        # Invalidate all dates for provider
        with patch(
            "src.services.schedule_checker.log_audit_event", new_callable=AsyncMock
        ):
            await schedule_checker.invalidate_cache("provider123")

        # Both should be removed from cache
        assert (
            len(
                [
                    k
                    for k in schedule_checker._schedule_cache.keys()
                    if k.startswith("provider123_")
                ]
            )
            == 0
        )

    @pytest.mark.asyncio
    async def test_cache_cleanup(self, schedule_checker):
        """Test automatic cache cleanup."""
        # Add old cache entries
        old_timestamp = datetime.now() - timedelta(hours=2)
        schedule_checker._schedule_cache["old_entry"] = {
            "schedule": {},
            "timestamp": old_timestamp,
        }
        schedule_checker._schedule_cache["new_entry"] = {
            "schedule": {},
            "timestamp": datetime.now(),
        }

        await schedule_checker._cleanup_cache()

        # Old entry should be removed
        assert "old_entry" not in schedule_checker._schedule_cache
        assert "new_entry" in schedule_checker._schedule_cache

    @pytest.mark.asyncio
    async def test_stale_cache_fallback(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test using stale cache when fresh fetch fails."""
        date = datetime(2025, 9, 22).date()
        cache_key = f"provider123_{date.isoformat()}"

        # Set up stale cache
        schedule_checker._schedule_cache[cache_key] = {
            "schedule": sample_schedule,
            "timestamp": datetime.now() - timedelta(minutes=10),  # Expired
        }

        # Make service call fail
        mock_schedule_service.get_provider_schedules.side_effect = Exception(
            "Network error"
        )

        # Should return stale cache as fallback
        result = await schedule_checker._get_cached_schedule("provider123", date)
        assert result == sample_schedule

    def test_times_overlap(self, schedule_checker):
        """Test time overlap detection."""
        # Overlapping times
        start1 = datetime(2025, 9, 22, 10, 0)
        end1 = datetime(2025, 9, 22, 10, 30)
        start2 = datetime(2025, 9, 22, 10, 15)
        end2 = datetime(2025, 9, 22, 10, 45)

        assert schedule_checker._times_overlap(start1, end1, start2, end2)

        # Non-overlapping times
        start2 = datetime(2025, 9, 22, 10, 30)
        end2 = datetime(2025, 9, 22, 11, 0)

        assert not schedule_checker._times_overlap(start1, end1, start2, end2)

    def test_find_available_slots_in_day(self, schedule_checker, sample_schedule):
        """Test finding available slots within a day."""
        duration = timedelta(minutes=30)

        slots = schedule_checker._find_available_slots_in_day(sample_schedule, duration)

        assert len(slots) > 0
        for slot in slots:
            assert "start" in slot
            assert "end" in slot
            assert "duration_minutes" in slot
            assert slot["duration_minutes"] == 30

    def test_find_available_slots_with_earliest_start(
        self, schedule_checker, sample_schedule
    ):
        """Test finding available slots with earliest start time."""
        duration = timedelta(minutes=30)
        earliest_start = datetime(2025, 9, 22, 10, 0)  # Start search from 10:00 AM

        slots = schedule_checker._find_available_slots_in_day(
            sample_schedule, duration, earliest_start
        )

        # All slots should start at or after earliest_start
        for slot in slots:
            slot_start = datetime.fromisoformat(slot["start"])
            assert slot_start >= earliest_start

    @pytest.mark.asyncio
    async def test_error_handling(self, schedule_checker, mock_schedule_service):
        """Test error handling in availability queries."""
        mock_schedule_service.get_provider_schedules.side_effect = Exception(
            "EMR connection failed"
        )

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        with pytest.raises(AvailabilityQueryError):
            await schedule_checker.is_time_available(
                "provider123", start_time, end_time
            )

    def test_hash_identifier(self, schedule_checker):
        """Test identifier hashing."""
        identifier = "provider123"
        hashed = schedule_checker._hash_identifier(identifier)

        assert len(hashed) == 16
        assert hashed.isalnum()

        # Same input should produce same hash
        hashed2 = schedule_checker._hash_identifier(identifier)
        assert hashed == hashed2


class TestScheduleCheckerEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_schedule(self, schedule_checker, mock_schedule_service):
        """Test handling of empty schedule."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        # Should be available when no slots exist
        result = await schedule_checker.is_time_available(
            "provider123", start_time, end_time
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_malformed_schedule_data(
        self, schedule_checker, mock_schedule_service
    ):
        """Test handling of malformed schedule data."""
        malformed_schedule = {
            "slots": [
                {
                    "start": "invalid-date",
                    "status": "busy"
                    # Missing end time
                }
            ]
        }
        mock_schedule_service.get_provider_schedules.return_value = [malformed_schedule]

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        # Should raise AvailabilityQueryError for malformed data
        with pytest.raises(AvailabilityQueryError, match="Availability check failed"):
            await schedule_checker.is_time_available(
                "provider123", start_time, end_time
            )

    @pytest.mark.asyncio
    async def test_very_long_duration(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test handling of very long appointment duration."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        date = datetime(2025, 9, 22).date()
        duration_minutes = 480  # 8 hours

        slots = await schedule_checker.get_available_slots(
            "provider123", date, duration_minutes
        )

        # Should handle long durations appropriately
        assert isinstance(slots, list)

    @pytest.mark.asyncio
    async def test_past_date_scheduling(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test scheduling for past dates."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        # Past date
        past_date = datetime.now().date() - timedelta(days=30)
        duration_minutes = 30

        slots = await schedule_checker.get_available_slots(
            "provider123", past_date, duration_minutes
        )

        # Should handle past dates without error
        assert isinstance(slots, list)

    @pytest.mark.asyncio
    async def test_far_future_date(
        self, schedule_checker, mock_schedule_service, sample_schedule
    ):
        """Test scheduling for far future dates."""
        mock_schedule_service.get_provider_schedules.return_value = [sample_schedule]

        # Far future date
        future_date = datetime.now().date() + timedelta(days=365)
        duration_minutes = 30

        slots = await schedule_checker.get_available_slots(
            "provider123", future_date, duration_minutes
        )

        # Should handle future dates without error
        assert isinstance(slots, list)

    @pytest.mark.asyncio
    async def test_bulk_availability_empty_list(
        self, schedule_checker, mock_schedule_service
    ):
        """Test bulk availability check with empty time slots list."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        time_slots = []

        results = await schedule_checker.check_bulk_availability(
            "provider123", time_slots
        )

        assert results == {}

    @pytest.mark.asyncio
    async def test_schedule_with_no_operational_hours(
        self, schedule_checker, mock_schedule_service
    ):
        """Test schedule without operational hours defined."""
        schedule_without_hours = {
            "slots": [
                {
                    "start": "2025-09-22T10:00:00",
                    "end": "2025-09-22T10:30:00",
                    "status": "free",
                }
            ]
            # Missing schedule.start_time and schedule.end_time
        }
        mock_schedule_service.get_provider_schedules.return_value = [
            schedule_without_hours
        ]

        date = datetime(2025, 9, 22).date()
        duration_minutes = 30

        # Should handle missing operational hours gracefully
        slots = await schedule_checker.get_available_slots(
            "provider123", date, duration_minutes
        )
        assert isinstance(slots, list)
