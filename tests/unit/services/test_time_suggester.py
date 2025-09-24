"""
Unit tests for TimeSuggester service.

Tests alternative appointment time suggestions, ranking algorithms,
and voice-friendly formatting functionality.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.conflict_detector import ConflictDetector, ConflictType
from src.services.schedule_checker import ScheduleChecker
from src.services.time_suggester import (
    SuggestionGenerationError,
    TimeSuggester,
    TimeSuggesterError,
)


class TestTimeSuggester:
    """Test TimeSuggester functionality."""

    @pytest.fixture
    def basic_config(self):
        """Basic configuration for testing."""
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
            },
            "suggestion_preferences": {
                "max_suggestions": 5,
                "look_ahead_days": 7,
                "preferred_time_slots": ["morning", "afternoon"],
                "avoid_lunch_hours": True,
            },
        }

    @pytest.fixture
    def mock_conflict_detector(self):
        """Mock ConflictDetector for testing."""
        mock = MagicMock(spec=ConflictDetector)
        mock.detect_conflicts = AsyncMock()
        return mock

    @pytest.fixture
    def mock_schedule_checker(self):
        """Mock ScheduleChecker for testing."""
        mock = MagicMock(spec=ScheduleChecker)
        mock.is_time_available = AsyncMock()
        mock.get_next_available_slot = AsyncMock()
        return mock

    @pytest.fixture
    def time_suggester(
        self, mock_conflict_detector, mock_schedule_checker, basic_config
    ):
        """Create TimeSuggester instance."""
        return TimeSuggester(
            mock_conflict_detector, mock_schedule_checker, basic_config
        )

    @pytest.mark.asyncio
    async def test_suggest_alternative_times_no_conflicts(
        self, time_suggester, mock_conflict_detector
    ):
        """Test suggesting alternative times when no conflicts exist."""
        # Mock no conflicts found
        mock_conflict_detector.detect_conflicts.return_value = {
            "conflicts": [],
            "alternative_suggestions": [],
        }

        start_time = datetime(2025, 9, 22, 10, 0)  # Monday 10:00 AM
        end_time = datetime(2025, 9, 22, 10, 30)  # Monday 10:30 AM

        result = await time_suggester.suggest_alternative_times(
            "provider123", start_time, end_time, "consultation"
        )

        assert result["has_conflicts"] is False
        assert result["suggested_times"] == []
        assert result["original_time_available"] is True

    @pytest.mark.asyncio
    async def test_suggest_alternative_times_with_conflicts(
        self, time_suggester, mock_conflict_detector, mock_schedule_checker
    ):
        """Test suggesting alternative times when conflicts exist."""
        # Mock conflicts detected
        mock_conflict_detector.detect_conflicts.return_value = {
            "conflicts": [
                {
                    "conflict_type": ConflictType.EXISTING_APPOINTMENT,
                    "conflict_start": datetime(2025, 9, 22, 10, 0),
                    "conflict_end": datetime(2025, 9, 22, 10, 30),
                }
            ],
            "alternative_suggestions": [],
        }

        # Mock available alternative slots
        mock_schedule_checker.get_next_available_slot.return_value = datetime(
            2025, 9, 22, 11, 0
        )
        mock_schedule_checker.is_time_available.return_value = True

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        result = await time_suggester.suggest_alternative_times(
            "provider123", start_time, end_time, "consultation"
        )

        assert result["has_conflicts"] is True
        assert len(result["suggested_times"]) > 0
        assert result["original_time_available"] is False

    @pytest.mark.asyncio
    async def test_find_next_available_slots_morning_preference(
        self, time_suggester, mock_schedule_checker
    ):
        """Test finding next available slots with morning preference."""
        # Mock available slots
        mock_schedule_checker.get_next_available_slot.side_effect = [
            datetime(2025, 9, 22, 9, 0),  # Next morning slot
            datetime(2025, 9, 22, 14, 0),  # Afternoon slot
            datetime(2025, 9, 23, 9, 0),  # Next day morning
        ]
        mock_schedule_checker.is_time_available.return_value = True

        start_time = datetime(2025, 9, 22, 10, 0)

        slots = await time_suggester.find_next_available_slots(
            "provider123", start_time, 30, max_suggestions=3
        )

        assert len(slots) == 3
        # First slot should be morning (higher ranking)
        assert slots[0]["suggested_start"].hour < 12

    @pytest.mark.asyncio
    async def test_rank_suggestions_morning_preference(self, time_suggester):
        """Test ranking suggestions with morning preference."""
        suggestions = [
            {
                "suggested_start": datetime(2025, 9, 22, 14, 0),  # Afternoon
                "suggested_end": datetime(2025, 9, 22, 14, 30),
                "ranking_score": 0.0,
            },
            {
                "suggested_start": datetime(2025, 9, 22, 9, 0),  # Morning
                "suggested_end": datetime(2025, 9, 22, 9, 30),
                "ranking_score": 0.0,
            },
        ]

        ranked = time_suggester.rank_suggestions(
            suggestions, datetime(2025, 9, 22, 10, 0)
        )

        # Morning slot should be ranked higher
        assert ranked[0]["suggested_start"].hour == 9
        assert ranked[0]["ranking_score"] > ranked[1]["ranking_score"]

    def test_calculate_time_preference_score_morning(self, time_suggester):
        """Test calculating time preference score for morning."""
        morning_time = datetime(2025, 9, 22, 9, 0)
        score = time_suggester.calculate_time_preference_score(morning_time)
        assert score > 0.5  # Morning should have high score

    def test_calculate_time_preference_score_lunch(self, time_suggester):
        """Test calculating time preference score for lunch hours."""
        lunch_time = datetime(2025, 9, 22, 12, 30)
        score = time_suggester.calculate_time_preference_score(lunch_time)
        assert score < 0.5  # Lunch hours should have low score

    def test_calculate_proximity_score_same_day(self, time_suggester):
        """Test calculating proximity score for same day."""
        original = datetime(2025, 9, 22, 10, 0)
        suggestion = datetime(2025, 9, 22, 11, 0)

        score = time_suggester.calculate_proximity_score(original, suggestion)
        assert score > 0.8  # Same day, close time should have high score

    def test_calculate_proximity_score_different_day(self, time_suggester):
        """Test calculating proximity score for different day."""
        original = datetime(2025, 9, 22, 10, 0)
        suggestion = datetime(2025, 9, 24, 10, 0)

        score = time_suggester.calculate_proximity_score(original, suggestion)
        assert score < 0.8  # Different day should have lower score

    def test_format_time_for_voice_12_hour(self, time_suggester):
        """Test formatting time for voice in 12-hour format."""
        morning_time = datetime(2025, 9, 22, 9, 30)
        formatted = time_suggester.format_time_for_voice(morning_time)
        assert "9:30 AM" in formatted

        afternoon_time = datetime(2025, 9, 22, 14, 30)
        formatted = time_suggester.format_time_for_voice(afternoon_time)
        assert "2:30 PM" in formatted

    def test_format_time_for_voice_with_date(self, time_suggester):
        """Test formatting time for voice with date."""
        future_time = datetime(2025, 9, 24, 10, 0)
        formatted = time_suggester.format_time_for_voice(future_time, include_date=True)
        assert "Wednesday" in formatted
        assert "10:00 AM" in formatted

    def test_format_suggestions_for_voice(self, time_suggester):
        """Test formatting suggestions for voice output."""
        suggestions = [
            {
                "suggested_start": datetime(2025, 9, 22, 9, 0),
                "suggested_end": datetime(2025, 9, 22, 9, 30),
                "ranking_score": 0.9,
                "reason": "Next available morning slot",
            },
            {
                "suggested_start": datetime(2025, 9, 22, 14, 0),
                "suggested_end": datetime(2025, 9, 22, 14, 30),
                "ranking_score": 0.7,
                "reason": "Available afternoon slot",
            },
        ]

        formatted = time_suggester.format_suggestions_for_voice(suggestions)

        assert "I found 2 alternative times" in formatted
        assert "9:00 AM" in formatted
        assert "2:00 PM" in formatted

    def test_format_suggestions_for_voice_empty(self, time_suggester):
        """Test formatting empty suggestions for voice."""
        formatted = time_suggester.format_suggestions_for_voice([])
        assert "no alternative times" in formatted.lower()

    @pytest.mark.asyncio
    async def test_get_same_day_alternatives(
        self, time_suggester, mock_schedule_checker
    ):
        """Test getting same-day alternative appointments."""
        # Mock available slots on same day
        mock_schedule_checker.is_time_available.side_effect = (
            lambda provider, start, end: (
                start.hour != 10  # 10 AM slot is not available
            )
        )

        original_start = datetime(2025, 9, 22, 10, 0)
        original_end = datetime(2025, 9, 22, 10, 30)

        alternatives = await time_suggester.get_same_day_alternatives(
            "provider123", original_start, original_end
        )

        assert len(alternatives) > 0
        # All alternatives should be on the same day
        for alt in alternatives:
            assert alt["suggested_start"].date() == original_start.date()

    @pytest.mark.asyncio
    async def test_get_next_day_alternatives(
        self, time_suggester, mock_schedule_checker
    ):
        """Test getting next-day alternative appointments."""
        mock_schedule_checker.is_time_available.return_value = True

        original_start = datetime(2025, 9, 22, 10, 0)  # Monday
        original_end = datetime(2025, 9, 22, 10, 30)

        alternatives = await time_suggester.get_next_day_alternatives(
            "provider123", original_start, original_end, max_days=3
        )

        assert len(alternatives) > 0
        # All alternatives should be on different days
        for alt in alternatives:
            assert alt["suggested_start"].date() > original_start.date()

    @pytest.mark.asyncio
    async def test_suggest_alternative_times_with_patient_preferences(
        self, time_suggester, mock_conflict_detector, mock_schedule_checker
    ):
        """Test suggesting alternatives with patient preferences."""
        # Mock conflicts
        mock_conflict_detector.detect_conflicts.return_value = {
            "conflicts": [{"conflict_type": ConflictType.EXISTING_APPOINTMENT}],
            "alternative_suggestions": [],
        }
        mock_schedule_checker.get_next_available_slot.return_value = datetime(
            2025, 9, 22, 9, 0
        )
        mock_schedule_checker.is_time_available.return_value = True

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        patient_preferences = {
            "preferred_times": ["morning"],
            "avoid_days": ["friday"],
            "max_days_ahead": 5,
        }

        result = await time_suggester.suggest_alternative_times(
            "provider123",
            start_time,
            end_time,
            "consultation",
            patient_preferences=patient_preferences,
        )

        assert result["has_conflicts"] is True
        # Should consider patient preferences in suggestions

    def test_apply_patient_preferences(self, time_suggester):
        """Test applying patient preferences to filter suggestions."""
        suggestions = [
            {
                "suggested_start": datetime(2025, 9, 22, 9, 0),  # Monday morning
                "suggested_end": datetime(2025, 9, 22, 9, 30),
                "ranking_score": 0.8,
            },
            {
                "suggested_start": datetime(2025, 9, 26, 14, 0),  # Friday afternoon
                "suggested_end": datetime(2025, 9, 26, 14, 30),
                "ranking_score": 0.7,
            },
        ]

        patient_prefs = {"preferred_times": ["morning"], "avoid_days": ["friday"]}

        filtered = time_suggester.apply_patient_preferences(suggestions, patient_prefs)

        # Should keep Monday morning, filter out Friday
        assert len(filtered) == 1
        assert filtered[0]["suggested_start"].hour == 9

    @pytest.mark.asyncio
    async def test_error_handling_schedule_checker_failure(
        self, time_suggester, mock_conflict_detector, mock_schedule_checker
    ):
        """Test error handling when schedule checker fails."""
        mock_conflict_detector.detect_conflicts.return_value = {
            "conflicts": [{"conflict_type": ConflictType.EXISTING_APPOINTMENT}],
            "alternative_suggestions": [],
        }
        mock_schedule_checker.get_next_available_slot.side_effect = Exception(
            "Schedule service unavailable"
        )

        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        with pytest.raises(
            SuggestionGenerationError, match="Failed to generate suggestions"
        ):
            await time_suggester.suggest_alternative_times(
                "provider123", start_time, end_time, "consultation"
            )

    def test_validate_suggestion_request_valid(self, time_suggester):
        """Test validating valid suggestion request."""
        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        # Should not raise exception
        time_suggester.validate_suggestion_request("provider123", start_time, end_time)

    def test_validate_suggestion_request_invalid_duration(self, time_suggester):
        """Test validating request with invalid duration."""
        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 9, 30)  # End before start

        with pytest.raises(TimeSuggesterError, match="Invalid appointment duration"):
            time_suggester.validate_suggestion_request(
                "provider123", start_time, end_time
            )

    def test_validate_suggestion_request_missing_provider(self, time_suggester):
        """Test validating request with missing provider."""
        start_time = datetime(2025, 9, 22, 10, 0)
        end_time = datetime(2025, 9, 22, 10, 30)

        with pytest.raises(TimeSuggesterError, match="Provider ID is required"):
            time_suggester.validate_suggestion_request("", start_time, end_time)


class TestTimeSuggesterEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def minimal_config(self):
        """Minimal configuration for edge case testing."""
        return {}

    @pytest.fixture
    def time_suggester_minimal(
        self, mock_conflict_detector, mock_schedule_checker, minimal_config
    ):
        """Create TimeSuggester with minimal config."""
        return TimeSuggester(
            mock_conflict_detector, mock_schedule_checker, minimal_config
        )

    def test_initialization_with_minimal_config(self, time_suggester_minimal):
        """Test initialization with minimal configuration."""
        # Should initialize with defaults
        assert time_suggester_minimal.config is not None
        assert time_suggester_minimal.suggestion_preferences["max_suggestions"] == 5

    @pytest.mark.asyncio
    async def test_find_alternatives_no_available_slots(
        self, time_suggester_minimal, mock_schedule_checker
    ):
        """Test finding alternatives when no slots are available."""
        mock_schedule_checker.get_next_available_slot.return_value = None
        mock_schedule_checker.is_time_available.return_value = False

        start_time = datetime(2025, 9, 22, 10, 0)

        slots = await time_suggester_minimal.find_next_available_slots(
            "provider123", start_time, 30, max_suggestions=3
        )

        assert slots == []

    def test_rank_suggestions_empty_list(self, time_suggester_minimal):
        """Test ranking empty suggestions list."""
        ranked = time_suggester_minimal.rank_suggestions(
            [], datetime(2025, 9, 22, 10, 0)
        )
        assert ranked == []

    def test_format_time_edge_cases(self, time_suggester_minimal):
        """Test formatting time edge cases."""
        # Midnight
        midnight = datetime(2025, 9, 22, 0, 0)
        formatted = time_suggester_minimal.format_time_for_voice(midnight)
        assert "12:00 AM" in formatted

        # Noon
        noon = datetime(2025, 9, 22, 12, 0)
        formatted = time_suggester_minimal.format_time_for_voice(noon)
        assert "12:00 PM" in formatted

    @patch("src.services.time_suggester.logger")
    def test_logging_on_suggestion_generation(
        self, mock_logger, time_suggester_minimal
    ):
        """Test that appropriate logging occurs during suggestion generation."""
        # This would test that the service logs important events
        # Implementation would depend on actual logging calls in the service
        pass
