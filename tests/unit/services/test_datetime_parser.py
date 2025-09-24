"""
Unit tests for DateTime Parser service.
Tests flexible date/time parsing including relative and absolute formats.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest

from src.services.datetime_parser import DateTimeParser, ParsedDateTime


class TestDateTimeParser:
    """Test cases for DateTime Parser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DateTimeParser()

    def test_initialization(self):
        """Test parser initialization."""
        assert self.parser is not None
        assert hasattr(self.parser, "business_hours")
        assert hasattr(self.parser, "day_names")
        assert hasattr(self.parser, "month_names")

    def test_parse_relative_today(self):
        """Test parsing 'today'."""
        with patch("src.services.datetime_parser.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 14, 30)
            mock_dt.now.return_value = mock_now

            result = self.parser.parse_datetime("I want an appointment today")

            assert result.datetime_value is not None
            assert result.date_part == mock_now.date()
            assert result.is_relative
            assert result.confidence > 0.8
            assert result.parsing_method == "relative_today"

    def test_parse_relative_tomorrow(self):
        """Test parsing 'tomorrow'."""
        with patch("src.services.datetime_parser.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 14, 30)
            mock_dt.now.return_value = mock_now

            result = self.parser.parse_datetime("I need to see the doctor tomorrow")

            assert result.datetime_value is not None
            expected_date = (mock_now + timedelta(days=1)).date()
            assert result.date_part == expected_date
            assert result.is_relative
            assert result.confidence > 0.8
            assert result.parsing_method == "relative_tomorrow"

    def test_parse_relative_next_week(self):
        """Test parsing 'next week'."""
        with patch("src.services.datetime_parser.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 14, 30)  # Monday
            mock_dt.now.return_value = mock_now

            result = self.parser.parse_datetime("Can I get an appointment next week?")

            assert result.datetime_value is not None
            assert result.is_relative
            assert result.confidence > 0.7
            assert result.parsing_method == "relative_next_week"

    def test_parse_absolute_month_day(self):
        """Test parsing absolute month and day."""
        test_cases = ["January 15th", "Jan 15", "March 3rd, 2024", "December 25th"]

        for test_case in test_cases:
            result = self.parser.parse_datetime(f"I want an appointment on {test_case}")
            assert result.datetime_value is not None
            assert not result.is_relative
            assert result.confidence > 0.8
            assert result.parsing_method == "absolute_month_day"

    def test_parse_absolute_slash_format(self):
        """Test parsing MM/DD and MM/DD/YYYY formats."""
        test_cases = ["12/25", "03/15", "12/25/2024", "1/1/2025"]

        for test_case in test_cases:
            result = self.parser.parse_datetime(f"Schedule me for {test_case}")
            assert result.datetime_value is not None
            assert not result.is_relative
            assert result.confidence > 0.7
            assert result.parsing_method == "absolute_slash_format"

    def test_parse_day_name(self):
        """Test parsing day names."""
        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        with patch("src.services.datetime_parser.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 14, 30)  # Monday
            mock_dt.now.return_value = mock_now

            for day_name in day_names:
                result = self.parser.parse_datetime(f"Can I come in on {day_name}?")
                assert result.datetime_value is not None
                assert result.is_relative
                assert result.confidence > 0.7
                assert result.parsing_method == "day_name"

    def test_parse_days_ahead(self):
        """Test parsing 'in X days' format."""
        with patch("src.services.datetime_parser.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 14, 30)
            mock_dt.now.return_value = mock_now

            result = self.parser.parse_datetime("I need an appointment in 5 days")

            assert result.datetime_value is not None
            expected_date = (mock_now + timedelta(days=5)).date()
            assert result.date_part == expected_date
            assert result.is_relative
            assert result.confidence > 0.7
            assert result.parsing_method == "relative_days_ahead"

    def test_parse_time_hhmm_format(self):
        """Test parsing HH:MM time format."""
        test_cases = [
            ("2:30 pm", time(14, 30)),
            ("10:00 am", time(10, 0)),
            ("12:00 pm", time(12, 0)),
            ("12:00 am", time(0, 0)),
            ("11:45", time(11, 45)),
        ]

        for time_str, expected_time in test_cases:
            result = self.parser._parse_time_component(f"at {time_str}")
            assert result == expected_time

    def test_parse_time_hour_ampm(self):
        """Test parsing H am/pm format."""
        test_cases = [
            ("3pm", time(15, 0)),
            ("10am", time(10, 0)),
            ("12pm", time(12, 0)),
            ("12am", time(0, 0)),
        ]

        for time_str, expected_time in test_cases:
            result = self.parser._parse_time_component(time_str)
            assert result == expected_time

    def test_parse_time_periods(self):
        """Test parsing time periods."""
        test_cases = [
            ("morning", time(9, 0)),
            ("afternoon", time(14, 0)),
            ("evening", time(17, 0)),
            ("noon", time(12, 0)),
        ]

        for period, expected_time in test_cases:
            result = self.parser._parse_time_component(f"in the {period}")
            assert result == expected_time

    def test_parse_word_time(self):
        """Test parsing time expressed in words."""
        test_cases = [
            ("three thirty", time(3, 30)),
            ("ten fifteen", time(10, 15)),
            ("two forty", time(2, 40)),  # Valid minute - 40 is valid
        ]

        for time_str, expected_time in test_cases:
            result = self.parser._parse_word_time(time_str)
            assert result == expected_time

    def test_parse_datetime_with_time(self):
        """Test parsing date and time together."""
        with patch("src.services.datetime_parser.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 14, 30)
            mock_dt.now.return_value = mock_now

            result = self.parser.parse_datetime("I want an appointment tomorrow at 3pm")

            assert result.datetime_value is not None
            assert result.time_part == time(15, 0)
            assert result.date_part == (mock_now + timedelta(days=1)).date()
            assert result.is_relative

    def test_parse_time_only_defaults_to_tomorrow(self):
        """Test that time-only parsing defaults to tomorrow."""
        with patch("src.services.datetime_parser.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 14, 30)
            mock_dt.now.return_value = mock_now

            result = self.parser.parse_datetime("Can I come in at 3pm?")

            assert result.datetime_value is not None
            assert result.time_part == time(15, 0)
            expected_date = (mock_now + timedelta(days=1)).date()
            assert result.date_part == expected_date
            assert result.parsing_method == "time_only_default_tomorrow"

    def test_validate_business_hours_valid(self):
        """Test validation of valid business hours."""
        # Tuesday at 10 AM
        valid_dt = datetime(2024, 1, 16, 10, 0)  # Tuesday
        is_valid, reason = self.parser.validate_business_hours(valid_dt)
        assert is_valid
        assert "Valid" in reason

    def test_validate_business_hours_weekend(self):
        """Test validation fails for weekends."""
        # Saturday
        weekend_dt = datetime(2024, 1, 13, 10, 0)  # Saturday
        is_valid, reason = self.parser.validate_business_hours(weekend_dt)
        assert not is_valid
        assert "weekend" in reason.lower()

    def test_validate_business_hours_before_hours(self):
        """Test validation fails before business hours."""
        # Tuesday at 7 AM (before 8 AM)
        early_dt = datetime(2024, 1, 16, 7, 0)
        is_valid, reason = self.parser.validate_business_hours(early_dt)
        assert not is_valid
        assert "before business hours" in reason.lower()

    def test_validate_business_hours_after_hours(self):
        """Test validation fails after business hours."""
        # Tuesday at 6 PM (after 5 PM)
        late_dt = datetime(2024, 1, 16, 18, 0)
        is_valid, reason = self.parser.validate_business_hours(late_dt)
        assert not is_valid
        assert "after business hours" in reason.lower()

    def test_validate_business_hours_lunch_time(self):
        """Test validation fails during lunch hour."""
        # Tuesday at 12:30 PM (lunch time)
        lunch_dt = datetime(2024, 1, 16, 12, 30)
        is_valid, reason = self.parser.validate_business_hours(lunch_dt)
        assert not is_valid
        assert "lunch" in reason.lower()

    def test_suggest_alternative_times(self):
        """Test alternative time suggestions."""
        # Invalid time: Saturday at 10 AM
        invalid_dt = datetime(2024, 1, 13, 10, 0)  # Saturday

        suggestions = self.parser.suggest_alternative_times(invalid_dt)

        assert len(suggestions) > 0
        # All suggestions should be valid business hours
        for suggestion in suggestions:
            is_valid, _ = self.parser.validate_business_hours(suggestion)
            assert is_valid

    def test_format_datetime_human(self):
        """Test human-readable datetime formatting."""
        dt = datetime(2024, 1, 15, 14, 30)  # Monday, January 15, 2024 at 2:30 PM

        formatted = self.parser.format_datetime_human(dt)

        assert "Monday" in formatted
        assert "January 15, 2024" in formatted
        assert "2:30 PM" in formatted

    def test_edge_cases_invalid_dates(self):
        """Test handling of invalid date inputs."""
        invalid_inputs = [
            "February 30th",  # Invalid date
            "13/45",  # Invalid MM/DD
            "abc def",  # No date information
            "",  # Empty string
        ]

        for invalid_input in invalid_inputs:
            result = self.parser.parse_datetime(invalid_input)
            # Should either return None datetime or low confidence
            assert result.datetime_value is None or result.confidence < 0.5

    def test_past_date_handling(self):
        """Test handling of past dates."""
        with patch("src.services.datetime_parser.datetime") as mock_dt, patch(
            "src.services.datetime_parser.date"
        ) as mock_date:
            mock_now = datetime(2024, 6, 15, 14, 30)  # June 15, 2024
            mock_dt.now.return_value = mock_now
            mock_date.today.return_value = mock_now.date()

            # Mock datetime.combine to return actual datetime
            def mock_combine(date_part, time_part):
                return datetime.combine(date_part, time_part)

            mock_dt.combine = mock_combine

            # Test past month in same year - should assume next year
            result = self.parser.parse_datetime("I want an appointment on January 15th")

            assert result.datetime_value is not None
            assert result.datetime_value.year == 2025  # Should be next year

    def test_business_hours_configuration(self):
        """Test business hours configuration."""
        assert self.parser.business_hours["start"] == time(8, 0)
        assert self.parser.business_hours["end"] == time(17, 0)
        assert self.parser.business_hours["lunch_start"] == time(12, 0)
        assert self.parser.business_hours["lunch_end"] == time(13, 0)

    def test_day_names_mapping(self):
        """Test day names mapping."""
        assert self.parser.day_names["monday"] == 0
        assert self.parser.day_names["mon"] == 0
        assert self.parser.day_names["sunday"] == 6
        assert self.parser.day_names["sun"] == 6

    def test_month_names_mapping(self):
        """Test month names mapping."""
        assert self.parser.month_names["january"] == 1
        assert self.parser.month_names["jan"] == 1
        assert self.parser.month_names["december"] == 12
        assert self.parser.month_names["dec"] == 12

    def test_complex_parsing_scenarios(self):
        """Test complex parsing scenarios."""
        with patch("src.services.datetime_parser.datetime") as mock_dt:
            mock_now = datetime(2024, 1, 15, 14, 30)  # Monday
            mock_dt.now.return_value = mock_now

            complex_cases = [
                "next Friday at 2:30 pm",
                "January 25th in the morning",
                "tomorrow afternoon",
                "Thursday at noon",
            ]

            for case in complex_cases:
                result = self.parser.parse_datetime(case)
                assert result.datetime_value is not None
                assert result.confidence > 0.5


class TestParsedDateTime:
    """Test cases for ParsedDateTime data class."""

    def test_parsed_datetime_initialization(self):
        """Test ParsedDateTime initialization."""
        dt = datetime(2024, 1, 15, 14, 30)
        parsed = ParsedDateTime(
            datetime_value=dt,
            is_relative=True,
            original_text="tomorrow at 2:30pm",
            confidence=0.9,
            parsing_method="relative_tomorrow",
        )

        assert parsed.datetime_value == dt
        assert parsed.is_relative
        assert parsed.original_text == "tomorrow at 2:30pm"
        assert parsed.confidence == 0.9
        assert parsed.parsing_method == "relative_tomorrow"

    def test_parsed_datetime_defaults(self):
        """Test ParsedDateTime default values."""
        parsed = ParsedDateTime()

        assert parsed.datetime_value is None
        assert parsed.date_part is None
        assert parsed.time_part is None
        assert not parsed.is_relative
        assert parsed.original_text == ""
        assert parsed.confidence == 0.0
        assert parsed.parsing_method == ""
        assert parsed.timezone_info is None


if __name__ == "__main__":
    pytest.main([__file__])
