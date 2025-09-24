"""
Unit tests for OpenAI Integration Service.

Tests speech-to-text processing, error handling, cost tracking,
and audio format conversion.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from src.services.openai_integration import OpenAIIntegrationService


class TestOpenAIIntegrationService:
    """Test cases for OpenAI Integration Service."""

    @pytest.fixture
    def service(self):
        """Create a fresh OpenAI service instance for each test."""
        with patch("src.services.openai_integration.get_config") as mock_config:
            mock_config.return_value = "test_api_key"
            return OpenAIIntegrationService()

    @pytest.fixture
    def mock_openai_response(self):
        """Mock successful OpenAI API response."""
        response = MagicMock()
        response.text = "I need to schedule an appointment"
        response.language = "en"
        response.confidence = 0.95
        response.segments = []
        return response

    @pytest.mark.asyncio
    async def test_transcribe_audio_success(self, service, mock_openai_response):
        """Test successful audio transcription."""
        audio_data = b"fake_audio_data_16khz_wav"

        with patch.object(
            service.client.audio.transcriptions,
            "create",
            return_value=mock_openai_response,
        ):
            with patch("builtins.open", mock_open()):
                with patch("tempfile.NamedTemporaryFile") as mock_temp:
                    mock_temp.return_value.__enter__.return_value.name = "test.wav"

                    result = await service.transcribe_audio(
                        audio_data=audio_data,
                        audio_format="wav",
                        language="en",
                        call_id="test_call_123",
                    )

        assert result["success"] is True
        assert result["text"] == "I need to schedule an appointment"
        assert result["language"] == "en"
        assert result["confidence"] == 0.95
        assert "timestamp" in result
        assert result["duration"] > 0

    @pytest.mark.asyncio
    async def test_transcribe_audio_api_failure(self, service):
        """Test handling of OpenAI API failures."""
        audio_data = b"fake_audio_data"

        with patch.object(
            service.client.audio.transcriptions,
            "create",
            side_effect=Exception("API Error"),
        ):
            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "test.wav"

                result = await service.transcribe_audio(
                    audio_data=audio_data, call_id="test_call_123"
                )

        assert result["success"] is False
        assert "API Error" in result["error"]
        assert result["text"] == ""
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_transcribe_audio_no_client(self):
        """Test transcription when OpenAI client is not initialized."""
        with patch("src.services.openai_integration.get_config", return_value=None):
            service = OpenAIIntegrationService()

        result = await service.transcribe_audio(b"audio_data")

        assert result["success"] is False
        assert "not initialized" in result["error"]

    def test_calculate_audio_duration(self, service):
        """Test audio duration calculation."""
        # Test data for 1 second of 16kHz mono audio (16000 samples * 2 bytes)
        one_second_audio = b"0" * 32000

        duration = service._calculate_audio_duration(one_second_audio, "wav")

        # Should be approximately 1/60 minute (1 second)
        expected_duration = 1.0 / 60.0
        assert abs(duration - expected_duration) < 0.001

    def test_update_usage_tracking_success(self, service):
        """Test usage tracking for successful requests."""
        initial_requests = service.usage_tracking["total_requests"]
        initial_minutes = service.usage_tracking["total_audio_minutes"]
        initial_cost = service.usage_tracking["monthly_cost_cents"]

        service._update_usage_tracking(2.5, True)  # 2.5 minutes success

        assert service.usage_tracking["total_requests"] == initial_requests + 1
        assert service.usage_tracking["total_audio_minutes"] == initial_minutes + 2.5
        assert (
            service.usage_tracking["monthly_cost_cents"] == initial_cost + 150
        )  # 2.5 * 0.6 * 100

    def test_update_usage_tracking_failure(self, service):
        """Test usage tracking for failed requests."""
        initial_requests = service.usage_tracking["total_requests"]
        initial_failed = service.usage_tracking["failed_requests"]
        initial_minutes = service.usage_tracking["total_audio_minutes"]

        service._update_usage_tracking(2.0, False)  # Failed request

        assert service.usage_tracking["total_requests"] == initial_requests + 1
        assert service.usage_tracking["failed_requests"] == initial_failed + 1
        assert (
            service.usage_tracking["total_audio_minutes"] == initial_minutes
        )  # No change for failures

    @pytest.mark.asyncio
    async def test_convert_audio_format_same_format(self, service):
        """Test audio format conversion for same format."""
        audio_data = b"test_audio_data"

        result = await service.convert_audio_format(audio_data, "wav", "wav")

        assert result == audio_data

    @pytest.mark.asyncio
    async def test_convert_audio_format_different_format(self, service):
        """Test audio format conversion for different formats (not implemented)."""
        audio_data = b"test_audio_data"

        result = await service.convert_audio_format(audio_data, "mp3", "wav")

        # Should return original data with warning log
        assert result == audio_data

    @pytest.mark.asyncio
    async def test_process_streaming_audio(self, service, mock_openai_response):
        """Test streaming audio processing."""
        # Setup audio stream queue
        audio_stream = asyncio.Queue()

        # Add some audio chunks
        chunk1 = b"0" * 48000  # 3 seconds worth of data
        chunk2 = b"0" * 16000  # 1 second worth of data
        await audio_stream.put(chunk1)
        await audio_stream.put(chunk2)
        await audio_stream.put(None)  # End of stream signal

        with patch.object(
            service, "transcribe_audio", new_callable=AsyncMock
        ) as mock_transcribe:
            mock_transcribe.return_value = {
                "success": True,
                "text": "Test transcription",
                "confidence": 0.9,
            }

            result_queue = await service.process_streaming_audio(
                audio_stream=audio_stream, call_id="test_call", chunk_duration=3.0
            )

            # Should have processed at least one chunk
            assert not result_queue.empty()
            result = await result_queue.get()
            assert result["success"] is True
            assert result["text"] == "Test transcription"

    @pytest.mark.asyncio
    async def test_retry_transcription_success_first_attempt(
        self, service, mock_openai_response
    ):
        """Test retry transcription succeeding on first attempt."""
        audio_data = b"test_audio"

        with patch.object(
            service, "transcribe_audio", new_callable=AsyncMock
        ) as mock_transcribe:
            mock_transcribe.return_value = {
                "success": True,
                "text": "Success on first try",
            }

            result = await service.retry_transcription(audio_data, max_retries=3)

            assert result["success"] is True
            assert result["text"] == "Success on first try"
            assert mock_transcribe.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_transcription_success_after_retries(self, service):
        """Test retry transcription succeeding after initial failures."""
        audio_data = b"test_audio"

        with patch.object(
            service, "transcribe_audio", new_callable=AsyncMock
        ) as mock_transcribe:
            # First two calls fail, third succeeds
            mock_transcribe.side_effect = [
                {"success": False, "error": "Timeout"},
                {"success": False, "error": "Rate limit"},
                {"success": True, "text": "Success after retries"},
            ]

            result = await service.retry_transcription(audio_data, max_retries=3)

            assert result["success"] is True
            assert result["text"] == "Success after retries"
            assert mock_transcribe.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_transcription_all_failures(self, service):
        """Test retry transcription failing all attempts."""
        audio_data = b"test_audio"

        with patch.object(
            service, "transcribe_audio", new_callable=AsyncMock
        ) as mock_transcribe:
            mock_transcribe.return_value = {
                "success": False,
                "error": "Persistent error",
            }

            result = await service.retry_transcription(audio_data, max_retries=2)

            assert result["success"] is False
            assert "Failed after 3 attempts" in result["error"]
            assert mock_transcribe.call_count == 3  # Initial + 2 retries

    def test_get_usage_stats(self, service):
        """Test getting usage statistics."""
        # Set some test values
        service.usage_tracking = {
            "total_requests": 100,
            "total_audio_minutes": 50.5,
            "failed_requests": 5,
            "monthly_cost_cents": 2525,  # $25.25
        }

        stats = service.get_usage_stats()

        assert stats["total_requests"] == 100
        assert stats["total_audio_minutes"] == 50.5
        assert stats["failed_requests"] == 5
        assert stats["monthly_cost_cents"] == 2525
        assert stats["cost_dollars"] == 25.25
        assert stats["success_rate"] == 95.0  # (100-5)/100 * 100
        assert "timestamp" in stats

    def test_reset_monthly_usage(self, service):
        """Test resetting monthly usage tracking."""
        # Set some values
        service.usage_tracking = {
            "total_requests": 100,
            "total_audio_minutes": 50.0,
            "failed_requests": 5,
            "monthly_cost_cents": 2500,
        }

        service.reset_monthly_usage()

        # All values should be reset to 0
        assert service.usage_tracking["total_requests"] == 0
        assert service.usage_tracking["total_audio_minutes"] == 0
        assert service.usage_tracking["failed_requests"] == 0
        assert service.usage_tracking["monthly_cost_cents"] == 0

    @pytest.mark.asyncio
    async def test_test_connection_success(self, service):
        """Test successful connection test."""
        with patch.object(
            service, "transcribe_audio", new_callable=AsyncMock
        ) as mock_transcribe:
            mock_transcribe.return_value = {"success": True, "text": "test"}

            result = await service.test_connection()

            assert result is True
            mock_transcribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, service):
        """Test failed connection test."""
        with patch.object(
            service, "transcribe_audio", new_callable=AsyncMock
        ) as mock_transcribe:
            mock_transcribe.return_value = {
                "success": False,
                "error": "Connection failed",
            }

            result = await service.test_connection()

            assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_no_client(self):
        """Test connection test with no client."""
        with patch("src.services.openai_integration.get_config", return_value=None):
            service = OpenAIIntegrationService()

        result = await service.test_connection()

        assert result is False

    def test_initialization_with_api_key(self):
        """Test service initialization with API key."""
        with patch(
            "src.services.openai_integration.get_config", return_value="test_key"
        ):
            with patch("src.services.openai_integration.OpenAI") as mock_openai_class:
                service = OpenAIIntegrationService()

                assert service.api_key == "test_key"
                mock_openai_class.assert_called_once_with(api_key="test_key")

    def test_initialization_without_api_key(self):
        """Test service initialization without API key."""
        with patch("src.services.openai_integration.get_config", return_value=None):
            service = OpenAIIntegrationService()

            assert service.api_key is None
            assert service.client is None

    @pytest.mark.asyncio
    async def test_process_streaming_audio_timeout(self, service):
        """Test streaming audio processing with timeout."""
        # Create empty queue (no audio data)
        audio_stream = asyncio.Queue()

        result_queue = await service.process_streaming_audio(
            audio_stream=audio_stream, call_id="test_call", chunk_duration=1.0
        )

        # Should handle timeout gracefully
        assert isinstance(result_queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_streaming_audio_error_handling(self, service):
        """Test error handling in streaming audio processing."""
        # Create queue with invalid data
        audio_stream = asyncio.Queue()
        await audio_stream.put("invalid_audio_data")  # String instead of bytes
        await audio_stream.put(None)

        with patch.object(
            service, "transcribe_audio", side_effect=Exception("Processing error")
        ):
            result_queue = await service.process_streaming_audio(
                audio_stream=audio_stream, call_id="test_call"
            )

            # Should return error result
            result = await result_queue.get()
            assert result["success"] is False
            assert "error" in result
