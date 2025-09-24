"""
Integration tests for Voice Confirmation Flow

Tests the complete TTS voice confirmation workflow including VoiceCallHandler,
ConversationManager, TTSService integration, and end-to-end flow scenarios.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.conversation_manager import ConversationManager
from src.services.tts_service import TTSService
from src.services.voice_handler import VoiceCallHandler


class TestVoiceConfirmationFlowIntegration:
    """Integration tests for complete voice confirmation workflow."""

    @pytest.fixture
    def voice_handler(self):
        """Create VoiceCallHandler instance with mocked dependencies."""
        with patch("src.services.voice_handler.twilio_service"), patch(
            "src.services.voice_handler.openai_service"
        ), patch("src.services.voice_handler.EMROAuthClient"), patch(
            "src.services.voice_handler.AppointmentCreator"
        ), patch(
            "src.services.voice_handler.ConfirmationGenerator"
        ):
            handler = VoiceCallHandler()
            return handler

    @pytest.fixture
    def sample_call_sid(self, voice_handler):
        """Create a sample call session."""
        call_sid = "test-call-123"
        # Simulate starting a call session
        session_data = {
            "call_sid": call_sid,
            "start_time": datetime.now(timezone.utc),
            "phone_hash": "test-hash",
            "from_number_hash": "from-hash",
            "to_number_hash": "to-hash",
            "status": "active",
            "last_activity": datetime.now(timezone.utc),
            "transcription_results": [],
            "conversation_state": "greeting",
            "timeout_warnings": 0,
            "error_count": 0,
            "appointment_data": None,
            "confirmation_number": None,
            "conversation_session_id": None,
            "tts_confirmation_state": "none",
            "confirmation_audio_url": None,
        }
        voice_handler.active_calls[call_sid] = session_data
        return call_sid

    @pytest.fixture
    def sample_appointment_details(self):
        """Sample appointment details for testing."""
        return {
            "appointment_id": "appt-789",
            "date": "2024-03-25",
            "time": "09:30",
            "provider_name": "Dr. Williams",
            "location": "Downtown Office",
            "appointment_type": "consultation",
            "patient_name": "Jane Smith",
            "confirmation_number": "CONF-12345",
        }

    @pytest.mark.asyncio
    async def test_complete_tts_confirmation_flow_success(
        self, voice_handler, sample_call_sid, sample_appointment_details
    ):
        """Test complete successful TTS confirmation flow from start to finish."""
        # Mock TTS service to return successful audio generation
        mock_tts_result = {
            "success": True,
            "audio_data": b"confirmation_audio_bytes",
            "text": "I have scheduled your consultation on Monday, March 25th at 9:30 AM with Dr. Williams at our Downtown Office location. Please say 'yes' to confirm or 'no' if you need to make changes.",
            "original_text": "Original confirmation text",
            "character_count": 150,
            "duration_estimate": 8.5,
            "voice_model": "alloy",
        }

        mock_greeting_result = {
            "success": True,
            "audio_data": b"greeting_audio_bytes",
            "text": "Thank you for confirming your appointment. We look forward to seeing you. Have a great day!",
        }

        with patch("src.services.voice_handler.tts_service") as mock_tts, patch(
            "src.services.voice_handler.conversation_manager"
        ) as mock_conv_mgr:
            # Mock conversation manager responses
            mock_conv_mgr.start_session.return_value = "conv-session-123"
            mock_conv_mgr.start_confirmation_flow.return_value = {
                "session_id": "conv-session-123",
                "confirmation_state": "pending",
                "exchange_count": 1,
                "remaining_exchanges": 4,
                "appointment_details": sample_appointment_details,
                "next_action": "play_confirmation_audio",
            }
            mock_conv_mgr.process_confirmation_response.return_value = {
                "session_id": "conv-session-123",
                "confirmation_state": "confirmed",
                "exchange_count": 2,
                "remaining_exchanges": 3,
                "user_response": "yes",
                "next_action": "complete_appointment",
                "interpretation": {
                    "confirmed": True,
                    "declined": False,
                    "needs_changes": False,
                },
            }

            # Mock TTS service responses
            mock_tts.generate_confirmation_audio.return_value = mock_tts_result
            mock_tts.create_practice_greeting_audio.return_value = mock_greeting_result

            # Step 1: Start TTS confirmation flow
            confirmation_result = await voice_handler.start_tts_confirmation_flow(
                call_sid=sample_call_sid, appointment_details=sample_appointment_details
            )

            # Verify confirmation flow started successfully
            assert confirmation_result["success"] is True
            assert (
                confirmation_result["confirmation_audio"] == b"confirmation_audio_bytes"
            )
            assert confirmation_result["next_action"] == "play_confirmation_audio"
            assert "twiml" in confirmation_result

            # Verify session state updates
            session = voice_handler.active_calls[sample_call_sid]
            assert session["tts_confirmation_state"] == "pending"
            assert session["conversation_session_id"] == "conv-session-123"
            assert session["appointment_data"] == sample_appointment_details

            # Step 2: Process patient's "yes" response
            response_result = await voice_handler.process_tts_confirmation_response(
                call_sid=sample_call_sid, user_response="yes"
            )

            # Verify successful confirmation
            assert response_result["success"] is True
            assert response_result["confirmation_state"] == "confirmed"
            assert response_result["next_action"] == "complete_call"
            assert "Thank you for confirming" in response_result["message"]
            assert session["conversation_state"] == "appointment_confirmed"

            # Verify all services were called correctly
            mock_conv_mgr.start_session.assert_called_once()
            mock_conv_mgr.start_confirmation_flow.assert_called_once()
            mock_conv_mgr.process_confirmation_response.assert_called_once()
            mock_tts.generate_confirmation_audio.assert_called_once()
            mock_tts.create_practice_greeting_audio.assert_called_once()

    @pytest.mark.asyncio
    async def test_tts_confirmation_flow_patient_declines(
        self, voice_handler, sample_call_sid, sample_appointment_details
    ):
        """Test TTS confirmation flow when patient declines appointment."""
        mock_tts_result = {
            "success": True,
            "audio_data": b"confirmation_audio_bytes",
            "text": "Confirmation text",
            "character_count": 100,
            "duration_estimate": 5.0,
        }

        with patch("src.services.voice_handler.tts_service") as mock_tts, patch(
            "src.services.voice_handler.conversation_manager"
        ) as mock_conv_mgr:
            # Mock conversation manager responses for decline flow
            mock_conv_mgr.start_session.return_value = "conv-session-123"
            mock_conv_mgr.start_confirmation_flow.return_value = {
                "session_id": "conv-session-123",
                "confirmation_state": "pending",
                "exchange_count": 1,
                "remaining_exchanges": 4,
                "next_action": "play_confirmation_audio",
            }
            mock_conv_mgr.process_confirmation_response.return_value = {
                "session_id": "conv-session-123",
                "confirmation_state": "declined",
                "exchange_count": 2,
                "remaining_exchanges": 3,
                "user_response": "no",
                "next_action": "cancel_appointment",
                "interpretation": {
                    "confirmed": False,
                    "declined": True,
                    "needs_changes": False,
                },
            }

            mock_tts.generate_confirmation_audio.return_value = mock_tts_result

            # Start confirmation flow
            await voice_handler.start_tts_confirmation_flow(
                call_sid=sample_call_sid, appointment_details=sample_appointment_details
            )

            # Process decline response
            response_result = await voice_handler.process_tts_confirmation_response(
                call_sid=sample_call_sid, user_response="no"
            )

            # Verify decline handling
            assert response_result["success"] is True
            assert response_result["confirmation_state"] == "declined"
            assert response_result["next_action"] == "handle_cancellation"
            assert "cancelled" in response_result["message"]

            session = voice_handler.active_calls[sample_call_sid]
            assert session["conversation_state"] == "appointment_cancelled"

    @pytest.mark.asyncio
    async def test_tts_confirmation_flow_patient_requests_changes(
        self, voice_handler, sample_call_sid, sample_appointment_details
    ):
        """Test TTS confirmation flow when patient requests changes."""
        mock_tts_result = {
            "success": True,
            "audio_data": b"confirmation_audio_bytes",
            "text": "Confirmation text",
            "character_count": 100,
            "duration_estimate": 5.0,
        }

        with patch("src.services.voice_handler.tts_service") as mock_tts, patch(
            "src.services.voice_handler.conversation_manager"
        ) as mock_conv_mgr:
            mock_conv_mgr.start_session.return_value = "conv-session-123"
            mock_conv_mgr.start_confirmation_flow.return_value = {
                "session_id": "conv-session-123",
                "confirmation_state": "pending",
                "exchange_count": 1,
                "remaining_exchanges": 4,
                "next_action": "play_confirmation_audio",
            }
            mock_conv_mgr.process_confirmation_response.return_value = {
                "session_id": "conv-session-123",
                "confirmation_state": "needs_changes",
                "exchange_count": 2,
                "remaining_exchanges": 3,
                "user_response": "I need to change the time",
                "next_action": "request_changes",
                "interpretation": {
                    "confirmed": False,
                    "declined": False,
                    "needs_changes": True,
                },
            }

            mock_tts.generate_confirmation_audio.return_value = mock_tts_result

            # Start confirmation flow
            await voice_handler.start_tts_confirmation_flow(
                call_sid=sample_call_sid, appointment_details=sample_appointment_details
            )

            # Process change request
            response_result = await voice_handler.process_tts_confirmation_response(
                call_sid=sample_call_sid, user_response="I need to change the time"
            )

            # Verify change request handling
            assert response_result["success"] is True
            assert response_result["confirmation_state"] == "needs_changes"
            assert response_result["next_action"] == "gather_changes"
            assert "what you'd like to change" in response_result["message"]

            session = voice_handler.active_calls[sample_call_sid]
            assert session["conversation_state"] == "appointment_changes_requested"

    @pytest.mark.asyncio
    async def test_tts_confirmation_flow_exchange_limit_exceeded(
        self, voice_handler, sample_call_sid, sample_appointment_details
    ):
        """Test TTS confirmation flow when exchange limit is exceeded."""
        mock_tts_result = {
            "success": True,
            "audio_data": b"confirmation_audio_bytes",
            "text": "Confirmation text",
            "character_count": 100,
            "duration_estimate": 5.0,
        }

        with patch("src.services.voice_handler.tts_service") as mock_tts, patch(
            "src.services.voice_handler.conversation_manager"
        ) as mock_conv_mgr:
            mock_conv_mgr.start_session.return_value = "conv-session-123"
            mock_conv_mgr.start_confirmation_flow.return_value = {
                "session_id": "conv-session-123",
                "confirmation_state": "pending",
                "exchange_count": 1,
                "remaining_exchanges": 4,
                "next_action": "play_confirmation_audio",
            }

            # Mock reaching exchange limit
            mock_conv_mgr.process_confirmation_response.return_value = {
                "session_id": "conv-session-123",
                "confirmation_state": "pending",
                "exchange_count": 5,
                "remaining_exchanges": 0,
                "user_response": "unclear response",
                "next_action": "human_handoff",
                "interpretation": {
                    "confirmed": False,
                    "declined": False,
                    "needs_changes": False,
                },
            }

            mock_conv_mgr.check_exchange_limit.return_value = {
                "session_id": "conv-session-123",
                "exchange_count": 5,
                "max_exchanges": 5,
                "within_limit": False,
                "remaining_exchanges": 0,
                "should_complete": True,
            }

            mock_tts.generate_confirmation_audio.return_value = mock_tts_result

            # Start confirmation flow
            await voice_handler.start_tts_confirmation_flow(
                call_sid=sample_call_sid, appointment_details=sample_appointment_details
            )

            # Process unclear response that triggers limit
            response_result = await voice_handler.process_tts_confirmation_response(
                call_sid=sample_call_sid, user_response="unclear response"
            )

            # Verify human handoff
            assert response_result["success"] is True
            assert response_result["next_action"] == "human_handoff"
            assert "connect you with our staff" in response_result["message"]

    @pytest.mark.asyncio
    async def test_tts_fallback_mode_when_audio_generation_fails(
        self, voice_handler, sample_call_sid, sample_appointment_details
    ):
        """Test fallback to text-based confirmation when TTS audio generation fails."""
        mock_tts_failure = {
            "success": False,
            "audio_data": None,
            "error": "TTS API error",
            "text": "",
        }

        with patch("src.services.voice_handler.tts_service") as mock_tts, patch(
            "src.services.voice_handler.conversation_manager"
        ) as mock_conv_mgr:
            mock_conv_mgr.start_session.return_value = "conv-session-123"
            mock_conv_mgr.start_confirmation_flow.return_value = {
                "session_id": "conv-session-123",
                "confirmation_state": "pending",
                "exchange_count": 1,
                "remaining_exchanges": 4,
                "next_action": "play_confirmation_audio",
            }

            mock_tts.generate_confirmation_audio.return_value = mock_tts_failure

            # Start confirmation flow
            confirmation_result = await voice_handler.start_tts_confirmation_flow(
                call_sid=sample_call_sid, appointment_details=sample_appointment_details
            )

            # Verify fallback mode
            assert confirmation_result["success"] is True
            assert confirmation_result["fallback_mode"] is True
            assert confirmation_result["next_action"] == "play_fallback_confirmation"
            assert (
                "I have scheduled your appointment"
                in confirmation_result["confirmation_text"]
            )

            session = voice_handler.active_calls[sample_call_sid]
            assert session["tts_confirmation_state"] == "fallback"

    @pytest.mark.asyncio
    async def test_mid_conversation_hangup_handling(
        self, voice_handler, sample_call_sid, sample_appointment_details
    ):
        """Test graceful handling of mid-conversation hangups."""
        with patch("src.services.voice_handler.conversation_manager") as mock_conv_mgr:
            mock_conv_mgr.handle_mid_conversation_hangup.return_value = {
                "session_id": "conv-session-123",
                "status": "hangup_handled",
                "summary": {"session_id": "conv-session-123", "duration_seconds": 45},
                "partial_data": {
                    "appointment_details": sample_appointment_details,
                    "exchange_count": 2,
                    "confirmation_state": "pending",
                },
                "follow_up_recommended": True,
            }

            # Set up session in confirmation state
            session = voice_handler.active_calls[sample_call_sid]
            session["conversation_session_id"] = "conv-session-123"
            session["tts_confirmation_state"] = "pending"

            # Handle hangup
            hangup_result = await voice_handler.handle_tts_mid_conversation_hangup(
                call_sid=sample_call_sid
            )

            # Verify hangup handling
            assert hangup_result["success"] is True
            assert hangup_result["hangup_handled"] is True
            assert hangup_result["follow_up_recommended"] is True
            assert hangup_result["partial_data"] is not None

            # Verify conversation manager was called
            mock_conv_mgr.handle_mid_conversation_hangup.assert_called_once_with(
                session_id="conv-session-123"
            )

    @pytest.mark.asyncio
    async def test_end_to_end_flow_with_real_services_mocked(self):
        """Test end-to-end flow with realistic service interactions."""
        # This test simulates a complete flow with more realistic mocking
        voice_handler = VoiceCallHandler()

        with patch.multiple(
            "src.services.voice_handler",
            tts_service=Mock(),
            conversation_manager=Mock(),
            twilio_service=Mock(),
            openai_service=Mock(),
            EMROAuthClient=Mock(),
            AppointmentCreator=Mock(),
            ConfirmationGenerator=Mock(),
        ) as mocks:
            # Set up realistic mock responses
            mocks["conversation_manager"].start_session = AsyncMock(
                return_value="session-456"
            )
            mocks["conversation_manager"].start_confirmation_flow = AsyncMock(
                return_value={
                    "session_id": "session-456",
                    "confirmation_state": "pending",
                    "exchange_count": 1,
                    "remaining_exchanges": 4,
                    "next_action": "play_confirmation_audio",
                }
            )
            mocks["conversation_manager"].process_confirmation_response = AsyncMock(
                return_value={
                    "session_id": "session-456",
                    "confirmation_state": "confirmed",
                    "exchange_count": 2,
                    "remaining_exchanges": 3,
                    "user_response": "yes",
                    "next_action": "complete_appointment",
                    "interpretation": {
                        "confirmed": True,
                        "declined": False,
                        "needs_changes": False,
                    },
                }
            )

            mocks["tts_service"].generate_confirmation_audio = AsyncMock(
                return_value={
                    "success": True,
                    "audio_data": b"realistic_audio_data",
                    "text": "Professional confirmation message",
                    "character_count": 200,
                    "duration_estimate": 12.0,
                }
            )

            mocks["tts_service"].create_practice_greeting_audio = AsyncMock(
                return_value={
                    "success": True,
                    "audio_data": b"greeting_audio_data",
                    "text": "Thank you message",
                }
            )

            # Start call session
            call_result = await voice_handler.start_call_session(
                call_sid="test-call-456",
                from_number="+1234567890",
                to_number="+1987654321",
            )

            assert call_result["success"] is True

            # Test complete confirmation flow
            appointment_details = {
                "appointment_id": "appt-456",
                "date": "2024-04-01",
                "time": "10:00",
                "provider_name": "Dr. Test",
                "location": "Test Clinic",
                "appointment_type": "annual_checkup",
            }

            # Start TTS confirmation
            confirmation_result = await voice_handler.start_tts_confirmation_flow(
                call_sid="test-call-456", appointment_details=appointment_details
            )

            assert confirmation_result["success"] is True
            assert len(confirmation_result["confirmation_audio"]) > 0

            # Process confirmation response
            response_result = await voice_handler.process_tts_confirmation_response(
                call_sid="test-call-456", user_response="yes, that's correct"
            )

            assert response_result["success"] is True
            assert response_result["confirmation_state"] == "confirmed"

            # Verify all async methods were called
            mocks["conversation_manager"].start_session.assert_called_once()
            mocks["conversation_manager"].start_confirmation_flow.assert_called_once()
            mocks[
                "conversation_manager"
            ].process_confirmation_response.assert_called_once()
            mocks["tts_service"].generate_confirmation_audio.assert_called_once()
            mocks["tts_service"].create_practice_greeting_audio.assert_called_once()


class TestVoiceConfirmationFlowErrorHandling:
    """Test error handling throughout the voice confirmation flow."""

    @pytest.mark.asyncio
    async def test_tts_service_failure_recovery(self):
        """Test recovery when TTS service completely fails."""
        voice_handler = VoiceCallHandler()

        with patch("src.services.voice_handler.tts_service") as mock_tts, patch(
            "src.services.voice_handler.conversation_manager"
        ) as mock_conv_mgr:
            # Mock complete TTS service failure
            mock_tts.generate_confirmation_audio.side_effect = Exception(
                "TTS service down"
            )
            mock_conv_mgr.start_session.return_value = "session-error"
            mock_conv_mgr.start_confirmation_flow.return_value = {
                "session_id": "session-error",
                "confirmation_state": "pending",
                "exchange_count": 1,
                "remaining_exchanges": 4,
                "next_action": "play_confirmation_audio",
            }

            # Set up call session
            call_sid = "error-call-123"
            voice_handler.active_calls[call_sid] = {
                "call_sid": call_sid,
                "start_time": datetime.now(timezone.utc),
                "phone_hash": "error-hash",
                "conversation_session_id": None,
                "tts_confirmation_state": "none",
            }

            # Attempt confirmation flow
            result = await voice_handler.start_tts_confirmation_flow(
                call_sid=call_sid, appointment_details={"appointment_id": "test"}
            )

            # Should fail gracefully with human handoff
            assert result["success"] is False
            assert result["next_action"] == "human_handoff"
            assert "having trouble" in result["message"]

    @pytest.mark.asyncio
    async def test_conversation_manager_failure_recovery(self):
        """Test recovery when conversation manager fails."""
        voice_handler = VoiceCallHandler()

        with patch("src.services.voice_handler.conversation_manager") as mock_conv_mgr:
            # Mock conversation manager failure
            mock_conv_mgr.start_session.side_effect = Exception(
                "ConversationManager error"
            )

            # Set up call session
            call_sid = "conv-error-123"
            voice_handler.active_calls[call_sid] = {
                "call_sid": call_sid,
                "start_time": datetime.now(timezone.utc),
                "phone_hash": "error-hash",
                "conversation_session_id": None,
                "tts_confirmation_state": "none",
            }

            # Attempt confirmation flow
            result = await voice_handler.start_tts_confirmation_flow(
                call_sid=call_sid, appointment_details={"appointment_id": "test"}
            )

            # Should fail gracefully
            assert result["success"] is False
            assert result["next_action"] == "human_handoff"


if __name__ == "__main__":
    pytest.main([__file__])
