"""
Integration tests for conflict resolution system.

Tests the integration between ConflictDetector, ScheduleChecker,
TimeSuggester, and SchedulingRulesManager services.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.conflict_detector import (
    ConflictDetector,
    ConflictSeverity,
    ConflictType,
)
from src.services.emr import EMROAuthClient
from src.services.provider_schedule import ProviderScheduleService
from src.services.schedule_checker import ScheduleChecker
from src.services.scheduling_rules import SchedulingRulesManager
from src.services.time_suggester import TimeSuggester


@pytest.fixture
def mock_emr_client():
    """Create mock EMR client."""
    return AsyncMock(spec=EMROAuthClient)


@pytest.fixture
def mock_schedule_service():
    """Create mock provider schedule service."""
    return AsyncMock(spec=ProviderScheduleService)


@pytest.fixture
def integration_config():
    """Create comprehensive configuration for integration testing."""
    return {
        "scheduling_rules": {
            "default_buffer_minutes": 15,
            "default_appointment_duration": 30,
            "operational_hours": {
                "monday": {"open": "08:00", "close": "17:00"},
                "tuesday": {"open": "08:00", "close": "17:00"},
                "wednesday": {"open": "08:00", "close": "17:00"},
                "thursday": {"open": "08:00", "close": "17:00"},
                "friday": {"open": "08:00", "close": "17:00"},
                "saturday": {"open": "09:00", "close": "12:00"},
                "sunday": None,
            },
            "practice_holidays": ["2025-12-25", "2025-01-01"],
            "provider_preferences": {
                "dr_smith": {
                    "default_buffer_minutes": 20,
                    "breaks": [{"start": "12:00", "end": "13:00"}],
                    "allowed_appointment_types": [
                        "consultation",
                        "followup",
                        "routine",
                    ],
                    "min_appointment_minutes": 15,
                    "max_appointment_minutes": 90,
                    "buffer_times": {"surgery": 30, "consultation": 20, "followup": 10},
                },
                "dr_jones": {
                    "default_buffer_minutes": 10,
                    "breaks": [
                        {"start": "11:30", "end": "12:00"},
                        {"start": "15:00", "end": "15:30"},
                    ],
                    "allowed_appointment_types": ["routine", "emergency", "followup"],
                    "min_appointment_minutes": 10,
                    "max_appointment_minutes": 60,
                },
            },
        },
        "suggestion_preferences": {
            "max_suggestions": 5,
            "search_days": 14,
            "preferred_time_ranges": ["09:00-11:00", "14:00-16:00"],
        },
    }


@pytest.fixture
def integrated_services(mock_emr_client, mock_schedule_service, integration_config):
    """Create integrated service instances."""
    rules_manager = SchedulingRulesManager(integration_config)
    schedule_checker = ScheduleChecker(mock_emr_client, mock_schedule_service)
    conflict_detector = ConflictDetector(
        mock_emr_client, mock_schedule_service, integration_config
    )
    time_suggester = TimeSuggester(
        conflict_detector, schedule_checker, integration_config
    )

    return {
        "rules_manager": rules_manager,
        "schedule_checker": schedule_checker,
        "conflict_detector": conflict_detector,
        "time_suggester": time_suggester,
    }


@pytest.fixture
def realistic_schedule():
    """Create realistic provider schedule for testing."""
    return {
        "schedule": {
            "start_time": "08:00",
            "end_time": "17:00",
            "provider_id": "dr_smith",
        },
        "slots": [
            # Morning appointments
            {
                "start": "2025-09-22T08:00:00",
                "end": "2025-09-22T08:30:00",
                "status": "busy",
                "appointment_id": "appt1",
            },
            {
                "start": "2025-09-22T08:30:00",
                "end": "2025-09-22T09:00:00",
                "status": "free",
            },
            {
                "start": "2025-09-22T09:00:00",
                "end": "2025-09-22T09:30:00",
                "status": "busy",
                "appointment_id": "appt2",
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
                "start": "2025-09-22T10:30:00",
                "end": "2025-09-22T11:00:00",
                "status": "busy",
                "appointment_id": "appt3",
            },
            {
                "start": "2025-09-22T11:00:00",
                "end": "2025-09-22T11:30:00",
                "status": "free",
            },
            {
                "start": "2025-09-22T11:30:00",
                "end": "2025-09-22T12:00:00",
                "status": "free",
            },
            # Lunch break (12:00-13:00) - no slots or busy slots
            {
                "start": "2025-09-22T12:00:00",
                "end": "2025-09-22T13:00:00",
                "status": "busy",
                "appointment_id": "lunch_break",
            },
            # Afternoon appointments
            {
                "start": "2025-09-22T13:00:00",
                "end": "2025-09-22T13:30:00",
                "status": "free",
            },
            {
                "start": "2025-09-22T13:30:00",
                "end": "2025-09-22T14:00:00",
                "status": "busy",
                "appointment_id": "appt4",
            },
            {
                "start": "2025-09-22T14:00:00",
                "end": "2025-09-22T14:30:00",
                "status": "free",
            },
            {
                "start": "2025-09-22T14:30:00",
                "end": "2025-09-22T15:00:00",
                "status": "free",
            },
            {
                "start": "2025-09-22T15:00:00",
                "end": "2025-09-22T16:00:00",
                "status": "busy",
                "appointment_id": "appt5",
            },
            {
                "start": "2025-09-22T16:00:00",
                "end": "2025-09-22T16:30:00",
                "status": "free",
            },
            {
                "start": "2025-09-22T16:30:00",
                "end": "2025-09-22T17:00:00",
                "status": "free",
            },
        ],
    }


class TestConflictResolutionIntegration:
    """Test integrated conflict resolution workflows."""

    @pytest.mark.asyncio
    async def test_successful_scheduling_no_conflicts(
        self, integrated_services, mock_schedule_service, realistic_schedule
    ):
        """Test successful appointment scheduling with no conflicts."""
        mock_schedule_service.get_provider_schedules.return_value = [realistic_schedule]

        conflict_detector = integrated_services["conflict_detector"]

        # Try to schedule in a free slot
        start_time = datetime(2025, 9, 22, 9, 30)  # Free slot
        end_time = datetime(2025, 9, 22, 10, 0)  # Free slot

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        assert not result["has_conflicts"]
        assert not result["has_blocking_conflicts"]
        assert result["can_schedule"]
        assert len(result["conflicts"]) == 0

    @pytest.mark.asyncio
    async def test_conflict_detection_and_resolution(
        self, integrated_services, mock_schedule_service, realistic_schedule
    ):
        """Test conflict detection and alternative time suggestion."""
        mock_schedule_service.get_provider_schedules.return_value = [realistic_schedule]

        conflict_detector = integrated_services["conflict_detector"]
        time_suggester = integrated_services["time_suggester"]

        # Try to schedule during busy time
        start_time = datetime(2025, 9, 22, 9, 0)  # Busy slot (conflicts with appt2)
        end_time = datetime(2025, 9, 22, 9, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            conflict_result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        # Should detect conflict
        assert conflict_result["has_conflicts"]
        assert conflict_result["has_blocking_conflicts"]
        assert not conflict_result["can_schedule"]

        existing_conflicts = [
            c
            for c in conflict_result["conflicts"]
            if c["conflict_type"] == ConflictType.EXISTING_APPOINTMENT.value
        ]
        assert len(existing_conflicts) > 0

        # Get alternative suggestions
        with patch(
            "src.services.time_suggester.log_audit_event", new_callable=AsyncMock
        ):
            suggestions = await time_suggester.suggest_alternative_times(
                "dr_smith", start_time, end_time, "consultation", max_suggestions=3
            )

        assert len(suggestions) > 0
        for suggestion in suggestions:
            assert "suggested_start" in suggestion
            assert "suggested_end" in suggestion
            assert "ranking_score" in suggestion
            assert "voice_friendly_time" in suggestion

    @pytest.mark.asyncio
    async def test_buffer_time_conflict_and_suggestions(
        self, integrated_services, mock_schedule_service, realistic_schedule
    ):
        """Test buffer time conflict detection and resolution."""
        mock_schedule_service.get_provider_schedules.return_value = [realistic_schedule]

        conflict_detector = integrated_services["conflict_detector"]

        # Try to schedule too close to existing appointment (dr_smith has 20-minute buffer for consultations)
        start_time = datetime(2025, 9, 22, 8, 45)  # 15 minutes after appt1 ends
        end_time = datetime(2025, 9, 22, 9, 15)  # Overlaps with appt2 start

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        # Should detect both buffer time and existing appointment conflicts
        conflict_types = {c["conflict_type"] for c in result["conflicts"]}
        assert (
            ConflictType.BUFFER_TIME.value in conflict_types
            or ConflictType.EXISTING_APPOINTMENT.value in conflict_types
        )

    @pytest.mark.asyncio
    async def test_break_time_conflict(
        self, integrated_services, mock_schedule_service, realistic_schedule
    ):
        """Test break time conflict detection."""
        mock_schedule_service.get_provider_schedules.return_value = [realistic_schedule]

        conflict_detector = integrated_services["conflict_detector"]

        # Try to schedule during lunch break (12:00-13:00)
        start_time = datetime(2025, 9, 22, 12, 15)  # During lunch
        end_time = datetime(2025, 9, 22, 12, 45)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        # Should detect break time conflict
        break_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.BREAK_TIME.value
        ]
        assert len(break_conflicts) > 0
        assert break_conflicts[0]["severity"] == ConflictSeverity.BLOCKING.value

    @pytest.mark.asyncio
    async def test_provider_rules_validation(
        self, integrated_services, mock_schedule_service, realistic_schedule
    ):
        """Test provider-specific rules validation."""
        mock_schedule_service.get_provider_schedules.return_value = [realistic_schedule]

        conflict_detector = integrated_services["conflict_detector"]

        # Try to schedule invalid appointment type for dr_smith
        start_time = datetime(2025, 9, 22, 10, 0)  # Free slot
        end_time = datetime(2025, 9, 22, 10, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "surgery"  # Not in allowed types
            )

        # Should detect provider rule violation
        provider_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.PROVIDER_UNAVAILABLE.value
        ]
        type_conflicts = [
            c for c in provider_conflicts if "does not accept" in c["description"]
        ]
        assert len(type_conflicts) > 0

    @pytest.mark.asyncio
    async def test_appointment_duration_limits(
        self, integrated_services, mock_schedule_service, realistic_schedule
    ):
        """Test appointment duration limit validation."""
        mock_schedule_service.get_provider_schedules.return_value = [realistic_schedule]

        conflict_detector = integrated_services["conflict_detector"]

        # Try to schedule appointment that's too short
        start_time = datetime(2025, 9, 22, 10, 0)  # Free slot
        end_time = datetime(
            2025, 9, 22, 10, 10
        )  # 10 minutes (less than 15 min minimum)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        # Should detect duration violation
        provider_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.PROVIDER_UNAVAILABLE.value
        ]
        duration_conflicts = [
            c for c in provider_conflicts if "too short" in c["description"]
        ]
        assert len(duration_conflicts) > 0

    @pytest.mark.asyncio
    async def test_different_providers_different_rules(
        self, integrated_services, mock_schedule_service
    ):
        """Test that different providers have different rules applied."""
        # Create separate schedules for different providers
        dr_jones_schedule = {
            "schedule": {"start_time": "08:00", "end_time": "17:00"},
            "slots": [
                {
                    "start": "2025-09-22T10:00:00",
                    "end": "2025-09-22T10:30:00",
                    "status": "free",
                }
            ],
        }

        mock_schedule_service.get_provider_schedules.return_value = [dr_jones_schedule]

        conflict_detector = integrated_services["conflict_detector"]

        # Test dr_jones (different buffer time and allowed types)
        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            # Test appointment type allowed for dr_jones but not dr_smith
            result_jones = await conflict_detector.check_conflicts(
                "dr_jones", start_time, end_time, "emergency"
            )

        # dr_jones allows emergency appointments
        provider_conflicts = [
            c
            for c in result_jones["conflicts"]
            if c["conflict_type"] == ConflictType.PROVIDER_UNAVAILABLE.value
        ]
        type_conflicts = [
            c for c in provider_conflicts if "does not accept" in c["description"]
        ]
        assert len(type_conflicts) == 0  # Should be allowed

    @pytest.mark.asyncio
    async def test_comprehensive_workflow(
        self, integrated_services, mock_schedule_service, realistic_schedule
    ):
        """Test complete workflow from conflict detection to suggestion selection."""
        mock_schedule_service.get_provider_schedules.return_value = [realistic_schedule]

        conflict_detector = integrated_services["conflict_detector"]
        time_suggester = integrated_services["time_suggester"]
        schedule_checker = integrated_services["schedule_checker"]

        # 1. Try to schedule appointment with conflicts
        start_time = datetime(2025, 9, 22, 10, 30)  # Conflicts with appt3
        end_time = datetime(2025, 9, 22, 11, 0)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            conflict_result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        assert conflict_result["has_conflicts"]

        # 2. Get alternative suggestions
        with patch(
            "src.services.time_suggester.log_audit_event", new_callable=AsyncMock
        ):
            suggestions = await time_suggester.suggest_alternative_times(
                "dr_smith", start_time, end_time, "consultation"
            )

        assert len(suggestions) > 0

        # 3. Verify first suggestion is actually available
        first_suggestion = suggestions[0]
        suggested_start = datetime.fromisoformat(first_suggestion["suggested_start"])
        suggested_end = datetime.fromisoformat(first_suggestion["suggested_end"])

        is_available = await schedule_checker.is_time_available(
            "dr_smith", suggested_start, suggested_end
        )
        assert is_available

        # 4. Verify suggestion doesn't have conflicts
        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            suggestion_conflicts = await conflict_detector.check_conflicts(
                "dr_smith", suggested_start, suggested_end, "consultation"
            )

        assert not suggestion_conflicts["has_blocking_conflicts"]

    @pytest.mark.asyncio
    async def test_weekend_scheduling_rules(
        self, integrated_services, mock_schedule_service
    ):
        """Test weekend scheduling with different operational hours."""
        saturday_schedule = {
            "schedule": {"start_time": "09:00", "end_time": "12:00"},
            "slots": [
                {
                    "start": "2025-09-20T09:00:00",
                    "end": "2025-09-20T09:30:00",
                    "status": "free",
                },
                {
                    "start": "2025-09-20T09:30:00",
                    "end": "2025-09-20T10:00:00",
                    "status": "free",
                },
            ],
        }

        mock_schedule_service.get_provider_schedules.return_value = [saturday_schedule]

        conflict_detector = integrated_services["conflict_detector"]

        # Valid Saturday appointment (within 9:00-12:00 hours)
        start_time = datetime(2025, 9, 20, 9, 30)  # Saturday 9:30 AM
        end_time = datetime(2025, 9, 20, 10, 0)  # Saturday 10:00 AM

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        # Should be allowed on Saturday during operational hours
        hours_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.OPERATIONAL_HOURS.value
        ]
        assert len(hours_conflicts) == 0

        # Invalid Saturday appointment (after 12:00)
        start_time = datetime(2025, 9, 20, 12, 30)  # Saturday 12:30 PM (after close)
        end_time = datetime(2025, 9, 20, 13, 0)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        # Should be blocked due to operational hours
        hours_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.OPERATIONAL_HOURS.value
        ]
        assert len(hours_conflicts) > 0

    @pytest.mark.asyncio
    async def test_holiday_conflict_detection(
        self, integrated_services, mock_schedule_service
    ):
        """Test holiday conflict detection."""
        holiday_schedule = {"slots": []}  # Empty schedule for holiday
        mock_schedule_service.get_provider_schedules.return_value = [holiday_schedule]

        conflict_detector = integrated_services["conflict_detector"]

        # Try to schedule on Christmas (configured as holiday)
        start_time = datetime(2025, 12, 25, 10, 0)  # Christmas Day
        end_time = datetime(2025, 12, 25, 10, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            result = await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        # Should detect holiday conflict
        holiday_conflicts = [
            c
            for c in result["conflicts"]
            if c["conflict_type"] == ConflictType.HOLIDAY.value
        ]
        assert len(holiday_conflicts) > 0

    @pytest.mark.asyncio
    async def test_cache_integration(
        self, integrated_services, mock_schedule_service, realistic_schedule
    ):
        """Test that caching works properly across integrated services."""
        mock_schedule_service.get_provider_schedules.return_value = [realistic_schedule]

        schedule_checker = integrated_services["schedule_checker"]
        conflict_detector = integrated_services["conflict_detector"]

        # First call should populate cache
        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            await conflict_detector.check_conflicts(
                "dr_smith", start_time, end_time, "consultation"
            )

        initial_call_count = mock_schedule_service.get_provider_schedules.call_count

        # Second call should use cache
        await schedule_checker.is_time_available("dr_smith", start_time, end_time)

        # Should not make additional EMR calls due to caching
        assert (
            mock_schedule_service.get_provider_schedules.call_count
            == initial_call_count
        )

    @pytest.mark.asyncio
    async def test_error_propagation(self, integrated_services, mock_schedule_service):
        """Test error handling and propagation across integrated services."""
        mock_schedule_service.get_provider_schedules.side_effect = Exception(
            "EMR service unavailable"
        )

        conflict_detector = integrated_services["conflict_detector"]

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        with patch(
            "src.services.conflict_detector.log_audit_event", new_callable=AsyncMock
        ):
            with pytest.raises(Exception):  # Should propagate the error
                await conflict_detector.check_conflicts(
                    "dr_smith", start_time, end_time, "consultation"
                )
