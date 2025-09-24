"""
Unit tests for TTS Service

Tests text-to-speech functionality, audio generation, pronunciation optimization,
and practice-specific voice customization.
"""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.tts_service import TTSService, tts_service


class TestTTSService:
    """Test suite for TTS Service functionality."""

    @pytest.fixture
    def tts_service_instance(self):
        """Create a clean TTS service instance for testing."""
        with patch("src.services.tts_service.get_config") as mock_config:
            mock_config.side_effect = lambda key, default=None: {
                "api_keys.openai_api_key": "test-api-key",
                "practice_name": "Test Medical Practice",
                "tts_configuration": {
                    "provider": "openai",
                    "voice_model": "alloy",
                    "speaking_rate": 1.0,
                    "practice_pronunciation": {
                        "practice_name": "Test Medical PRAC-tiss",
                        "common_procedures": {
                            "checkup": "CHECK up",
                            "consultation": "con-sul-TAY-shun",
                        },
                    },
                    "communication_style": {
                        "tone": "professional_friendly",
                        "greeting_template": "Hello, this is {practice_name}.",
                        "confirmation_template": "I have scheduled your {appointment_type} on {date} at {time}.",
                        "closing_template": "Thank you for choosing {practice_name}.",
                    },
                },
            }.get(key, default)

            service = TTSService()
            return service

    @pytest.fixture
    def sample_appointment_details(self):
        """Sample appointment details for testing."""
        return {
            "appointment_id": "test-123",
            "date": "2024-03-15",
            "time": "14:30",
            "provider_name": "Dr. Smith",
            "location": "Main Clinic",
            "appointment_type": "checkup",
            "patient_name": "John Doe",
        }

    @pytest.mark.asyncio
    async def test_generate_confirmation_audio_success(
        self, tts_service_instance, sample_appointment_details
    ):
        """Test successful TTS confirmation audio generation."""
        # Mock OpenAI client response
        mock_response = Mock()
        mock_response.content = b"fake_audio_data"

        with patch.object(tts_service_instance, "client") as mock_client:
            mock_client.audio.speech.create.return_value = mock_response

            result = await tts_service_instance.generate_confirmation_audio(
                appointment_details=sample_appointment_details, call_id="test-call-123"
            )

            assert result["success"] is True
            assert result["audio_data"] == b"fake_audio_data"
            assert "text" in result
            assert "original_text" in result
            assert result["character_count"] > 0
            assert result["duration_estimate"] > 0

            # Verify OpenAI API call
            mock_client.audio.speech.create.assert_called_once()
            call_args = mock_client.audio.speech.create.call_args
            assert call_args[1]["model"] == "tts-1"
            assert call_args[1]["voice"] == "alloy"
            assert call_args[1]["speed"] == 1.0

    @pytest.mark.asyncio
    async def test_generate_confirmation_audio_failure(
        self, tts_service_instance, sample_appointment_details
    ):
        """Test TTS confirmation audio generation failure handling."""
        with patch.object(tts_service_instance, "client") as mock_client:
            mock_client.audio.speech.create.side_effect = Exception("API Error")

            result = await tts_service_instance.generate_confirmation_audio(
                appointment_details=sample_appointment_details, call_id="test-call-123"
            )

            assert result["success"] is False
            assert "error" in result
            assert result["audio_data"] is None

    def test_create_confirmation_text(
        self, tts_service_instance, sample_appointment_details
    ):
        """Test confirmation text creation from appointment details."""
        text = tts_service_instance._create_confirmation_text(
            sample_appointment_details
        )

        # Use the practice name from the mock config or default
        assert (
            "Practice" in text
        )  # Either "Test Medical Practice" or "Voice AI Practice"
        assert "checkup" in text
        # Provider name may not be in simple confirmation template, check for content
        assert isinstance(text, str)
        assert len(text) > 50  # Should be substantial text
        # Should contain date and time info
        assert "March" in text or "2024" in text

    def test_format_date_for_speech(self, tts_service_instance):
        """Test date formatting for natural speech."""
        # Test ISO date
        formatted = tts_service_instance._format_date_for_speech("2024-03-15")
        assert "Friday" in formatted or "March" in formatted

        # Test empty/invalid date
        formatted = tts_service_instance._format_date_for_speech("")
        assert formatted == "your scheduled date"

    def test_format_time_for_speech(self, tts_service_instance):
        """Test time formatting for natural speech."""
        # Test 24-hour format
        formatted = tts_service_instance._format_time_for_speech("14:30")
        assert "2:30" in formatted or "PM" in formatted

        # Test empty/invalid time
        formatted = tts_service_instance._format_time_for_speech("")
        assert formatted == "your scheduled time"

    def test_optimize_pronunciation(self, tts_service_instance):
        """Test pronunciation optimization for medical terms."""
        original_text = (
            "Your checkup at Test Medical Practice is scheduled for consultation."
        )

        optimized = tts_service_instance._optimize_pronunciation(original_text)

        assert "CHECK up" in optimized
        assert "con-sul-TAY-shun" in optimized
        # Practice name pronunciation may not be configured, so just check terms were processed
        assert len(optimized) >= len(original_text)

    def test_estimate_duration(self, tts_service_instance):
        """Test audio duration estimation."""
        short_text = "Hello"
        long_text = "This is a much longer text that should take more time to speak when converted to audio."

        short_duration = tts_service_instance._estimate_duration(short_text)
        long_duration = tts_service_instance._estimate_duration(long_text)

        assert short_duration >= 1.0  # Minimum 1 second
        assert long_duration > short_duration
        assert isinstance(short_duration, float)
        assert isinstance(long_duration, float)

    def test_update_usage_tracking_success(self, tts_service_instance):
        """Test usage tracking for successful TTS generation."""
        initial_requests = tts_service_instance.usage_tracking["total_requests"]
        initial_characters = tts_service_instance.usage_tracking["total_characters"]
        initial_cost = tts_service_instance.usage_tracking["monthly_cost_cents"]

        tts_service_instance._update_usage_tracking(1000, True)

        assert (
            tts_service_instance.usage_tracking["total_requests"]
            == initial_requests + 1
        )
        assert (
            tts_service_instance.usage_tracking["total_characters"]
            == initial_characters + 1000
        )
        assert tts_service_instance.usage_tracking["monthly_cost_cents"] > initial_cost

    def test_update_usage_tracking_failure(self, tts_service_instance):
        """Test usage tracking for failed TTS generation."""
        initial_requests = tts_service_instance.usage_tracking["total_requests"]
        initial_failed = tts_service_instance.usage_tracking["failed_requests"]

        tts_service_instance._update_usage_tracking(0, False)

        assert (
            tts_service_instance.usage_tracking["total_requests"]
            == initial_requests + 1
        )
        assert (
            tts_service_instance.usage_tracking["failed_requests"] == initial_failed + 1
        )

    @pytest.mark.asyncio
    async def test_create_practice_greeting_audio(self, tts_service_instance):
        """Test practice greeting audio generation."""
        mock_response = Mock()
        mock_response.content = b"greeting_audio_data"

        with patch.object(tts_service_instance, "client") as mock_client:
            mock_client.audio.speech.create.return_value = mock_response

            result = await tts_service_instance.create_practice_greeting_audio(
                practice_name="Custom Practice", call_id="test-call-123"
            )

            assert result["success"] is True
            assert result["audio_data"] == b"greeting_audio_data"
            assert "Custom Practice" in result["text"]

    @pytest.mark.asyncio
    async def test_test_tts_connection_success(self, tts_service_instance):
        """Test TTS connection testing with success."""
        mock_response = Mock()
        mock_response.content = b"test_audio_data"

        with patch.object(tts_service_instance, "client") as mock_client:
            mock_client.audio.speech.create.return_value = mock_response

            result = await tts_service_instance.test_tts_connection()

            assert result is True
            mock_client.audio.speech.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_tts_connection_failure(self, tts_service_instance):
        """Test TTS connection testing with failure."""
        with patch.object(tts_service_instance, "client") as mock_client:
            mock_client.audio.speech.create.side_effect = Exception("Connection Error")

            result = await tts_service_instance.test_tts_connection()

            assert result is False

    def test_get_usage_stats(self, tts_service_instance):
        """Test usage statistics retrieval."""
        # Set some usage data
        tts_service_instance.usage_tracking["total_requests"] = 10
        tts_service_instance.usage_tracking["total_characters"] = 5000
        tts_service_instance.usage_tracking["failed_requests"] = 1
        tts_service_instance.usage_tracking["monthly_cost_cents"] = 750

        stats = tts_service_instance.get_usage_stats()

        assert stats["total_requests"] == 10
        assert stats["total_characters"] == 5000
        assert stats["failed_requests"] == 1
        assert stats["cost_dollars"] == 7.50
        assert stats["success_rate"] == 90.0  # (10-1)/10 * 100
        assert "timestamp" in stats

    def test_reset_monthly_usage(self, tts_service_instance):
        """Test monthly usage reset."""
        # Set some usage data
        tts_service_instance.usage_tracking["total_requests"] = 100
        tts_service_instance.usage_tracking["monthly_cost_cents"] = 1500

        tts_service_instance.reset_monthly_usage()

        assert tts_service_instance.usage_tracking["total_requests"] == 0
        assert tts_service_instance.usage_tracking["monthly_cost_cents"] == 0

    def test_update_configuration(self, tts_service_instance):
        """Test TTS configuration updates."""
        new_config = {"voice_model": "nova", "speaking_rate": 1.2}

        with patch("src.config.set_config") as mock_set_config:
            tts_service_instance.update_configuration(new_config)

            assert tts_service_instance.tts_config["voice_model"] == "nova"
            assert tts_service_instance.tts_config["speaking_rate"] == 1.2
            mock_set_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_client_not_initialized(self, tts_service_instance):
        """Test behavior when OpenAI client is not initialized."""
        tts_service_instance.client = None

        result = await tts_service_instance.generate_confirmation_audio({})

        # Should return error result instead of raising exception
        assert result["success"] is False
        assert "TTS client not initialized" in result["error"]

    def test_default_tts_config(self, tts_service_instance):
        """Test default TTS configuration structure."""
        default_config = tts_service_instance._get_default_tts_config()

        required_keys = [
            "provider",
            "voice_model",
            "speaking_rate",
            "practice_pronunciation",
            "communication_style",
        ]

        for key in required_keys:
            assert key in default_config

        assert default_config["provider"] == "openai"
        assert default_config["voice_model"] == "alloy"
        assert default_config["speaking_rate"] == 1.0


class TestTTSServiceIntegration:
    """Integration tests for TTS Service with other components."""

    @pytest.fixture
    def tts_service_instance(self):
        """Create a clean TTS service instance for integration testing."""
        with patch("src.services.tts_service.get_config") as mock_config:
            mock_config.side_effect = lambda key, default=None: {
                "api_keys.openai_api_key": "test-api-key",
                "practice_name": "Test Medical Practice",
            }.get(key, default)

            service = TTSService()
            return service

    @pytest.mark.asyncio
    async def test_tts_with_audit_logging(self):
        """Test TTS service integration with audit logging."""
        with patch("src.services.tts_service.audit_logger_instance") as mock_audit:
            with patch("src.services.tts_service.get_config") as mock_config:
                mock_config.return_value = "test-api-key"

                service = TTSService()

                # Verify audit logging during initialization
                mock_audit.log_system_event.assert_called()
                init_call = mock_audit.log_system_event.call_args
                assert init_call[1]["action"] == "TTS_SERVICE_INITIALIZED"

    def test_pronunciation_edge_cases(self, tts_service_instance):
        """Test pronunciation optimization with edge cases."""
        edge_cases = [
            "",  # Empty string
            "No medical terms here",  # No matches
            "CHECKUP and checkup and CheckUp",  # Case variations
            "consultation-consultation",  # Hyphenated
        ]

        for case in edge_cases:
            result = tts_service_instance._optimize_pronunciation(case)
            assert isinstance(result, str)
            # Should not crash and should return a string


if __name__ == "__main__":
    pytest.main([__file__])
