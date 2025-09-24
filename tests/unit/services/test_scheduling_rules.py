"""
Unit tests for SchedulingRulesManager service.

Tests buffer time management, provider-specific rules, operational hours,
and scheduling rule validation functionality.
"""

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.scheduling_rules import (
    RuleValidationError,
    SchedulingRulesError,
    SchedulingRulesManager,
)


class TestSchedulingRulesManager:
    """Test SchedulingRulesManager functionality."""

    @pytest.fixture
    def basic_config(self):
        """Basic configuration for testing."""
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
                    "provider123": {
                        "default_buffer_minutes": 20,
                        "buffer_times": {"consultation": 15, "surgery": 30},
                        "appointment_durations": {
                            "consultation": {"min_minutes": 15, "max_minutes": 60},
                            "surgery": {"min_minutes": 60, "max_minutes": 180},
                        },
                        "breaks": [{"start": "12:00", "end": "13:00", "name": "Lunch"}],
                    }
                },
            }
        }

    @pytest.fixture
    def rules_manager(self, basic_config):
        """Create SchedulingRulesManager instance."""
        return SchedulingRulesManager(basic_config)

    def test_initialization_with_empty_config(self):
        """Test initialization with empty configuration."""
        rules_manager = SchedulingRulesManager({})

        # Should initialize with defaults
        assert rules_manager.get_buffer_time("any_provider") == 15
        assert (
            rules_manager.get_operational_hours(datetime(2025, 9, 22).date())
            is not None
        )

    def test_get_buffer_time_default(self, rules_manager):
        """Test getting default buffer time."""
        result = rules_manager.get_buffer_time("unknown_provider")
        assert result == 15

    def test_get_buffer_time_provider_specific(self, rules_manager):
        """Test getting provider-specific buffer time."""
        result = rules_manager.get_buffer_time("provider123")
        assert result == 20

    def test_get_buffer_time_appointment_type_specific(self, rules_manager):
        """Test getting appointment type specific buffer time."""
        result = rules_manager.get_buffer_time("provider123", "consultation")
        assert result == 15

        result = rules_manager.get_buffer_time("provider123", "surgery")
        assert result == 30

    def test_get_appointment_duration_limits_default(self, rules_manager):
        """Test getting default duration limits."""
        result = rules_manager.get_appointment_duration_limits("unknown_provider")
        assert result == {"min_minutes": None, "max_minutes": None}

    def test_get_appointment_duration_limits_provider_specific(self, rules_manager):
        """Test getting provider-specific duration limits."""
        result = rules_manager.get_appointment_duration_limits(
            "provider123", "consultation"
        )
        assert result == {"min_minutes": 15, "max_minutes": 60}

        result = rules_manager.get_appointment_duration_limits("provider123", "surgery")
        assert result == {"min_minutes": 60, "max_minutes": 180}

    def test_get_operational_hours_weekday(self, rules_manager):
        """Test getting operational hours for weekday."""
        monday = datetime(2025, 9, 22).date()  # Monday
        result = rules_manager.get_operational_hours(monday)
        assert result == {"open": "08:00", "close": "17:00"}

    def test_get_operational_hours_saturday(self, rules_manager):
        """Test getting operational hours for Saturday."""
        saturday = datetime(2025, 9, 27).date()  # Saturday
        result = rules_manager.get_operational_hours(saturday)
        assert result == {"open": "09:00", "close": "12:00"}

    def test_get_operational_hours_sunday_closed(self, rules_manager):
        """Test getting operational hours for closed Sunday."""
        sunday = datetime(2025, 9, 28).date()  # Sunday
        result = rules_manager.get_operational_hours(sunday)
        assert result is None

    def test_get_provider_breaks(self, rules_manager):
        """Test getting provider break times."""
        monday = datetime(2025, 9, 22).date()
        breaks = rules_manager.get_provider_breaks("provider123", monday)
        assert len(breaks) == 1
        assert breaks[0]["start"] == "12:00"
        assert breaks[0]["end"] == "13:00"
        assert breaks[0]["name"] == "Lunch"

    def test_get_provider_breaks_none(self, rules_manager):
        """Test getting break times for provider with none."""
        monday = datetime(2025, 9, 22).date()
        breaks = rules_manager.get_provider_breaks("unknown_provider", monday)
        assert breaks == []

    def test_is_appointment_type_allowed_default(self, rules_manager):
        """Test appointment type checking with no restrictions."""
        result = rules_manager.is_appointment_type_allowed(
            "unknown_provider", "consultation"
        )
        assert result is True

    def test_is_appointment_type_allowed_with_restrictions(self):
        """Test appointment type checking with restrictions."""
        config = {
            "scheduling_rules": {
                "provider_preferences": {
                    "provider123": {
                        "allowed_appointment_types": ["consultation", "checkup"]
                    }
                }
            }
        }
        rules_manager = SchedulingRulesManager(config)

        assert (
            rules_manager.is_appointment_type_allowed("provider123", "consultation")
            is True
        )
        assert (
            rules_manager.is_appointment_type_allowed("provider123", "surgery") is False
        )

    @pytest.mark.asyncio
    async def test_validate_appointment_rules_valid(self, rules_manager):
        """Test validating valid appointment."""
        start_time = datetime(2025, 9, 22, 10, 0)  # Monday 10:00 AM
        end_time = datetime(2025, 9, 22, 10, 30)  # Monday 10:30 AM

        result = await rules_manager.validate_appointment_rules(
            "provider123", start_time, end_time, "consultation"
        )

        assert result["valid"] is True
        assert len(result["violations"]) == 0

    @pytest.mark.asyncio
    async def test_validate_appointment_rules_outside_hours(self, rules_manager):
        """Test validating appointment outside operational hours."""
        start_time = datetime(2025, 9, 22, 7, 0)  # Monday 7:00 AM (before open)
        end_time = datetime(2025, 9, 22, 7, 30)  # Monday 7:30 AM

        result = await rules_manager.validate_appointment_rules(
            "provider123", start_time, end_time, "consultation"
        )

        assert result["valid"] is False
        assert any("operational hours" in v["message"] for v in result["violations"])

    @pytest.mark.asyncio
    async def test_validate_appointment_rules_during_break(self, rules_manager):
        """Test validating appointment during provider break."""
        start_time = datetime(2025, 9, 22, 12, 15)  # Monday 12:15 PM (during lunch)
        end_time = datetime(2025, 9, 22, 12, 45)  # Monday 12:45 PM

        result = await rules_manager.validate_appointment_rules(
            "provider123", start_time, end_time, "consultation"
        )

        assert result["valid"] is False
        assert any("break time" in v["message"] for v in result["violations"])

    @pytest.mark.asyncio
    async def test_update_provider_preferences(self, rules_manager):
        """Test updating provider preferences."""
        new_prefs = {"default_buffer_minutes": 25}

        with patch("src.services.scheduling_rules.get_config") as mock_get, patch(
            "src.services.scheduling_rules.set_config"
        ) as mock_set, patch(
            "src.services.scheduling_rules.log_audit_event"
        ) as mock_audit:
            mock_get.return_value = {"scheduling_rules": rules_manager.rules}

            result = await rules_manager.update_provider_preferences(
                "provider123", new_prefs
            )

            assert result is True
            assert rules_manager.get_buffer_time("provider123") == 25
            mock_set.assert_called_once()
            mock_audit.assert_called_once()

    def test_get_all_rules(self, rules_manager):
        """Test getting all rules."""
        rules = rules_manager.get_all_rules()
        assert "default_buffer_minutes" in rules
        assert "operational_hours" in rules
        assert "provider_preferences" in rules

    @patch("src.services.scheduling_rules.logger")
    def test_error_handling_in_get_buffer_time(self, mock_logger, rules_manager):
        """Test error handling in get_buffer_time method."""
        # Corrupt the rules to force an error
        rules_manager.rules = None

        result = rules_manager.get_buffer_time("provider123")
        assert result == 15  # Should return default
        mock_logger.warning.assert_called()

    @patch("src.services.scheduling_rules.logger")
    def test_error_handling_in_get_duration_limits(self, mock_logger, rules_manager):
        """Test error handling in get_appointment_duration_limits method."""
        # Corrupt the rules to force an error
        rules_manager.rules = None

        result = rules_manager.get_appointment_duration_limits("provider123")
        assert result == {"min_minutes": None, "max_minutes": None}
        mock_logger.warning.assert_called()


class TestSchedulingRulesEdgeCases:
    """Test edge cases and error conditions."""

    def test_malformed_operational_hours(self):
        """Test handling of malformed operational hours."""
        config = {
            "scheduling_rules": {"operational_hours": {"monday": "invalid_format"}}
        }
        rules_manager = SchedulingRulesManager(config)

        monday = datetime(2025, 9, 22).date()
        result = rules_manager.get_operational_hours(monday)

        # Should handle gracefully and return default
        assert result is not None

    def test_empty_provider_preferences(self):
        """Test handling of empty provider preferences."""
        config = {"scheduling_rules": {"provider_preferences": {"provider123": {}}}}
        rules_manager = SchedulingRulesManager(config)

        # Should use defaults
        assert rules_manager.get_buffer_time("provider123") == 15

    def test_invalid_preferences_format(self):
        """Test validation of invalid preferences format."""
        rules_manager = SchedulingRulesManager({})

        # Invalid preferences should raise validation error
        invalid_prefs = {"working_hours": {"monday": {"open": "25:00"}}}  # Invalid hour

        with pytest.raises(RuleValidationError):
            rules_manager._validate_preferences_format(invalid_prefs)

    def test_times_overlap_utility(self):
        """Test the _times_overlap utility method."""
        rules_manager = SchedulingRulesManager({})

        # Overlapping times
        start1 = datetime(2025, 9, 22, 10, 0)
        end1 = datetime(2025, 9, 22, 11, 0)
        start2 = datetime(2025, 9, 22, 10, 30)
        end2 = datetime(2025, 9, 22, 11, 30)

        assert rules_manager._times_overlap(start1, end1, start2, end2) is True

        # Non-overlapping times
        start3 = datetime(2025, 9, 22, 12, 0)
        end3 = datetime(2025, 9, 22, 13, 0)

        assert rules_manager._times_overlap(start1, end1, start3, end3) is False

    def test_hash_identifier_utility(self):
        """Test the _hash_identifier utility method."""
        rules_manager = SchedulingRulesManager({})

        # Should return consistent hash
        hash1 = rules_manager._hash_identifier("provider123")
        hash2 = rules_manager._hash_identifier("provider123")

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hash length
