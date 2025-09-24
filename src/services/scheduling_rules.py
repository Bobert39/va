"""
Scheduling Rules Manager

This module provides management and validation of provider-specific
scheduling rules, buffer times, and practice preferences.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..audit import log_audit_event
from ..config import get_config, set_config

logger = logging.getLogger(__name__)


class SchedulingRulesError(Exception):
    """Base exception for scheduling rules operations."""

    pass


class RuleValidationError(SchedulingRulesError):
    """Error during rule validation."""

    pass


class SchedulingRulesManager:
    """
    Service for managing provider-specific scheduling rules and preferences.

    Handles buffer times, appointment duration limits, working hours,
    and other practice-specific scheduling constraints.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize scheduling rules manager.

        Args:
            config: Configuration dictionary with scheduling rules
        """
        self.config = config
        self.rules = config.get("scheduling_rules", {})
        self._initialize_default_rules()

    def _initialize_default_rules(self):
        """Initialize default scheduling rules if not present."""
        defaults = {
            "default_buffer_minutes": 15,
            "default_appointment_duration": 30,
            "operational_hours": {
                "monday": {"open": "08:00", "close": "17:00"},
                "tuesday": {"open": "08:00", "close": "17:00"},
                "wednesday": {"open": "08:00", "close": "17:00"},
                "thursday": {"open": "08:00", "close": "17:00"},
                "friday": {"open": "08:00", "close": "17:00"},
                "saturday": {"open": "09:00", "close": "12:00"},
                "sunday": None,  # Closed
            },
            "practice_holidays": [],
            "provider_preferences": {},
        }

        # Merge defaults with existing rules
        for key, value in defaults.items():
            if key not in self.rules:
                self.rules[key] = value

    def get_buffer_time(
        self, provider_id: str, appointment_type: str = "standard"
    ) -> int:
        """
        Get buffer time in minutes for provider and appointment type.

        Args:
            provider_id: Provider identifier
            appointment_type: Type of appointment

        Returns:
            Buffer time in minutes
        """
        try:
            provider_prefs = self.rules.get("provider_preferences", {}).get(
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
            return self.rules.get("default_buffer_minutes", 15)

        except Exception as e:
            logger.warning(f"Failed to get buffer time: {str(e)}")
            return 15  # Safe default

    def get_appointment_duration_limits(
        self, provider_id: str, appointment_type: str = "standard"
    ) -> Dict[str, Optional[int]]:
        """
        Get appointment duration limits for provider and type.

        Args:
            provider_id: Provider identifier
            appointment_type: Type of appointment

        Returns:
            Dict with 'min_minutes' and 'max_minutes' keys
        """
        try:
            provider_prefs = self.rules.get("provider_preferences", {}).get(
                provider_id, {}
            )

            # Check type-specific duration limits
            type_durations = provider_prefs.get("appointment_durations", {})
            if appointment_type in type_durations:
                type_settings = type_durations[appointment_type]
                return {
                    "min_minutes": type_settings.get("min_minutes"),
                    "max_minutes": type_settings.get("max_minutes"),
                }

            # Check provider defaults
            return {
                "min_minutes": provider_prefs.get("min_appointment_minutes"),
                "max_minutes": provider_prefs.get("max_appointment_minutes"),
            }

        except Exception as e:
            logger.warning(f"Failed to get duration limits: {str(e)}")
            return {"min_minutes": None, "max_minutes": None}

    def get_operational_hours(self, date: datetime.date) -> Optional[Dict[str, str]]:
        """
        Get operational hours for a specific date.

        Args:
            date: Date to check

        Returns:
            Dict with 'open' and 'close' times or None if closed
        """
        try:
            day_name = date.strftime("%A").lower()
            operational_hours = self.rules.get("operational_hours", {})

            # Check if practice is closed on this day
            day_hours = operational_hours.get(day_name)
            if day_hours is None:
                return None

            # Check for practice holidays
            if date.isoformat() in self.rules.get("practice_holidays", []):
                return None

            return day_hours

        except Exception as e:
            logger.warning(f"Failed to get operational hours: {str(e)}")
            return {"open": "09:00", "close": "17:00"}  # Safe default

    def get_provider_breaks(
        self, provider_id: str, date: datetime.date
    ) -> List[Dict[str, str]]:
        """
        Get provider break times for a specific date.

        Args:
            provider_id: Provider identifier
            date: Date to check

        Returns:
            List of break periods with 'start' and 'end' times
        """
        try:
            provider_prefs = self.rules.get("provider_preferences", {}).get(
                provider_id, {}
            )

            # Get regular breaks
            breaks = provider_prefs.get("breaks", [])

            # Check for date-specific breaks or vacation days
            date_specific = provider_prefs.get("date_specific_breaks", {})
            date_str = date.isoformat()
            if date_str in date_specific:
                breaks.extend(date_specific[date_str])

            return breaks

        except Exception as e:
            logger.warning(f"Failed to get provider breaks: {str(e)}")
            return []

    def is_appointment_type_allowed(
        self, provider_id: str, appointment_type: str
    ) -> bool:
        """
        Check if provider accepts specific appointment type.

        Args:
            provider_id: Provider identifier
            appointment_type: Type of appointment

        Returns:
            True if appointment type is allowed
        """
        try:
            provider_prefs = self.rules.get("provider_preferences", {}).get(
                provider_id, {}
            )
            allowed_types = provider_prefs.get("allowed_appointment_types")

            # If no restriction specified, allow all types
            if allowed_types is None:
                return True

            return appointment_type in allowed_types

        except Exception as e:
            logger.warning(f"Failed to check appointment type: {str(e)}")
            return True  # Safe default - allow all types

    def validate_appointment_rules(
        self,
        provider_id: str,
        start_time: datetime,
        end_time: datetime,
        appointment_type: str = "standard",
    ) -> Dict[str, Any]:
        """
        Validate appointment against all scheduling rules.

        Args:
            provider_id: Provider identifier
            start_time: Appointment start time
            end_time: Appointment end time
            appointment_type: Type of appointment

        Returns:
            Dict with validation results and rule violations
        """
        violations = []
        warnings = []

        try:
            # Check appointment type
            if not self.is_appointment_type_allowed(provider_id, appointment_type):
                violations.append(
                    {
                        "rule": "appointment_type",
                        "message": f"Provider does not accept {appointment_type} appointments",
                    }
                )

            # Check duration limits
            duration_minutes = int((end_time - start_time).total_seconds() / 60)
            limits = self.get_appointment_duration_limits(provider_id, appointment_type)

            if limits["min_minutes"] and duration_minutes < limits["min_minutes"]:
                violations.append(
                    {
                        "rule": "min_duration",
                        "message": f"Appointment too short (minimum {limits['min_minutes']} minutes)",
                    }
                )

            if limits["max_minutes"] and duration_minutes > limits["max_minutes"]:
                violations.append(
                    {
                        "rule": "max_duration",
                        "message": f"Appointment too long (maximum {limits['max_minutes']} minutes)",
                    }
                )

            # Check operational hours
            date = start_time.date()
            hours = self.get_operational_hours(date)

            if hours is None:
                violations.append(
                    {
                        "rule": "operational_hours",
                        "message": f"Practice is closed on {date.strftime('%A, %B %d, %Y')}",
                    }
                )
            else:
                open_time = datetime.strptime(hours["open"], "%H:%M").time()
                close_time = datetime.strptime(hours["close"], "%H:%M").time()

                if start_time.time() < open_time or end_time.time() > close_time:
                    violations.append(
                        {
                            "rule": "operational_hours",
                            "message": f"Outside operational hours ({open_time} - {close_time})",
                        }
                    )

            # Check provider breaks
            breaks = self.get_provider_breaks(provider_id, date)
            for break_period in breaks:
                break_start = datetime.strptime(break_period["start"], "%H:%M").time()
                break_end = datetime.strptime(break_period["end"], "%H:%M").time()

                break_start_dt = datetime.combine(date, break_start)
                break_end_dt = datetime.combine(date, break_end)

                if self._times_overlap(
                    start_time, end_time, break_start_dt, break_end_dt
                ):
                    violations.append(
                        {
                            "rule": "break_time",
                            "message": f"Conflicts with provider break ({break_start} - {break_end})",
                        }
                    )

            return {
                "is_valid": len(violations) == 0,
                "violations": violations,
                "warnings": warnings,
            }

        except Exception as e:
            logger.error(f"Rule validation failed: {str(e)}")
            raise RuleValidationError(f"Failed to validate rules: {str(e)}")

    async def update_provider_preferences(
        self, provider_id: str, preferences: Dict[str, Any]
    ) -> bool:
        """
        Update provider-specific scheduling preferences.

        Args:
            provider_id: Provider identifier
            preferences: New preferences to set

        Returns:
            True if update successful

        Raises:
            RuleValidationError: If preferences are invalid
        """
        try:
            # Validate preferences format
            self._validate_preferences_format(preferences)

            # Update preferences in rules
            if "provider_preferences" not in self.rules:
                self.rules["provider_preferences"] = {}

            if provider_id not in self.rules["provider_preferences"]:
                self.rules["provider_preferences"][provider_id] = {}

            self.rules["provider_preferences"][provider_id].update(preferences)

            # Save to configuration
            config = get_config()
            config["scheduling_rules"] = self.rules
            set_config(config)

            # Log the update
            await log_audit_event(
                "provider_preferences_updated",
                {
                    "provider_id_hash": self._hash_identifier(provider_id),
                    "preferences_updated": list(preferences.keys()),
                },
            )

            return True

        except Exception as e:
            logger.error(f"Failed to update provider preferences: {str(e)}")
            raise RuleValidationError(f"Preference update failed: {str(e)}")

    def _validate_preferences_format(self, preferences: Dict[str, Any]):
        """Validate provider preferences format."""
        valid_keys = {
            "default_buffer_minutes",
            "min_appointment_minutes",
            "max_appointment_minutes",
            "allowed_appointment_types",
            "breaks",
            "buffer_times",
            "appointment_durations",
            "date_specific_breaks",
        }

        for key in preferences.keys():
            if key not in valid_keys:
                raise RuleValidationError(f"Invalid preference key: {key}")

        # Validate specific formats
        if "default_buffer_minutes" in preferences:
            value = preferences["default_buffer_minutes"]
            if not isinstance(value, int) or value < 0 or value > 120:
                raise RuleValidationError(
                    "default_buffer_minutes must be integer 0-120"
                )

        if "breaks" in preferences:
            breaks = preferences["breaks"]
            if not isinstance(breaks, list):
                raise RuleValidationError("breaks must be a list")

            for break_period in breaks:
                if (
                    not isinstance(break_period, dict)
                    or "start" not in break_period
                    or "end" not in break_period
                ):
                    raise RuleValidationError(
                        "Each break must have 'start' and 'end' times"
                    )

                # Validate time format
                try:
                    datetime.strptime(break_period["start"], "%H:%M")
                    datetime.strptime(break_period["end"], "%H:%M")
                except ValueError:
                    raise RuleValidationError("Break times must be in HH:MM format")

    def _times_overlap(
        self,
        start1: datetime,
        end1: datetime,
        start2: datetime,
        end2: datetime,
    ) -> bool:
        """Check if two time periods overlap."""
        return start1 < end2 and end1 > start2

    def get_all_rules(self) -> Dict[str, Any]:
        """Get all scheduling rules."""
        return self.rules.copy()

    def _hash_identifier(self, identifier: str) -> str:
        """Create SHA256 hash of identifier for audit logging."""
        import hashlib

        return hashlib.sha256(identifier.encode()).hexdigest()[:16]
