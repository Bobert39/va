"""
Date/Time parsing service for appointment scheduling.
Handles flexible date and time formats including relative and absolute parsing.
"""

import calendar
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class ParsedDateTime:
    """Result of date/time parsing."""

    datetime_value: Optional[datetime] = None
    date_part: Optional[date] = None
    time_part: Optional[time] = None
    is_relative: bool = False
    original_text: str = ""
    confidence: float = 0.0
    parsing_method: str = ""
    timezone_info: Optional[str] = None


class DateTimeParser:
    """
    Flexible date/time parser for natural language appointment scheduling.

    Supports:
    - Relative dates: "tomorrow", "next week", "Monday"
    - Absolute dates: "January 15th", "12/25", "Dec 3rd"
    - Flexible times: "3pm", "fifteen thirty", "morning"
    - Business hours validation
    """

    def __init__(self):
        """Initialize date/time parser with patterns and mappings."""
        self.business_hours = {
            "start": time(8, 0),  # 8:00 AM
            "end": time(17, 0),  # 5:00 PM
            "lunch_start": time(12, 0),  # 12:00 PM
            "lunch_end": time(13, 0),  # 1:00 PM
        }

        # Day name mappings
        self.day_names = {
            "monday": 0,
            "mon": 0,
            "tuesday": 1,
            "tue": 1,
            "tues": 1,
            "wednesday": 2,
            "wed": 2,
            "thursday": 3,
            "thu": 3,
            "thur": 3,
            "thurs": 3,
            "friday": 4,
            "fri": 4,
            "saturday": 5,
            "sat": 5,
            "sunday": 6,
            "sun": 6,
        }

        # Month name mappings
        self.month_names = {
            "january": 1,
            "jan": 1,
            "february": 2,
            "feb": 2,
            "march": 3,
            "mar": 3,
            "april": 4,
            "apr": 4,
            "may": 5,
            "june": 6,
            "jun": 6,
            "july": 7,
            "jul": 7,
            "august": 8,
            "aug": 8,
            "september": 9,
            "sep": 9,
            "sept": 9,
            "october": 10,
            "oct": 10,
            "november": 11,
            "nov": 11,
            "december": 12,
            "dec": 12,
        }

        # Time period mappings
        self.time_periods = {
            "morning": time(9, 0),
            "afternoon": time(14, 0),
            "evening": time(17, 0),
            "noon": time(12, 0),
            "midnight": time(0, 0),
        }

        # Number word mappings
        self.number_words = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
        }

    def parse_datetime(self, text: str) -> ParsedDateTime:
        """
        Parse date and time from natural language text.

        Args:
            text: Input text containing date/time information

        Returns:
            ParsedDateTime with parsed components and metadata
        """
        text_lower = text.lower().strip()

        # Try different parsing strategies in order of preference
        parsers = [
            self._parse_relative_date,
            self._parse_absolute_date,
            self._parse_day_name,
            self._parse_date_patterns,
        ]

        best_result = ParsedDateTime(original_text=text, confidence=0.0)

        for parser in parsers:
            try:
                result = parser(text_lower)
                if result and result.confidence > best_result.confidence:
                    best_result = result
                    best_result.original_text = text
            except Exception as e:
                logger.warning(f"Parser {parser.__name__} failed: {e}")
                continue

        # Parse time component separately if not already parsed
        if best_result.datetime_value and not best_result.time_part:
            time_result = self._parse_time_component(text_lower)
            if time_result:
                # Combine date and time
                date_part = best_result.datetime_value.date()
                combined_dt = datetime.combine(date_part, time_result)
                best_result.datetime_value = combined_dt
                best_result.time_part = time_result
                best_result.confidence = min(1.0, best_result.confidence + 0.2)
        elif not best_result.datetime_value:
            # Try parsing time only
            time_result = self._parse_time_component(text_lower)
            if time_result:
                # Default to tomorrow if only time is provided
                tomorrow = datetime.now().date() + timedelta(days=1)
                best_result.datetime_value = datetime.combine(tomorrow, time_result)
                best_result.time_part = time_result
                best_result.date_part = tomorrow
                best_result.confidence = 0.6
                best_result.parsing_method = "time_only_default_tomorrow"

        return best_result

    def _parse_relative_date(self, text: str) -> Optional[ParsedDateTime]:
        """Parse relative date expressions."""
        now = datetime.now()

        # Today
        if "today" in text:
            return ParsedDateTime(
                datetime_value=now.replace(hour=9, minute=0, second=0, microsecond=0),
                date_part=now.date(),
                is_relative=True,
                confidence=0.9,
                parsing_method="relative_today",
            )

        # Tomorrow
        if "tomorrow" in text:
            tomorrow = now + timedelta(days=1)
            return ParsedDateTime(
                datetime_value=tomorrow.replace(
                    hour=9, minute=0, second=0, microsecond=0
                ),
                date_part=tomorrow.date(),
                is_relative=True,
                confidence=0.9,
                parsing_method="relative_tomorrow",
            )

        # Next week
        if "next week" in text:
            next_week = now + timedelta(days=7)
            # Default to Monday of next week
            days_until_monday = (7 - next_week.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            target_date = next_week + timedelta(days=days_until_monday)

            return ParsedDateTime(
                datetime_value=target_date.replace(
                    hour=9, minute=0, second=0, microsecond=0
                ),
                date_part=target_date.date(),
                is_relative=True,
                confidence=0.8,
                parsing_method="relative_next_week",
            )

        # This week
        if "this week" in text:
            # Default to next weekday
            days_ahead = 1 if now.weekday() < 4 else (7 - now.weekday() + 1)
            target_date = now + timedelta(days=days_ahead)

            return ParsedDateTime(
                datetime_value=target_date.replace(
                    hour=9, minute=0, second=0, microsecond=0
                ),
                date_part=target_date.date(),
                is_relative=True,
                confidence=0.7,
                parsing_method="relative_this_week",
            )

        return None

    def _parse_absolute_date(self, text: str) -> Optional[ParsedDateTime]:
        """Parse absolute date formats."""
        # Month DD, YYYY or Month DD
        month_day_pattern = r"(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(?:(\d{4})|)"
        match = re.search(month_day_pattern, text, re.IGNORECASE)

        if match:
            month_name = match.group(1).lower()
            day = int(match.group(2))
            year = int(match.group(3)) if match.group(3) else datetime.now().year

            if month_name in self.month_names:
                month = self.month_names[month_name]

                try:
                    target_date = date(year, month, day)
                    # If date is in the past this year, assume next year
                    if target_date < date.today() and not match.group(3):
                        target_date = date(year + 1, month, day)

                    return ParsedDateTime(
                        datetime_value=datetime.combine(target_date, time(9, 0)),
                        date_part=target_date,
                        is_relative=False,
                        confidence=0.9,
                        parsing_method="absolute_month_day",
                    )
                except ValueError:
                    pass

        # MM/DD or MM/DD/YYYY
        date_slash_pattern = r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?"
        match = re.search(date_slash_pattern, text)

        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            year = int(match.group(3)) if match.group(3) else datetime.now().year

            try:
                target_date = date(year, month, day)
                # If date is in the past this year, assume next year
                if target_date < date.today() and not match.group(3):
                    target_date = date(year + 1, month, day)

                return ParsedDateTime(
                    datetime_value=datetime.combine(target_date, time(9, 0)),
                    date_part=target_date,
                    is_relative=False,
                    confidence=0.8,
                    parsing_method="absolute_slash_format",
                )
            except ValueError:
                pass

        return None

    def _parse_day_name(self, text: str) -> Optional[ParsedDateTime]:
        """Parse day names (Monday, Tuesday, etc.)."""
        for day_name, day_num in self.day_names.items():
            if day_name in text:
                now = datetime.now()
                current_day = now.weekday()

                # Calculate days until target day
                days_ahead = (day_num - current_day) % 7
                if days_ahead == 0:  # Same day, assume next week
                    days_ahead = 7

                target_date = now + timedelta(days=days_ahead)

                return ParsedDateTime(
                    datetime_value=target_date.replace(
                        hour=9, minute=0, second=0, microsecond=0
                    ),
                    date_part=target_date.date(),
                    is_relative=True,
                    confidence=0.8,
                    parsing_method="day_name",
                )

        return None

    def _parse_date_patterns(self, text: str) -> Optional[ParsedDateTime]:
        """Parse other date patterns."""
        # "in X days"
        days_pattern = r"in\s+(\d+)\s+days?"
        match = re.search(days_pattern, text)

        if match:
            days = int(match.group(1))
            target_date = datetime.now() + timedelta(days=days)

            return ParsedDateTime(
                datetime_value=target_date.replace(
                    hour=9, minute=0, second=0, microsecond=0
                ),
                date_part=target_date.date(),
                is_relative=True,
                confidence=0.8,
                parsing_method="relative_days_ahead",
            )

        return None

    def _parse_time_component(self, text: str) -> Optional[time]:
        """Parse time component from text."""
        # Time periods (morning, afternoon, etc.)
        for period, default_time in self.time_periods.items():
            if period in text:
                return default_time

        # HH:MM format (24-hour or 12-hour with am/pm)
        time_pattern = r"(\d{1,2}):(\d{2})\s*(am|pm)?"
        match = re.search(time_pattern, text, re.IGNORECASE)

        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            am_pm = match.group(3).lower() if match.group(3) else None

            if am_pm == "pm" and hour != 12:
                hour += 12
            elif am_pm == "am" and hour == 12:
                hour = 0

            try:
                return time(hour, minute)
            except ValueError:
                pass

        # H pm/am format (e.g., "3pm", "10am")
        hour_pattern = r"(\d{1,2})\s*(am|pm)"
        match = re.search(hour_pattern, text, re.IGNORECASE)

        if match:
            hour = int(match.group(1))
            am_pm = match.group(2).lower()

            if am_pm == "pm" and hour != 12:
                hour += 12
            elif am_pm == "am" and hour == 12:
                hour = 0

            try:
                return time(hour, 0)
            except ValueError:
                pass

        # Word-based time (e.g., "three thirty", "fifteen twenty")
        word_time = self._parse_word_time(text)
        if word_time:
            return word_time

        return None

    def _parse_word_time(self, text: str) -> Optional[time]:
        """Parse time expressed in words."""
        # Extract hour and minute words
        words = text.split()

        # Look for patterns like "three thirty" or "fifteen twenty"
        for i in range(len(words) - 1):
            hour_word = words[i].lower()
            minute_word = words[i + 1].lower()

            if hour_word in self.number_words and minute_word in self.number_words:
                hour = self.number_words[hour_word]
                minute = self.number_words[minute_word]

                # Validate hour and minute ranges
                if 1 <= hour <= 24 and 0 <= minute <= 59:
                    # Convert 24-hour to 12-hour if needed
                    if hour > 12:
                        hour -= 12

                    try:
                        return time(hour, minute)
                    except ValueError:
                        pass

        return None

    def validate_business_hours(self, dt: datetime) -> Tuple[bool, str]:
        """
        Validate if datetime falls within business hours.

        Args:
            dt: Datetime to validate

        Returns:
            Tuple of (is_valid, reason)
        """
        appointment_time = dt.time()
        day_of_week = dt.weekday()

        # Check if weekend
        if day_of_week >= 5:  # Saturday (5) or Sunday (6)
            return False, "Appointment requested for weekend"

        # Check if before business hours
        if appointment_time < self.business_hours["start"]:
            return (
                False,
                f"Appointment before business hours (opens at {self.business_hours['start'].strftime('%I:%M %p')})",
            )

        # Check if after business hours
        if appointment_time > self.business_hours["end"]:
            return (
                False,
                f"Appointment after business hours (closes at {self.business_hours['end'].strftime('%I:%M %p')})",
            )

        # Check if during lunch hour
        if (
            self.business_hours["lunch_start"]
            <= appointment_time
            <= self.business_hours["lunch_end"]
        ):
            return False, "Appointment during lunch hour"

        return True, "Valid business hours"

    def suggest_alternative_times(self, original_dt: datetime) -> List[datetime]:
        """
        Suggest alternative appointment times if original is invalid.

        Args:
            original_dt: Original datetime that was invalid

        Returns:
            List of alternative datetime suggestions
        """
        suggestions = []

        # Try same day, different times
        for hour in [9, 10, 11, 14, 15, 16]:  # Skip lunch hour
            try:
                alt_time = original_dt.replace(
                    hour=hour, minute=0, second=0, microsecond=0
                )
                is_valid, _ = self.validate_business_hours(alt_time)
                if is_valid:
                    suggestions.append(alt_time)
            except ValueError:
                continue

        # Try next business day, same time
        next_day = original_dt + timedelta(days=1)
        while next_day.weekday() >= 5:  # Skip weekends
            next_day += timedelta(days=1)

        try:
            next_day_option = next_day.replace(hour=max(9, original_dt.hour))
            is_valid, _ = self.validate_business_hours(next_day_option)
            if is_valid:
                suggestions.append(next_day_option)
        except ValueError:
            pass

        return suggestions[:3]  # Return up to 3 suggestions

    def format_datetime_human(self, dt: datetime) -> str:
        """
        Format datetime in human-readable format.

        Args:
            dt: Datetime to format

        Returns:
            Human-readable datetime string
        """
        day_name = dt.strftime("%A")
        formatted_date = dt.strftime("%B %d, %Y")
        formatted_time = dt.strftime("%I:%M %p").lstrip("0")

        return f"{day_name}, {formatted_date} at {formatted_time}"


# Global datetime parser instance
datetime_parser = DateTimeParser()
