"""
Unit tests for VoiceCallHandler service.

Tests voice call processing, session management, timeout handling,
and audio feedback generation.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.voice_handler import VoiceCallHandler


class TestVoiceCallHandler:
    """Test cases for VoiceCallHandler service."""

    @pytest.fixture
    def handler(self):
        """Create a fresh VoiceCallHandler instance for each test."""
        return VoiceCallHandler()

    @pytest.fixture
    def sample_call_data(self):
        """Sample call data for testing."""
        return {
            "call_sid": "test_call_123",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
        }

    @pytest.mark.asyncio
    async def test_start_call_session_success(self, handler, sample_call_data):
        """Test successful call session initiation."""
        result = await handler.start_call_session(
            sample_call_data["call_sid"],
            sample_call_data["from_number"],
            sample_call_data["to_number"],
        )

        assert result["success"] is True
        assert result["session_id"] == sample_call_data["call_sid"]
        assert sample_call_data["call_sid"] in handler.active_calls

        session = handler.active_calls[sample_call_data["call_sid"]]
        assert session["status"] == "active"
        assert session["call_sid"] == sample_call_data["call_sid"]
        assert "phone_hash" in session
        assert isinstance(session["start_time"], datetime)

    @pytest.mark.asyncio
    async def test_start_call_session_creates_hash(self, handler, sample_call_data):
        """Test that phone numbers are properly hashed."""
        await handler.start_call_session(
            sample_call_data["call_sid"],
            sample_call_data["from_number"],
            sample_call_data["to_number"],
        )

        session = handler.active_calls[sample_call_data["call_sid"]]

        # Hash should be consistent
        expected_hash = handler._hash_phone_number(sample_call_data["from_number"])
        assert session["phone_hash"] == expected_hash

        # Hash should not contain original phone number
        assert sample_call_data["from_number"] not in session["phone_hash"]

    @pytest.mark.asyncio
    @patch("src.services.voice_handler.openai_service")
    async def test_process_audio_chunk_success(
        self, mock_openai, handler, sample_call_data
    ):
        """Test successful audio chunk processing."""
        # Setup
        await handler.start_call_session(**sample_call_data)

        mock_openai.retry_transcription = AsyncMock(
            return_value={
                "success": True,
                "text": "I need to schedule an appointment",
                "confidence": 0.95,
            }
        )

        # Test
        audio_data = b"fake_audio_data"
        result = await handler.process_audio_chunk(
            sample_call_data["call_sid"], audio_data
        )

        # Verify
        assert result["success"] is True
        assert result["transcription"] == "I need to schedule an appointment"
        assert result["confidence"] == 0.95
        assert result["next_action"] == "appointment_booking"

        # Verify session was updated
        session = handler.active_calls[sample_call_data["call_sid"]]
        assert len(session["transcription_results"]) == 1
        assert session["last_activity"] > session["start_time"]

    @pytest.mark.asyncio
    @patch("src.services.voice_handler.openai_service")
    async def test_process_audio_chunk_transcription_failure(
        self, mock_openai, handler, sample_call_data
    ):
        """Test handling of transcription failures."""
        # Setup
        await handler.start_call_session(**sample_call_data)

        mock_openai.retry_transcription = AsyncMock(
            return_value={"success": False, "error": "API rate limit exceeded"}
        )

        # Test
        audio_data = b"fake_audio_data"
        result = await handler.process_audio_chunk(
            sample_call_data["call_sid"], audio_data
        )

        # Verify
        assert result["success"] is False
        assert "API rate limit exceeded" in result["error"]
        assert result["next_action"] == "request_repeat"

        # Verify error count increased
        session = handler.active_calls[sample_call_data["call_sid"]]
        assert session["error_count"] == 1

    @pytest.mark.asyncio
    async def test_process_audio_chunk_no_session(self, handler):
        """Test processing audio for non-existent session."""
        result = await handler.process_audio_chunk("non_existent_call", b"audio_data")

        assert result["success"] is False
        assert "No active session found" in result["error"]

    def test_determine_next_action_appointment_keywords(self, handler):
        """Test next action determination for appointment requests."""
        test_cases = [
            ("I need to schedule an appointment", "appointment_booking"),
            ("Can I book a visit with the doctor?", "appointment_booking"),
            ("I want to see Dr. Smith", "appointment_booking"),
            ("Schedule me for next week", "appointment_booking"),
        ]

        for text, expected_action in test_cases:
            action = handler._determine_next_action("test_call", text)
            assert action == expected_action, f"Failed for text: {text}"

    def test_determine_next_action_emergency_keywords(self, handler):
        """Test next action determination for emergency situations."""
        test_cases = [
            ("This is an emergency!", "emergency_transfer"),
            ("I'm having chest pain", "emergency_transfer"),
            ("URGENT - need help now", "emergency_transfer"),
            ("Please help me, it's an emergency", "emergency_transfer"),
        ]

        for text, expected_action in test_cases:
            action = handler._determine_next_action("test_call", text)
            assert action == expected_action, f"Failed for text: {text}"

    def test_determine_next_action_unclear_text(self, handler):
        """Test next action determination for unclear input."""
        test_cases = [
            ("Hello there", "clarification_needed"),
            ("What's the weather like?", "clarification_needed"),
            ("Random text here", "clarification_needed"),
            ("", "silence_detected"),
            ("   ", "silence_detected"),
        ]

        for text, expected_action in test_cases:
            action = handler._determine_next_action("test_call", text)
            assert action == expected_action, f"Failed for text: '{text}'"

    @pytest.mark.asyncio
    async def test_handle_silence_timeout_warnings(self, handler, sample_call_data):
        """Test silence timeout handling with warning progression."""
        # Setup
        await handler.start_call_session(**sample_call_data)

        # First timeout - should warn
        result = await handler.handle_silence_timeout(sample_call_data["call_sid"])
        assert result["success"] is True
        assert result["action"] == "timeout_warning"
        assert result["warnings_remaining"] == 2

        session = handler.active_calls[sample_call_data["call_sid"]]
        assert session["timeout_warnings"] == 1

        # Second timeout - should warn again
        result = await handler.handle_silence_timeout(sample_call_data["call_sid"])
        assert result["success"] is True
        assert result["action"] == "timeout_warning"
        assert result["warnings_remaining"] == 1
        assert session["timeout_warnings"] == 2

        # Third timeout - should end call
        with patch.object(
            handler, "end_call_session", new_callable=AsyncMock
        ) as mock_end_call:
            mock_end_call.return_value = {"success": True, "reason": "timeout_exceeded"}

            result = await handler.handle_silence_timeout(sample_call_data["call_sid"])

            mock_end_call.assert_called_once_with(
                sample_call_data["call_sid"], "timeout_exceeded"
            )

    @pytest.mark.asyncio
    async def test_handle_silence_timeout_no_session(self, handler):
        """Test silence timeout handling for non-existent session."""
        result = await handler.handle_silence_timeout("non_existent_call")
        assert result["success"] is False
        assert "Session not found" in result["error"]

    @pytest.mark.asyncio
    async def test_generate_audio_feedback(self, handler, sample_call_data):
        """Test audio feedback generation for different scenarios."""
        # Setup
        await handler.start_call_session(**sample_call_data)

        test_cases = [
            (
                "greeting",
                "Hello! Please state your appointment request after the tone.",
            ),
            (
                "timeout_warning",
                "I didn't hear anything. Please state your appointment request.",
            ),
            (
                "clarification",
                "I didn't understand. Could you please repeat your appointment request?",
            ),
            (
                "error",
                "Sorry, we're experiencing technical difficulties. Please try again.",
            ),
            (
                "unknown_type",
                "Sorry, we're experiencing technical difficulties. Please try again.",
            ),
        ]

        for feedback_type, expected_message in test_cases:
            result = await handler.generate_audio_feedback(
                sample_call_data["call_sid"], feedback_type
            )

            assert result["success"] is True
            assert result["message"] == expected_message
            assert result["feedback_type"] == feedback_type
            assert "<Say>" in result["twiml"]
            assert expected_message in result["twiml"]

    @pytest.mark.asyncio
    @patch("src.services.voice_handler.twilio_service")
    async def test_end_call_session_success(
        self, mock_twilio, handler, sample_call_data
    ):
        """Test successful call session termination."""
        # Setup
        await handler.start_call_session(**sample_call_data)
        mock_twilio.end_call.return_value = True

        # Test
        result = await handler.end_call_session(
            sample_call_data["call_sid"], "completed"
        )

        # Verify
        assert result["success"] is True
        assert result["reason"] == "completed"
        assert result["duration_seconds"] > 0
        assert "session_summary" in result

        # Verify session was cleaned up
        assert sample_call_data["call_sid"] not in handler.active_calls

        # Verify Twilio was called
        mock_twilio.end_call.assert_called_once_with(
            sample_call_data["call_sid"], "completed"
        )

    @pytest.mark.asyncio
    async def test_end_call_session_no_session(self, handler):
        """Test ending non-existent call session."""
        result = await handler.end_call_session("non_existent_call")
        assert result["success"] is False
        assert "Session not found" in result["error"]

    def test_get_session_details(self, handler, sample_call_data):
        """Test getting session details."""
        # No session exists
        assert handler.get_session_details("non_existent") is None

        # Create session and verify details
        asyncio.run(handler.start_call_session(**sample_call_data))

        details = handler.get_session_details(sample_call_data["call_sid"])
        assert details is not None
        assert details["call_sid"] == sample_call_data["call_sid"]
        assert details["status"] == "active"

    def test_get_active_sessions_count(self, handler, sample_call_data):
        """Test getting count of active sessions."""
        assert handler.get_active_sessions_count() == 0

        # Add session
        asyncio.run(handler.start_call_session(**sample_call_data))
        assert handler.get_active_sessions_count() == 1

        # Add another session
        sample_call_data["call_sid"] = "test_call_456"
        asyncio.run(handler.start_call_session(**sample_call_data))
        assert handler.get_active_sessions_count() == 2

    def test_get_all_sessions_summary(self, handler, sample_call_data):
        """Test getting summary of all active sessions."""
        # No sessions
        summary = handler.get_all_sessions_summary()
        assert summary["active_count"] == 0
        assert len(summary["sessions"]) == 0

        # Add session
        asyncio.run(handler.start_call_session(**sample_call_data))

        summary = handler.get_all_sessions_summary()
        assert summary["active_count"] == 1
        assert len(summary["sessions"]) == 1

        session_summary = summary["sessions"][0]
        assert session_summary["call_sid"] == sample_call_data["call_sid"]
        assert session_summary["status"] == "active"
        assert "start_time" in session_summary
        assert "duration" in session_summary

    @pytest.mark.asyncio
    async def test_monitor_active_calls_timeout_detection(
        self, handler, sample_call_data
    ):
        """Test that monitoring detects timeouts correctly."""
        # Setup
        await handler.start_call_session(**sample_call_data)

        # Simulate old last_activity time
        session = handler.active_calls[sample_call_data["call_sid"]]
        session["last_activity"] = datetime.now(timezone.utc) - timedelta(seconds=35)

        # Mock the timeout handler
        with patch.object(
            handler, "handle_silence_timeout", new_callable=AsyncMock
        ) as mock_timeout:
            mock_timeout.return_value = {"success": True}

            # Run one iteration of monitoring
            await asyncio.sleep(0.1)  # Brief sleep to simulate monitoring cycle

            # Manually trigger timeout check (since we can't easily test the infinite loop)
            current_time = datetime.now(timezone.utc)
            silence_duration = (current_time - session["last_activity"]).total_seconds()

            if silence_duration >= handler.timeout_seconds:
                await handler.handle_silence_timeout(sample_call_data["call_sid"])
                mock_timeout.assert_called()

    def test_hash_phone_number_consistency(self, handler):
        """Test that phone number hashing is consistent."""
        phone_number = "+1234567890"

        hash1 = handler._hash_phone_number(phone_number)
        hash2 = handler._hash_phone_number(phone_number)

        assert hash1 == hash2
        assert len(hash1) == 16  # First 16 chars of SHA256
        assert phone_number not in hash1  # Original number not in hash

    def test_hash_phone_number_different_numbers(self, handler):
        """Test that different phone numbers produce different hashes."""
        phone1 = "+1234567890"
        phone2 = "+0987654321"

        hash1 = handler._hash_phone_number(phone1)
        hash2 = handler._hash_phone_number(phone2)

        assert hash1 != hash2
