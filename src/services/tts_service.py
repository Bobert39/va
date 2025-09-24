"""
Text-to-Speech Service

Handles OpenAI TTS API integration for appointment confirmation audio generation,
including real-time TTS processing, medical term optimization, and practice-specific
voice customization.
"""

import asyncio
import io
import logging
import tempfile
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

from openai import OpenAI

from src.audit import audit_logger_instance
from src.config import get_config

logger = logging.getLogger(__name__)


class TTSService:
    """
    Handles Text-to-Speech processing for appointment confirmations.

    Features:
    - OpenAI TTS API integration
    - Medical term pronunciation optimization
    - Practice-specific voice customization
    - Real-time audio generation
    - HIPAA-compliant audio handling (no local storage)
    """

    def __init__(self):
        """Initialize TTS service."""
        self.client: Optional[OpenAI] = None
        self.api_key: Optional[str] = None
        self.tts_config: Dict[str, any] = {}
        self.usage_tracking: Dict[str, int] = {
            "total_requests": 0,
            "total_characters": 0,
            "failed_requests": 0,
            "monthly_cost_cents": 0,
        }
        self._initialize_client()

    def _initialize_client(self):
        """Initialize OpenAI client and load TTS configuration."""
        try:
            self.api_key = get_config("api_keys.openai_api_key")

            if not self.api_key:
                logger.warning("OpenAI API key not configured")
                return

            self.client = OpenAI(api_key=self.api_key)

            # Load TTS configuration
            self.tts_config = get_config(
                "tts_configuration", self._get_default_tts_config()
            )

            logger.info("TTS service initialized successfully")

            audit_logger_instance.log_system_event(
                action="TTS_SERVICE_INITIALIZED", result="SUCCESS"
            )

        except Exception as e:
            logger.error(f"Failed to initialize TTS service: {e}")
            audit_logger_instance.log_system_event(
                action="TTS_SERVICE_INITIALIZATION",
                result="FAILURE",
                additional_data={"error": str(e)},
            )

    def _get_default_tts_config(self) -> Dict[str, any]:
        """Get default TTS configuration."""
        return {
            "provider": "openai",
            "voice_model": "alloy",
            "speaking_rate": 1.0,
            "practice_pronunciation": {
                "practice_name": "",
                "common_procedures": {
                    "checkup": "CHECK up",
                    "consultation": "con-sul-TAY-shun",
                    "follow up": "FOLLOW up",
                    "appointment": "a-POINT-ment",
                },
            },
            "communication_style": {
                "tone": "professional_friendly",
                "greeting_template": "Hello, this is {practice_name}. I'm calling to confirm your upcoming appointment.",
                "confirmation_template": "I have scheduled your {appointment_type} on {date} at {time} with {provider_name} at our {location} location. Please say 'yes' to confirm or 'no' if you need to make changes.",
                "closing_template": "Thank you for choosing {practice_name}. We look forward to seeing you. Have a great day!",
            },
        }

    async def generate_confirmation_audio(
        self,
        appointment_details: Dict[str, any],
        call_id: Optional[str] = None,
        voice_model: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Generate appointment confirmation audio using TTS.

        Args:
            appointment_details: Dictionary containing appointment information
            call_id: Optional call ID for tracking
            voice_model: Override voice model (defaults to config)

        Returns:
            Dictionary with audio data and metadata
        """
        try:
            if not self.client:
                raise ValueError("TTS client not initialized")

            # Generate confirmation text
            confirmation_text = self._create_confirmation_text(appointment_details)

            # Apply pronunciation optimizations
            optimized_text = self._optimize_pronunciation(confirmation_text)

            # Generate TTS audio
            response = self.client.audio.speech.create(
                model="tts-1",
                voice=voice_model or self.tts_config.get("voice_model", "alloy"),
                input=optimized_text,
                speed=self.tts_config.get("speaking_rate", 1.0),
            )

            # Get audio data
            audio_data = response.content

            # Calculate metrics
            character_count = len(optimized_text)
            duration_estimate = self._estimate_duration(optimized_text)

            # Update usage tracking
            self._update_usage_tracking(character_count, True)

            # Log successful generation
            audit_logger_instance.log_system_event(
                action="TTS_CONFIRMATION_GENERATED",
                result="SUCCESS",
                additional_data={
                    "call_id": call_id,
                    "character_count": character_count,
                    "duration_estimate": duration_estimate,
                    "voice_model": voice_model
                    or self.tts_config.get("voice_model", "alloy"),
                    "appointment_id": appointment_details.get("appointment_id"),
                },
            )

            result = {
                "audio_data": audio_data,
                "text": optimized_text,
                "original_text": confirmation_text,
                "character_count": character_count,
                "duration_estimate": duration_estimate,
                "voice_model": voice_model
                or self.tts_config.get("voice_model", "alloy"),
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(
                f"TTS confirmation generated successfully: {character_count} characters, "
                f"estimated {duration_estimate:.1f}s duration"
            )
            return result

        except Exception as e:
            self._update_usage_tracking(0, False)
            logger.error(f"TTS confirmation generation failed: {e}")

            audit_logger_instance.log_system_event(
                action="TTS_CONFIRMATION_GENERATED",
                result="FAILURE",
                additional_data={
                    "call_id": call_id,
                    "error": str(e),
                    "appointment_id": appointment_details.get("appointment_id"),
                },
            )

            return {
                "audio_data": None,
                "text": "",
                "error": str(e),
                "success": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _create_confirmation_text(self, appointment_details: Dict[str, any]) -> str:
        """
        Create confirmation text from appointment details.

        Args:
            appointment_details: Appointment information

        Returns:
            Formatted confirmation text
        """
        try:
            # Get templates from configuration
            greeting = self.tts_config.get("communication_style", {}).get(
                "greeting_template",
                "Hello, this is {practice_name}. I'm calling to confirm your upcoming appointment.",
            )

            confirmation = self.tts_config.get("communication_style", {}).get(
                "confirmation_template",
                "I have scheduled your {appointment_type} on {date} at {time} with {provider_name} at our {location} location. Please say 'yes' to confirm or 'no' if you need to make changes.",
            )

            closing = self.tts_config.get("communication_style", {}).get(
                "closing_template",
                "Thank you for choosing {practice_name}. We look forward to seeing you. Have a great day!",
            )

            # Get practice name from config
            practice_name = get_config("practice_name", "our practice")

            # Format appointment date and time for speech
            formatted_date = self._format_date_for_speech(
                appointment_details.get("date", "")
            )
            formatted_time = self._format_time_for_speech(
                appointment_details.get("time", "")
            )

            # Build complete confirmation text
            text_parts = []

            # Greeting
            text_parts.append(greeting.format(practice_name=practice_name))

            # Confirmation details
            text_parts.append(
                confirmation.format(
                    appointment_type=appointment_details.get(
                        "appointment_type", "appointment"
                    ),
                    date=formatted_date,
                    time=formatted_time,
                    provider_name=appointment_details.get(
                        "provider_name", "your provider"
                    ),
                    location=appointment_details.get("location", "our clinic"),
                )
            )

            # Closing
            text_parts.append(closing.format(practice_name=practice_name))

            return " ".join(text_parts)

        except Exception as e:
            logger.error(f"Failed to create confirmation text: {e}")
            return "I'm calling to confirm your upcoming appointment. Please say yes to confirm or no if you need to make changes."

    def _format_date_for_speech(self, date_str: str) -> str:
        """Format date string for natural speech."""
        try:
            # Parse date and format for speech
            if isinstance(date_str, str) and date_str:
                # Assume format like "2024-03-15"
                date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return date_obj.strftime("%A, %B %d")
            return "your scheduled date"
        except Exception:
            return "your scheduled date"

    def _format_time_for_speech(self, time_str: str) -> str:
        """Format time string for natural speech."""
        try:
            # Parse time and format for speech
            if isinstance(time_str, str) and time_str:
                # Handle various time formats
                if ":" in time_str:
                    time_obj = datetime.strptime(time_str.split()[0], "%H:%M").time()
                    return (
                        time_obj.strftime("%I:%M %p")
                        .lstrip("0")
                        .replace(":00", " o'clock")
                    )
            return "your scheduled time"
        except Exception:
            return "your scheduled time"

    def _optimize_pronunciation(self, text: str) -> str:
        """
        Optimize text for better pronunciation of medical and practice-specific terms.

        Args:
            text: Original text

        Returns:
            Text with pronunciation optimizations
        """
        try:
            optimized_text = text

            # Apply practice-specific pronunciation
            practice_pronunciations = self.tts_config.get("practice_pronunciation", {})

            # Replace practice name if configured
            practice_name_pronunciation = practice_pronunciations.get("practice_name")
            if practice_name_pronunciation:
                practice_name = get_config("practice_name", "")
                if practice_name:
                    optimized_text = optimized_text.replace(
                        practice_name, practice_name_pronunciation
                    )

            # Apply common procedure pronunciations
            common_procedures = practice_pronunciations.get("common_procedures", {})
            for term, pronunciation in common_procedures.items():
                # Use word boundaries to avoid partial replacements
                import re

                pattern = r"\b" + re.escape(term) + r"\b"
                optimized_text = re.sub(
                    pattern, pronunciation, optimized_text, flags=re.IGNORECASE
                )

            return optimized_text

        except Exception as e:
            logger.warning(f"Pronunciation optimization failed: {e}")
            return text

    def _estimate_duration(self, text: str) -> float:
        """
        Estimate audio duration based on text length.

        Args:
            text: Text to estimate duration for

        Returns:
            Estimated duration in seconds
        """
        # Average speaking rate: ~150 words per minute
        # Adjusted for TTS speaking rate configuration
        words = len(text.split())
        base_wpm = 150
        speaking_rate = self.tts_config.get("speaking_rate", 1.0)

        # Adjust WPM based on speaking rate
        effective_wpm = base_wpm * speaking_rate

        # Calculate duration in seconds
        duration = (words / effective_wpm) * 60

        return max(duration, 1.0)  # Minimum 1 second

    def _update_usage_tracking(self, character_count: int, success: bool):
        """Update TTS API usage tracking for cost monitoring."""
        self.usage_tracking["total_requests"] += 1

        if success:
            self.usage_tracking["total_characters"] += character_count
            # TTS pricing: ~$0.015 per 1K characters
            cost_cents = int((character_count / 1000) * 1.5)  # Convert to cents
            self.usage_tracking["monthly_cost_cents"] += cost_cents
        else:
            self.usage_tracking["failed_requests"] += 1

    async def create_practice_greeting_audio(
        self, practice_name: Optional[str] = None, call_id: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Generate standardized practice greeting audio.

        Args:
            practice_name: Override practice name
            call_id: Optional call ID for tracking

        Returns:
            Dictionary with audio data and metadata
        """
        try:
            if not self.client:
                raise ValueError("TTS client not initialized")

            # Use provided practice name or get from config
            name = practice_name or get_config("practice_name", "our practice")

            greeting_template = self.tts_config.get("communication_style", {}).get(
                "greeting_template",
                "Hello, this is {practice_name}. I'm calling to confirm your upcoming appointment.",
            )

            greeting_text = greeting_template.format(practice_name=name)
            optimized_text = self._optimize_pronunciation(greeting_text)

            # Generate TTS audio
            response = self.client.audio.speech.create(
                model="tts-1",
                voice=self.tts_config.get("voice_model", "alloy"),
                input=optimized_text,
                speed=self.tts_config.get("speaking_rate", 1.0),
            )

            audio_data = response.content
            character_count = len(optimized_text)
            duration_estimate = self._estimate_duration(optimized_text)

            self._update_usage_tracking(character_count, True)

            audit_logger_instance.log_system_event(
                action="TTS_GREETING_GENERATED",
                result="SUCCESS",
                additional_data={
                    "call_id": call_id,
                    "character_count": character_count,
                    "practice_name": name,
                },
            )

            return {
                "audio_data": audio_data,
                "text": optimized_text,
                "character_count": character_count,
                "duration_estimate": duration_estimate,
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            self._update_usage_tracking(0, False)
            logger.error(f"Practice greeting generation failed: {e}")

            audit_logger_instance.log_system_event(
                action="TTS_GREETING_GENERATED",
                result="FAILURE",
                additional_data={"call_id": call_id, "error": str(e)},
            )

            return {
                "audio_data": None,
                "text": "",
                "error": str(e),
                "success": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def test_tts_connection(self) -> bool:
        """
        Test TTS API connection with a simple phrase.

        Returns:
            True if connection successful
        """
        try:
            if not self.client:
                return False

            # Test with simple phrase
            test_text = "This is a test of the text-to-speech service."

            response = self.client.audio.speech.create(
                model="tts-1", voice="alloy", input=test_text
            )

            success = len(response.content) > 0

            audit_logger_instance.log_system_event(
                action="TTS_CONNECTION_TEST",
                result="SUCCESS" if success else "FAILURE",
            )

            logger.info(f"TTS connection test: {'successful' if success else 'failed'}")
            return success

        except Exception as e:
            logger.error(f"TTS connection test failed: {e}")
            audit_logger_instance.log_system_event(
                action="TTS_CONNECTION_TEST",
                result="FAILURE",
                additional_data={"error": str(e)},
            )
            return False

    def get_usage_stats(self) -> Dict[str, any]:
        """
        Get current TTS usage statistics.

        Returns:
            Usage statistics dictionary
        """
        return {
            **self.usage_tracking,
            "cost_dollars": self.usage_tracking["monthly_cost_cents"] / 100.0,
            "success_rate": (
                (
                    self.usage_tracking["total_requests"]
                    - self.usage_tracking["failed_requests"]
                )
                / max(self.usage_tracking["total_requests"], 1)
            )
            * 100,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def reset_monthly_usage(self):
        """Reset monthly usage tracking (call at start of each month)."""
        self.usage_tracking = {
            "total_requests": 0,
            "total_characters": 0,
            "failed_requests": 0,
            "monthly_cost_cents": 0,
        }

        audit_logger_instance.log_system_event(
            action="TTS_MONTHLY_USAGE_RESET", result="SUCCESS"
        )

    def update_configuration(self, new_config: Dict[str, any]):
        """
        Update TTS configuration.

        Args:
            new_config: New TTS configuration
        """
        try:
            # Merge with existing config
            self.tts_config.update(new_config)

            # Save to global config
            from src.config import set_config

            set_config("tts_configuration", self.tts_config)

            audit_logger_instance.log_system_event(
                action="TTS_CONFIGURATION_UPDATED",
                result="SUCCESS",
                additional_data={"updated_fields": list(new_config.keys())},
            )

            logger.info("TTS configuration updated successfully")

        except Exception as e:
            logger.error(f"Failed to update TTS configuration: {e}")
            audit_logger_instance.log_system_event(
                action="TTS_CONFIGURATION_UPDATED",
                result="FAILURE",
                additional_data={"error": str(e)},
            )


# Global service instance
tts_service = TTSService()
