"""
Time Suggestion Engine

This module provides intelligent alternative appointment time suggestions
when conflicts are detected, with ranking and voice-friendly formatting.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from ..audit import log_audit_event
from .conflict_detector import ConflictDetector
from .schedule_checker import ScheduleChecker

logger = logging.getLogger(__name__)


class TimeSuggesterError(Exception):
    """Base exception for time suggestion operations."""

    pass


class SuggestionGenerationError(TimeSuggesterError):
    """Error during suggestion generation."""

    pass


class TimeSuggester:
    """
    Service for generating intelligent appointment time suggestions.

    Provides ranked alternative times when conflicts are detected,
    with voice-friendly formatting for conversational interfaces.
    """

    def __init__(
        self,
        conflict_detector: ConflictDetector,
        schedule_checker: ScheduleChecker,
        config: Dict[str, Any],
    ):
        """
        Initialize time suggester.

        Args:
            conflict_detector: Conflict detection service
            schedule_checker: Schedule checking service
            config: Configuration including suggestion preferences
        """
        self.conflict_detector = conflict_detector
        self.schedule_checker = schedule_checker
        self.config = config
        self.suggestion_preferences = config.get("suggestion_preferences", {})

    async def suggest_alternative_times(
        self,
        provider_id: str,
        original_start: datetime,
        original_end: datetime,
        appointment_type: str = "standard",
        max_suggestions: int = 5,
        search_days: int = 14,
    ) -> List[Dict[str, Any]]:
        """
        Generate ranked alternative appointment times.

        Args:
            provider_id: Provider identifier
            original_start: Original requested start time
            original_end: Original requested end time
            appointment_type: Type of appointment
            max_suggestions: Maximum number of suggestions to return
            search_days: Number of days ahead to search

        Returns:
            List of suggestion dictionaries with rankings

        Raises:
            SuggestionGenerationError: If suggestion generation fails
        """
        try:
            duration = original_end - original_start
            duration_minutes = int(duration.total_seconds() / 60)

            suggestions = []

            # Log suggestion request
            await log_audit_event(
                "time_suggestions_requested",
                {
                    "provider_id_hash": self._hash_identifier(provider_id),
                    "original_start": original_start.isoformat(),
                    "duration_minutes": duration_minutes,
                    "appointment_type": appointment_type,
                    "search_days": search_days,
                },
            )

            # Strategy 1: Same day, nearby times
            same_day_suggestions = await self._suggest_same_day_times(
                provider_id, original_start, duration, appointment_type
            )
            suggestions.extend(same_day_suggestions)

            # Strategy 2: Same time, different days
            if len(suggestions) < max_suggestions:
                same_time_suggestions = await self._suggest_same_time_different_days(
                    provider_id,
                    original_start,
                    duration,
                    appointment_type,
                    search_days,
                )
                suggestions.extend(same_time_suggestions)

            # Strategy 3: Similar times, nearby days
            if len(suggestions) < max_suggestions:
                nearby_suggestions = await self._suggest_nearby_times_and_days(
                    provider_id,
                    original_start,
                    duration,
                    appointment_type,
                    search_days,
                )
                suggestions.extend(nearby_suggestions)

            # Strategy 4: Next available slots
            if len(suggestions) < max_suggestions:
                next_available = await self._suggest_next_available_slots(
                    provider_id, original_start, duration_minutes, search_days
                )
                suggestions.extend(next_available)

            # Remove duplicates and sort by ranking score
            unique_suggestions = self._remove_duplicates(suggestions)
            ranked_suggestions = sorted(
                unique_suggestions,
                key=lambda x: x["ranking_score"],
                reverse=True,
            )

            # Add voice-friendly formatting
            formatted_suggestions = self._add_voice_formatting(
                ranked_suggestions[:max_suggestions]
            )

            # Log suggestion results
            await log_audit_event(
                "time_suggestions_generated",
                {
                    "provider_id_hash": self._hash_identifier(provider_id),
                    "suggestions_count": len(formatted_suggestions),
                    "strategies_used": 4,
                    "top_score": formatted_suggestions[0]["ranking_score"]
                    if formatted_suggestions
                    else 0,
                },
            )

            return formatted_suggestions

        except Exception as e:
            logger.error(f"Failed to generate time suggestions: {str(e)}")
            await log_audit_event(
                "time_suggestions_error",
                {
                    "provider_id_hash": self._hash_identifier(provider_id),
                    "error": str(e),
                },
            )
            raise SuggestionGenerationError(f"Suggestion generation failed: {str(e)}")

    async def _suggest_same_day_times(
        self,
        provider_id: str,
        original_start: datetime,
        duration: timedelta,
        appointment_type: str,
    ) -> List[Dict[str, Any]]:
        """Suggest alternative times on the same day."""
        suggestions = []

        try:
            date = original_start.date()
            duration_minutes = int(duration.total_seconds() / 60)

            # Get all available slots for the day
            available_slots = await self.schedule_checker.get_available_slots(
                provider_id, date, duration_minutes
            )

            for slot in available_slots:
                slot_start = datetime.fromisoformat(slot["start"])
                # slot_end = datetime.fromisoformat(slot["end"])  # Not used in ranking

                # Skip if this is the original time
                if slot_start == original_start:
                    continue

                # Calculate ranking based on time proximity
                time_diff = abs((slot_start - original_start).total_seconds())
                max_day_diff = 8 * 3600  # 8 hours in seconds
                proximity_score = max(0, 1.0 - (time_diff / max_day_diff))

                # Bonus for preferred times
                time_preference_bonus = self._get_time_preference_bonus(slot_start)

                ranking_score = 0.8 + (proximity_score * 0.15) + time_preference_bonus

                suggestions.append(
                    {
                        "suggested_start": slot["start"],
                        "suggested_end": slot["end"],
                        "ranking_score": ranking_score,
                        "strategy": "same_day",
                        "reason": f"Same day, {self._format_time_difference(slot_start, original_start)} from requested time",
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to suggest same day times: {str(e)}")

        return suggestions

    async def _suggest_same_time_different_days(
        self,
        provider_id: str,
        original_start: datetime,
        duration: timedelta,
        appointment_type: str,
        search_days: int,
    ) -> List[Dict[str, Any]]:
        """Suggest same time on different days."""
        suggestions = []

        try:
            original_time = original_start.time()

            for days_ahead in range(1, search_days + 1):
                future_date = original_start.date() + timedelta(days=days_ahead)
                future_start = datetime.combine(future_date, original_time)
                future_end = future_start + duration

                # Check if this time is available
                is_available = await self.schedule_checker.is_time_available(
                    provider_id, future_start, future_end
                )

                if is_available:
                    # Check for conflicts to ensure it's really available
                    conflicts = await self.conflict_detector.check_conflicts(
                        provider_id, future_start, future_end, appointment_type
                    )

                    if not conflicts["has_blocking_conflicts"]:
                        # Calculate ranking based on date proximity
                        date_penalty = days_ahead * 0.05
                        ranking_score = max(0.1, 0.9 - date_penalty)

                        # Bonus for preferred days
                        day_preference_bonus = self._get_day_preference_bonus(
                            future_date
                        )
                        ranking_score += day_preference_bonus

                        suggestions.append(
                            {
                                "suggested_start": future_start.isoformat(),
                                "suggested_end": future_end.isoformat(),
                                "ranking_score": ranking_score,
                                "strategy": "same_time",
                                "reason": f"Same time on {future_date.strftime('%A, %B %d')}",
                            }
                        )

        except Exception as e:
            logger.warning(f"Failed to suggest same time different days: {str(e)}")

        return suggestions

    async def _suggest_nearby_times_and_days(
        self,
        provider_id: str,
        original_start: datetime,
        duration: timedelta,
        appointment_type: str,
        search_days: int,
    ) -> List[Dict[str, Any]]:
        """Suggest nearby times on nearby days."""
        suggestions = []

        try:
            # duration_minutes = int(duration.total_seconds() / 60)  # Not used in current logic
            time_offsets = [-2, -1, 1, 2]  # Hours before/after original time

            for days_ahead in range(1, min(search_days + 1, 8)):  # Limit to one week
                future_date = original_start.date() + timedelta(days=days_ahead)

                for hour_offset in time_offsets:
                    adjusted_start = original_start.replace(
                        year=future_date.year,
                        month=future_date.month,
                        day=future_date.day,
                    ) + timedelta(hours=hour_offset)

                    adjusted_end = adjusted_start + duration

                    # Skip if outside reasonable hours
                    if adjusted_start.hour < 7 or adjusted_end.hour > 19:
                        continue

                    # Check availability
                    is_available = await self.schedule_checker.is_time_available(
                        provider_id, adjusted_start, adjusted_end
                    )

                    if is_available:
                        conflicts = await self.conflict_detector.check_conflicts(
                            provider_id,
                            adjusted_start,
                            adjusted_end,
                            appointment_type,
                        )

                        if not conflicts["has_blocking_conflicts"]:
                            # Calculate ranking
                            date_penalty = days_ahead * 0.05
                            time_penalty = abs(hour_offset) * 0.03
                            ranking_score = max(0.1, 0.7 - date_penalty - time_penalty)

                            suggestions.append(
                                {
                                    "suggested_start": adjusted_start.isoformat(),
                                    "suggested_end": adjusted_end.isoformat(),
                                    "ranking_score": ranking_score,
                                    "strategy": "nearby",
                                    "reason": f"{adjusted_start.strftime('%A, %B %d at %I:%M %p')}",
                                }
                            )

        except Exception as e:
            logger.warning(f"Failed to suggest nearby times and days: {str(e)}")

        return suggestions

    async def _suggest_next_available_slots(
        self,
        provider_id: str,
        original_start: datetime,
        duration_minutes: int,
        search_days: int,
    ) -> List[Dict[str, Any]]:
        """Suggest next available slots regardless of time."""
        suggestions = []

        try:
            # Find next available slot
            next_slot = await self.schedule_checker.get_next_available_slot(
                provider_id, original_start, duration_minutes, search_days
            )

            if next_slot:
                slot_start = datetime.fromisoformat(next_slot["start"])
                days_diff = (slot_start.date() - original_start.date()).days

                # Lower ranking since this is just "next available"
                ranking_score = max(0.1, 0.5 - (days_diff * 0.02))

                suggestions.append(
                    {
                        "suggested_start": next_slot["start"],
                        "suggested_end": next_slot["end"],
                        "ranking_score": ranking_score,
                        "strategy": "next_available",
                        "reason": f"Next available appointment on {slot_start.strftime('%A, %B %d at %I:%M %p')}",
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to suggest next available slots: {str(e)}")

        return suggestions

    def _remove_duplicates(
        self, suggestions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate suggestions based on start time."""
        seen_times = set()
        unique_suggestions = []

        for suggestion in suggestions:
            start_time = suggestion["suggested_start"]
            if start_time not in seen_times:
                seen_times.add(start_time)
                unique_suggestions.append(suggestion)

        return unique_suggestions

    def _add_voice_formatting(
        self, suggestions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Add voice-friendly formatting to suggestions."""
        for i, suggestion in enumerate(suggestions):
            start_dt = datetime.fromisoformat(suggestion["suggested_start"])

            # Add human-readable time formatting
            suggestion["voice_friendly_time"] = self._format_for_voice(start_dt)
            suggestion["display_time"] = start_dt.strftime("%A, %B %d at %I:%M %p")
            suggestion["rank"] = i + 1

            # Add time category
            suggestion["time_category"] = self._get_time_category(start_dt)

        return suggestions

    def _format_for_voice(self, dt: datetime) -> str:
        """Format datetime for voice announcement."""
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        dt_date = dt.date()

        if dt_date == today:
            return f"today at {dt.strftime('%I:%M %p')}"
        elif dt_date == tomorrow:
            return f"tomorrow at {dt.strftime('%I:%M %p')}"
        elif (dt_date - today).days <= 7:
            return f"{dt.strftime('%A')} at {dt.strftime('%I:%M %p')}"
        else:
            return f"{dt.strftime('%A, %B %d')} at {dt.strftime('%I:%M %p')}"

    def _format_time_difference(self, time1: datetime, time2: datetime) -> str:
        """Format time difference for human readability."""
        diff = abs((time1 - time2).total_seconds())
        hours = int(diff // 3600)
        minutes = int((diff % 3600) // 60)

        if hours > 0:
            if minutes > 0:
                return f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
            else:
                return f"{hours} hour{'s' if hours != 1 else ''}"
        else:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"

    def _get_time_preference_bonus(self, dt: datetime) -> float:
        """Get bonus score for preferred appointment times."""
        hour = dt.hour

        # Preferred times (9-11 AM, 2-4 PM)
        if 9 <= hour <= 11 or 14 <= hour <= 16:
            return 0.05
        # Good times (8-12 PM, 1-5 PM)
        elif 8 <= hour <= 12 or 13 <= hour <= 17:
            return 0.02
        # Less preferred times
        else:
            return 0

    def _get_day_preference_bonus(self, date: datetime.date) -> float:
        """Get bonus score for preferred days."""
        day_name = date.strftime("%A").lower()

        # Prefer weekdays over weekends
        if day_name in [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
        ]:
            return 0.03
        else:
            return 0

    def _get_time_category(self, dt: datetime) -> str:
        """Categorize time for voice interface."""
        hour = dt.hour

        if 6 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "other"

    def _hash_identifier(self, identifier: str) -> str:
        """Create SHA256 hash of identifier for audit logging."""
        import hashlib

        return hashlib.sha256(identifier.encode()).hexdigest()[:16]
