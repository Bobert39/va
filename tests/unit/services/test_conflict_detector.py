"""
Unit tests for ConflictDetector service.

Tests all conflict detection scenarios including existing appointments,
buffer times, operational hours, breaks, and rule validation.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.conflict_detector import (
    ConflictDetector,
    ConflictSeverity,
    ConflictType,
    ScheduleConflictError,
)
from src.services.emr import EMROAuthClient
from src.services.provider_schedule import ProviderScheduleService


@pytest.fixture
def mock_emr_client():
    """Create mock EMR client."""
    return AsyncMock(spec=EMROAuthClient)


@pytest.fixture
def mock_schedule_service():
    """Create mock schedule service."""
    return AsyncMock(spec=ProviderScheduleService)


@pytest.fixture
def scheduling_config():
    """Create test scheduling configuration."""
    return {
        "scheduling_rules": {
            "default_buffer_minutes": 15,
            "operational_hours": {
                "monday": {"open": "08:00", "close": "17:00"},
                "tuesday": {"open": "08:00", "close": "17:00"},
                "wednesday": {"open": "08:00", "close": "17:00"},
                "thursday": {"open": "08:00", "close": "17:00"},
                "friday": {"open": "08:00", "close": "17:00"},
                "saturday": {"open": "09:00", "close": "12:00"},
                "sunday": None,
            },
            "practice_holidays": ["2025-09-21"],
            "provider_preferences": {
                "provider123": {
                    "default_buffer_minutes": 20,
                    "breaks": [{"start": "12:00", "end": "13:00"}],
                    "allowed_appointment_types": ["standard", "followup"],
                    "min_appointment_minutes": 15,
                    "max_appointment_minutes": 90,
                }
            },
        }
    }


@pytest.fixture
def conflict_detector(mock_emr_client, mock_schedule_service, scheduling_config):
    """Create ConflictDetector instance."""
    return ConflictDetector(mock_emr_client, mock_schedule_service, scheduling_config)


class TestConflictDetector:
    """Test ConflictDetector functionality."""

    @pytest.mark.asyncio
    async def test_check_conflicts_no_conflicts(
        self, conflict_detector, mock_schedule_service
    ):
        """Test conflict check with no conflicts found."""
        # Mock schedule with no conflicting appointments
        mock_schedule_service.get_provider_schedules.return_value = [
            {
                "slots": [
                    {
                        "start": "2025-09-22T09:00:00",
                        "end": "2025-09-22T09:30:00",
                        "status": "free",
                    },
                    {
                        "start": "2025-09-22T11:00:00",
                        "end": "2025-09-22T11:30:00",
                        "status": "busy",
                        "appointment_id": "appt456",
                    },
                ]
            }
        ]

        start_time = datetime(2025, 9, 22, 10, 0)  # Monday 10:00 AM
        end_time = datetime(2025, 9, 22, 10, 30)  # Monday 10:30 AM

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        assert not result["has_conflicts"]
        assert not result["has_blocking_conflicts"]
        assert result["can_schedule"]
        assert result["conflicts"] == []

    @pytest.mark.asyncio
    async def test_check_conflicts_existing_appointment(
        self, conflict_detector, mock_schedule_service
    ):
        """Test conflict detection with existing appointment overlap."""
        # Mock schedule with conflicting appointment
        mock_schedule_service.get_provider_schedules.return_value = [
            {
                "slots": [
                    {
                        "start": "2025-09-22T10:15:00",
                        "end": "2025-09-22T10:45:00",
                        "status": "busy",
                        "appointment_id": "appt456",
                    }
                ]
            }
        ]

        start_time = datetime(2025, 9, 22, 10, 0)  # Monday 10:00 AM
        end_time = datetime(2025, 9, 22, 10, 30)  # Monday 10:30 AM (overlaps)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        assert result["has_conflicts"]
        assert result["has_blocking_conflicts"]
        assert not result["can_schedule"]
        assert len(result["conflicts"]) == 1
        assert (
            result["conflicts"][0]["conflict_type"]
            == ConflictType.EXISTING_APPOINTMENT.value
        )
        assert result["conflicts"][0]["severity"] == ConflictSeverity.BLOCKING.value

    @pytest.mark.asyncio
    async def test_check_conflicts_buffer_time(
        self, conflict_detector, mock_schedule_service
    ):
        """Test buffer time conflict detection."""
        # Mock schedule with appointment that violates buffer time
        mock_schedule_service.get_provider_schedules.return_value = [
            {
                "slots": [
                    {
                        "start": "2025-09-22T09:50:00",  # 10 minutes before proposed start
                        "end": "2025-09-22T10:00:00",
                        "status": "busy",
                        "appointment_id": "appt456",
                    }
                ]
            }
        ]

        start_time = datetime(2025, 9, 22, 10, 0)  # Monday 10:00 AM
        end_time = datetime(2025, 9, 22, 10, 30)  # Monday 10:30 AM

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        # Should have buffer time conflict (provider123 has 20-minute buffer)
        buffer_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.BUFFER_TIME.value
        ]
        assert len(buffer_conflicts) == 1
        assert buffer_conflicts[0]["severity"] == ConflictSeverity.WARNING.value

    @pytest.mark.asyncio
    async def test_check_conflicts_outside_hours(
        self, conflict_detector, mock_schedule_service
    ):
        """Test conflict detection for outside operational hours."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        # Try to schedule before opening hours
        start_time = datetime(2025, 9, 22, 7, 0)  # Monday 7:00 AM (before 8:00 AM open)
        end_time = datetime(2025, 9, 22, 7, 30)  # Monday 7:30 AM

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        hours_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.OPERATIONAL_HOURS.value
        ]
        assert len(hours_conflicts) == 1
        assert hours_conflicts[0]["severity"] == ConflictSeverity.BLOCKING.value

    @pytest.mark.asyncio
    async def test_check_conflicts_break_time(
        self, conflict_detector, mock_schedule_service
    ):
        """Test conflict detection during provider break time."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        # Try to schedule during lunch break (12:00-13:00)
        start_time = datetime(2025, 9, 22, 12, 15)  # Monday 12:15 PM
        end_time = datetime(2025, 9, 22, 12, 45)  # Monday 12:45 PM

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        break_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.BREAK_TIME.value
        ]
        assert len(break_conflicts) == 1
        assert break_conflicts[0]["severity"] == ConflictSeverity.BLOCKING.value

    @pytest.mark.asyncio
    async def test_check_conflicts_holiday(
        self, conflict_detector, mock_schedule_service
    ):
        """Test conflict detection on practice holiday."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        # Try to schedule on holiday (2025-09-21)
        start_time = datetime(2025, 9, 21, 10, 0)  # Sunday (holiday) 10:00 AM
        end_time = datetime(2025, 9, 21, 10, 30)  # Sunday 10:30 AM

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        holiday_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.HOLIDAY.value
        ]
        assert len(holiday_conflicts) == 1
        assert holiday_conflicts[0]["severity"] == ConflictSeverity.BLOCKING.value

    @pytest.mark.asyncio
    async def test_check_conflicts_invalid_appointment_type(
        self, conflict_detector, mock_schedule_service
    ):
        """Test conflict detection for invalid appointment type."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        start_time = datetime(2025, 9, 22, 10, 0)  # Monday 10:00 AM
        end_time = datetime(2025, 9, 22, 10, 30)  # Monday 10:30 AM

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "surgery"  # Not in allowed types
            )

        provider_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.PROVIDER_UNAVAILABLE.value
        ]
        type_conflicts = [
            c for c in provider_conflicts if "does not accept" in c["description"]
        ]
        assert len(type_conflicts) == 1
        assert type_conflicts[0]["severity"] == ConflictSeverity.BLOCKING.value

    @pytest.mark.asyncio
    async def test_check_conflicts_appointment_too_short(
        self, conflict_detector, mock_schedule_service
    ):
        """Test conflict detection for appointment too short."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        start_time = datetime(2025, 9, 22, 10, 0)  # Monday 10:00 AM
        end_time = datetime(
            2025, 9, 22, 10, 10
        )  # Monday 10:10 AM (10 minutes, less than 15 min minimum)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        provider_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.PROVIDER_UNAVAILABLE.value
        ]
        duration_conflicts = [
            c for c in provider_conflicts if "too short" in c["description"]
        ]
        assert len(duration_conflicts) == 1
        assert duration_conflicts[0]["severity"] == ConflictSeverity.WARNING.value

    @pytest.mark.asyncio
    async def test_check_conflicts_appointment_too_long(
        self, conflict_detector, mock_schedule_service
    ):
        """Test conflict detection for appointment too long."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        start_time = datetime(2025, 9, 22, 10, 0)  # Monday 10:00 AM
        end_time = datetime(
            2025, 9, 22, 12, 0
        )  # Monday 12:00 PM (120 minutes, more than 90 min maximum)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        provider_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.PROVIDER_UNAVAILABLE.value
        ]
        duration_conflicts = [
            c for c in provider_conflicts if "too long" in c["description"]
        ]
        assert len(duration_conflicts) == 1
        assert duration_conflicts[0]["severity"] == ConflictSeverity.WARNING.value

    @pytest.mark.asyncio
    async def test_generate_alternative_times(
        self, conflict_detector, mock_schedule_service
    ):
        """Test alternative time generation."""
        # Mock schedule with some busy slots
        mock_schedule_service.get_provider_schedules.return_value = [
            {
                "schedule": {"start_time": "08:00", "end_time": "17:00"},
                "slots": [
                    {
                        "start": "2025-09-22T10:00:00",
                        "end": "2025-09-22T10:30:00",
                        "status": "busy",
                        "appointment_id": "existing1",
                    },
                    {
                        "start": "2025-09-22T14:00:00",
                        "end": "2025-09-22T14:30:00",
                        "status": "busy",
                        "appointment_id": "existing2",
                    },
                ],
            }
        ]

        # Mock conflict checks for alternative times to return no conflicts
        original_check_conflicts = conflict_detector.check_conflicts

        async def mock_check_conflicts(provider_id, start, end, appt_type):
            # Only original time has conflicts
            if start == datetime(2025, 9, 22, 10, 0):
                return {"has_blocking_conflicts": True}
            return {"has_blocking_conflicts": False}

        conflict_detector.check_conflicts = AsyncMock(side_effect=mock_check_conflicts)

        original_start = datetime(
            2025, 9, 22, 10, 0
        )  # Conflicts with existing appointment
        original_end = datetime(2025, 9, 22, 10, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            alternatives = await conflict_detector._generate_alternative_times(
                "provider123",
                original_start,
                original_end,
                "standard",
                max_suggestions=3,
            )

        assert len(alternatives) > 0
        for alt in alternatives:
            assert "suggested_start" in alt
            assert "suggested_end" in alt
            assert "ranking_score" in alt
            assert "reason" in alt
            assert 0 <= alt["ranking_score"] <= 1.0

        # Restore original method
        conflict_detector.check_conflicts = original_check_conflicts

    @pytest.mark.asyncio
    async def test_times_overlap(self, conflict_detector):
        """Test time overlap detection."""
        # Test overlapping times
        start1 = datetime(2025, 9, 22, 10, 0)
        end1 = datetime(2025, 9, 22, 10, 30)
        start2 = datetime(2025, 9, 22, 10, 15)
        end2 = datetime(2025, 9, 22, 10, 45)

        assert conflict_detector._times_overlap(start1, end1, start2, end2)

        # Test non-overlapping times
        start2 = datetime(2025, 9, 22, 10, 30)
        end2 = datetime(2025, 9, 22, 11, 0)

        assert not conflict_detector._times_overlap(start1, end1, start2, end2)

        # Test adjacent times (should not overlap)
        start2 = datetime(2025, 9, 22, 10, 30)
        end2 = datetime(2025, 9, 22, 11, 0)

        assert not conflict_detector._times_overlap(start1, end1, start2, end2)

    def test_get_buffer_time(self, conflict_detector):
        """Test buffer time calculation."""
        # Provider-specific buffer time
        buffer_time = conflict_detector._get_buffer_time("provider123", "standard")
        assert buffer_time == 20  # Provider preference

        # Default buffer time for unknown provider
        buffer_time = conflict_detector._get_buffer_time("unknown_provider", "standard")
        assert buffer_time == 15  # System default

    def test_hash_identifier(self, conflict_detector):
        """Test identifier hashing."""
        identifier = "provider123"
        hashed = conflict_detector._hash_identifier(identifier)

        assert len(hashed) == 16  # Should be truncated to 16 chars
        assert hashed.isalnum()  # Should contain only alphanumeric characters

        # Same input should produce same hash
        hashed2 = conflict_detector._hash_identifier(identifier)
        assert hashed == hashed2

    @pytest.mark.asyncio
    async def test_schedule_conflict_error_handling(
        self, conflict_detector, mock_schedule_service
    ):
        """Test error handling when schedule service fails."""
        # Make schedule service raise an exception
        mock_schedule_service.get_provider_schedules.side_effect = Exception(
            "EMR connection failed"
        )

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            with pytest.raises(ScheduleConflictError):
                await conflict_detector.check_conflicts(
                    "provider123", start_time, end_time, "standard"
                )

    @pytest.mark.asyncio
    async def test_multiple_conflict_types(
        self, conflict_detector, mock_schedule_service
    ):
        """Test detection of multiple conflict types in one check."""
        # Schedule appointment during break time AND with buffer conflict
        mock_schedule_service.get_provider_schedules.return_value = [
            {
                "slots": [
                    {
                        "start": "2025-09-22T11:50:00",  # 10 minutes before proposed start (buffer conflict)
                        "end": "2025-09-22T12:00:00",
                        "status": "busy",
                        "appointment_id": "appt1",
                    }
                ]
            }
        ]

        # Try to schedule during lunch break (12:00-13:00) which also violates buffer time
        start_time = datetime(2025, 9, 22, 12, 0)  # Monday 12:00 PM (start of break)
        end_time = datetime(2025, 9, 22, 12, 30)  # Monday 12:30 PM (during break)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        # Should detect both buffer time and break time conflicts
        conflict_types = {c["conflict_type"] for c in result["conflicts"]}
        assert ConflictType.BUFFER_TIME.value in conflict_types
        assert ConflictType.BREAK_TIME.value in conflict_types
        assert result["has_blocking_conflicts"]  # Break time is blocking
        assert not result["can_schedule"]


class TestConflictDetectorEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_weekend_scheduling(self, conflict_detector, mock_schedule_service):
        """Test scheduling on weekend with limited hours."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        # Saturday (limited hours 9:00-12:00)
        start_time = datetime(2025, 9, 20, 10, 0)  # Saturday 10:00 AM (within hours)
        end_time = datetime(2025, 9, 20, 10, 30)  # Saturday 10:30 AM

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        # Should be allowed on Saturday during operational hours
        hours_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.OPERATIONAL_HOURS.value
        ]
        assert len(hours_conflicts) == 0

    @pytest.mark.asyncio
    async def test_sunday_scheduling(self, conflict_detector, mock_schedule_service):
        """Test scheduling on Sunday (closed day)."""
        mock_schedule_service.get_provider_schedules.return_value = [{"slots": []}]

        # Sunday (closed)
        start_time = datetime(2025, 9, 21, 10, 0)  # Sunday 10:00 AM
        end_time = datetime(2025, 9, 21, 10, 30)  # Sunday 10:30 AM

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        # Should be blocked on Sunday
        hours_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.OPERATIONAL_HOURS.value
        ]
        assert len(hours_conflicts) == 1

    @pytest.mark.asyncio
    async def test_empty_schedule_response(
        self, conflict_detector, mock_schedule_service
    ):
        """Test handling of empty schedule response."""
        mock_schedule_service.get_provider_schedules.return_value = [{}]

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        # Should handle empty schedule gracefully
        assert isinstance(result, dict)
        assert "has_conflicts" in result
        assert "conflicts" in result

    @pytest.mark.asyncio
    async def test_malformed_schedule_data(
        self, conflict_detector, mock_schedule_service
    ):
        """Test handling of malformed schedule data."""
        # Schedule with missing required fields
        mock_schedule_service.get_provider_schedules.return_value = [
            {
                "slots": [
                    {
                        "start": "invalid-date-format",
                        "status": "busy"
                        # Missing end time
                    }
                ]
            }
        ]

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            # Should handle malformed data gracefully without crashing
            result = await conflict_detector.check_conflicts(
                "provider123", start_time, end_time, "standard"
            )

        assert isinstance(result, dict)
        assert "has_conflicts" in result
