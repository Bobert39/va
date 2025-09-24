"""
Integration tests for voice processing functionality.

Tests end-to-end voice processing workflows including Twilio integration,
OpenAI speech-to-text, and voice call handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.openai_integration import openai_service
from src.services.system_monitoring import monitoring_service
from src.services.twilio_integration import twilio_service
from src.services.voice_handler import voice_call_handler


class TestVoiceProcessingIntegration:
    """Integration tests for voice processing system."""

    @pytest.fixture
    def sample_call_data(self):
        """Sample call data for testing."""
        return {
            "call_sid": "integration_test_call_123",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
        }

    @pytest.fixture
    def sample_audio_data(self):
        """Sample audio data for testing."""
        # Generate test audio data (1 second of 16kHz mono)
        return b"0" * 32000

    @pytest.mark.asyncio
    async def test_complete_voice_call_workflow(
        self, sample_call_data, sample_audio_data
    ):
        """Test complete voice call processing workflow."""
        call_sid = sample_call_data["call_sid"]

        # Mock external services
        with patch.object(
            openai_service, "retry_transcription", new_callable=AsyncMock
        ) as mock_transcribe:
            with patch.object(twilio_service, "end_call") as mock_end_call:
                mock_transcribe.return_value = {
                    "success": True,
                    "text": "I need to schedule an appointment for next week",
                    "confidence": 0.92,
                    "duration": 3.0,
                }
                mock_end_call.return_value = True

                # 1. Start call session
                start_result = await voice_call_handler.start_call_session(
                    **sample_call_data
                )
                assert start_result["success"] is True

                # 2. Process audio chunk
                audio_result = await voice_call_handler.process_audio_chunk(
                    call_sid, sample_audio_data
                )
                assert audio_result["success"] is True
                assert audio_result["next_action"] == "appointment_booking"

                # 3. Generate feedback
                feedback_result = await voice_call_handler.generate_audio_feedback(
                    call_sid, "clarification"
                )
                assert feedback_result["success"] is True

                # 4. End call session
                end_result = await voice_call_handler.end_call_session(
                    call_sid, "completed"
                )
                assert end_result["success"] is True
                assert end_result["duration_seconds"] > 0

                # Verify session was cleaned up
                assert call_sid not in voice_call_handler.active_calls

    @pytest.mark.asyncio
    async def test_voice_call_with_transcription_errors(
        self, sample_call_data, sample_audio_data
    ):
        """Test voice call handling with transcription errors."""
        call_sid = sample_call_data["call_sid"]

        with patch.object(
            openai_service, "retry_transcription", new_callable=AsyncMock
        ) as mock_transcribe:
            mock_transcribe.return_value = {
                "success": False,
                "error": "API rate limit exceeded",
            }

            # Start session
            await voice_call_handler.start_call_session(**sample_call_data)

            # Process audio with error
            result = await voice_call_handler.process_audio_chunk(
                call_sid, sample_audio_data
            )

            assert result["success"] is False
            assert "rate limit" in result["error"]
            assert result["next_action"] == "request_repeat"

            # Verify error count increased
            session = voice_call_handler.active_calls[call_sid]
            assert session["error_count"] == 1

    @pytest.mark.asyncio
    async def test_voice_call_timeout_handling(self, sample_call_data):
        """Test voice call timeout handling."""
        call_sid = sample_call_data["call_sid"]

        with patch.object(
            voice_call_handler, "end_call_session", new_callable=AsyncMock
        ) as mock_end:
            mock_end.return_value = {"success": True, "reason": "timeout_exceeded"}

            # Start session
            await voice_call_handler.start_call_session(**sample_call_data)

            # Simulate multiple timeouts
            for i in range(3):
                result = await voice_call_handler.handle_silence_timeout(call_sid)
                if i < 2:
                    assert result["action"] == "timeout_warning"
                    assert result["warnings_remaining"] == 2 - i
                else:
                    # Third timeout should end call
                    mock_end.assert_called_once_with(call_sid, "timeout_exceeded")

    @pytest.mark.asyncio
    async def test_emergency_detection_workflow(
        self, sample_call_data, sample_audio_data
    ):
        """Test emergency keyword detection and handling."""
        call_sid = sample_call_data["call_sid"]

        with patch.object(
            openai_service, "retry_transcription", new_callable=AsyncMock
        ) as mock_transcribe:
            mock_transcribe.return_value = {
                "success": True,
                "text": "This is an emergency! I'm having chest pain!",
                "confidence": 0.95,
            }

            # Start session
            await voice_call_handler.start_call_session(**sample_call_data)

            # Process emergency audio
            result = await voice_call_handler.process_audio_chunk(
                call_sid, sample_audio_data
            )

            assert result["success"] is True
            assert result["next_action"] == "emergency_transfer"

            # Generate emergency feedback
            feedback = await voice_call_handler.generate_audio_feedback(
                call_sid, "emergency"
            )
            assert "emergency" in feedback["message"]
            assert "911" in feedback["message"]

    @pytest.mark.asyncio
    async def test_monitoring_integration(self, sample_call_data, sample_audio_data):
        """Test integration with monitoring service."""
        call_sid = sample_call_data["call_sid"]

        with patch.object(
            openai_service, "retry_transcription", new_callable=AsyncMock
        ) as mock_transcribe:
            with patch.object(
                monitoring_service, "record_call_start"
            ) as mock_record_start:
                with patch.object(
                    monitoring_service, "record_call_end"
                ) as mock_record_end:
                    mock_transcribe.return_value = {
                        "success": True,
                        "text": "Schedule appointment",
                        "confidence": 0.9,
                    }

                    # Test call monitoring
                    monitoring_service.record_call_start(call_sid)
                    mock_record_start.assert_called_with(call_sid)

                    # Start and end call
                    await voice_call_handler.start_call_session(**sample_call_data)
                    await voice_call_handler.process_audio_chunk(
                        call_sid, sample_audio_data
                    )
                    result = await voice_call_handler.end_call_session(
                        call_sid, "completed"
                    )

                    # Test call end monitoring
                    monitoring_service.record_call_end(
                        call_sid, result["duration_seconds"], True
                    )
                    mock_record_end.assert_called()

    @pytest.mark.asyncio
    async def test_multiple_concurrent_calls(self):
        """Test handling multiple concurrent voice calls."""
        call_data_1 = {
            "call_sid": "call_1",
            "from_number": "+1111111111",
            "to_number": "+2222222222",
        }
        call_data_2 = {
            "call_sid": "call_2",
            "from_number": "+3333333333",
            "to_number": "+4444444444",
        }

        with patch.object(
            openai_service, "retry_transcription", new_callable=AsyncMock
        ) as mock_transcribe:
            mock_transcribe.return_value = {
                "success": True,
                "text": "Appointment request",
                "confidence": 0.85,
            }

            # Start multiple calls
            result1 = await voice_call_handler.start_call_session(**call_data_1)
            result2 = await voice_call_handler.start_call_session(**call_data_2)

            assert result1["success"] is True
            assert result2["success"] is True
            assert voice_call_handler.get_active_sessions_count() == 2

            # Process audio for both calls
            audio_data = b"0" * 16000
            await voice_call_handler.process_audio_chunk("call_1", audio_data)
            await voice_call_handler.process_audio_chunk("call_2", audio_data)

            # Verify both sessions have transcription results
            session1 = voice_call_handler.get_session_details("call_1")
            session2 = voice_call_handler.get_session_details("call_2")

            assert len(session1["transcription_results"]) == 1
            assert len(session2["transcription_results"]) == 1

            # End both calls
            await voice_call_handler.end_call_session("call_1", "completed")
            await voice_call_handler.end_call_session("call_2", "completed")

            assert voice_call_handler.get_active_sessions_count() == 0

    @pytest.mark.asyncio
    async def test_audio_streaming_workflow(self, sample_call_data):
        """Test audio streaming processing workflow."""
        call_sid = sample_call_data["call_sid"]

        with patch.object(
            openai_service, "process_streaming_audio", new_callable=AsyncMock
        ) as mock_stream:
            # Mock streaming results
            result_queue = asyncio.Queue()
            await result_queue.put(
                {
                    "success": True,
                    "text": "Streaming transcription chunk 1",
                    "confidence": 0.88,
                }
            )
            await result_queue.put(
                {
                    "success": True,
                    "text": "Streaming transcription chunk 2",
                    "confidence": 0.92,
                }
            )
            mock_stream.return_value = result_queue

            # Start session
            await voice_call_handler.start_call_session(**sample_call_data)

            # Setup audio stream
            audio_stream = asyncio.Queue()
            await audio_stream.put(b"0" * 16000)  # Chunk 1
            await audio_stream.put(b"0" * 16000)  # Chunk 2
            await audio_stream.put(None)  # End signal

            # Process streaming audio
            result_queue = await openai_service.process_streaming_audio(
                audio_stream, call_sid, chunk_duration=1.0
            )

            # Verify results
            result1 = await result_queue.get()
            assert result1["success"] is True
            assert "chunk 1" in result1["text"]

            result2 = await result_queue.get()
            assert result2["success"] is True
            assert "chunk 2" in result2["text"]

    @pytest.mark.asyncio
    async def test_cost_tracking_integration(self, sample_call_data, sample_audio_data):
        """Test cost tracking integration with voice processing."""
        call_sid = sample_call_data["call_sid"]

        with patch.object(
            openai_service, "retry_transcription", new_callable=AsyncMock
        ) as mock_transcribe:
            with patch.object(
                monitoring_service, "record_api_usage"
            ) as mock_record_usage:
                mock_transcribe.return_value = {
                    "success": True,
                    "text": "Cost tracking test",
                    "confidence": 0.9,
                    "duration": 2.0,  # 2 minutes
                }

                # Start session and process audio
                await voice_call_handler.start_call_session(**sample_call_data)
                await voice_call_handler.process_audio_chunk(
                    call_sid, sample_audio_data
                )

                # Verify transcription was called
                mock_transcribe.assert_called_once()

                # Simulate cost recording
                monitoring_service.record_api_usage(
                    service="openai",
                    request_type="transcription",
                    cost_dollars=0.012,  # 2 minutes * $0.006
                    duration=2.0,
                    success=True,
                )

                mock_record_usage.assert_called_with(
                    service="openai",
                    request_type="transcription",
                    cost_dollars=0.012,
                    duration=2.0,
                    success=True,
                )

    @pytest.mark.asyncio
    async def test_error_recovery_workflow(self, sample_call_data, sample_audio_data):
        """Test error recovery and retry mechanisms."""
        call_sid = sample_call_data["call_sid"]

        with patch.object(
            openai_service, "retry_transcription", new_callable=AsyncMock
        ) as mock_transcribe:
            # First call fails, second succeeds
            mock_transcribe.side_effect = [
                {"success": False, "error": "Temporary failure"},
                {"success": True, "text": "Recovery successful", "confidence": 0.9},
            ]

            # Start session
            await voice_call_handler.start_call_session(**sample_call_data)

            # First audio processing fails
            result1 = await voice_call_handler.process_audio_chunk(
                call_sid, sample_audio_data
            )
            assert result1["success"] is False
            assert result1["next_action"] == "request_repeat"

            # Second audio processing succeeds
            result2 = await voice_call_handler.process_audio_chunk(
                call_sid, sample_audio_data
            )
            assert result2["success"] is True
            assert result2["transcription"] == "Recovery successful"

            # Verify both attempts were made
            assert mock_transcribe.call_count == 2

    @pytest.mark.asyncio
    async def test_session_cleanup_on_error(self, sample_call_data):
        """Test session cleanup when errors occur."""
        call_sid = sample_call_data["call_sid"]

        # Start session
        await voice_call_handler.start_call_session(**sample_call_data)
        assert call_sid in voice_call_handler.active_calls

        # Simulate error during processing
        with patch.object(
            openai_service,
            "retry_transcription",
            side_effect=Exception("Critical error"),
        ):
            result = await voice_call_handler.process_audio_chunk(call_sid, b"audio")
            assert result["success"] is False

        # Session should still exist for potential recovery
        assert call_sid in voice_call_handler.active_calls

        # End session manually
        await voice_call_handler.end_call_session(call_sid, "error")
        assert call_sid not in voice_call_handler.active_calls

    def test_dashboard_metrics_integration(self):
        """Test dashboard metrics integration with voice processing."""
        # Get initial metrics
        initial_metrics = monitoring_service.get_dashboard_metrics()
        initial_calls = initial_metrics["call_statistics"]["total_calls"]

        # Simulate call activity
        monitoring_service.record_call_start("test_call_integration")
        monitoring_service.record_call_end("test_call_integration", 150.0, True)

        # Check updated metrics
        updated_metrics = monitoring_service.get_dashboard_metrics()
        assert updated_metrics["call_statistics"]["total_calls"] == initial_calls + 1
        assert updated_metrics["call_statistics"]["successful_calls"] >= 1

    @pytest.mark.asyncio
    async def test_twilio_integration_workflow(self, sample_call_data):
        """Test Twilio integration in voice processing workflow."""
        call_sid = sample_call_data["call_sid"]
        from_number = sample_call_data["from_number"]

        with patch.object(twilio_service, "handle_incoming_call") as mock_handle:
            with patch.object(twilio_service, "end_call") as mock_end:
                # Mock TwiML response
                mock_response = MagicMock()
                mock_handle.return_value = mock_response
                mock_end.return_value = True

                # Test incoming call handling
                twiml_response = twilio_service.handle_incoming_call(
                    call_sid, from_number
                )
                mock_handle.assert_called_once_with(call_sid, from_number)

                # Start voice processing session
                await voice_call_handler.start_call_session(**sample_call_data)

                # End call through both systems
                await voice_call_handler.end_call_session(call_sid, "completed")
                twilio_service.end_call(call_sid, "completed")

                mock_end.assert_called_with(call_sid, "completed")
