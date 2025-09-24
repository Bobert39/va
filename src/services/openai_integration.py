"""
OpenAI Integration Service

Handles OpenAI API integration for speech-to-text processing using Whisper,
including real-time audio processing, error handling, and cost tracking.
"""

import asyncio
import io
import logging
import tempfile
from datetime import datetime, timezone
from typing import Dict, Optional

from openai import OpenAI

from src.audit import audit_logger_instance
from src.config import get_config

logger = logging.getLogger(__name__)


class OpenAIIntegrationService:
    """
    Handles OpenAI API integration for speech-to-text processing.

    Features:
    - Whisper API integration for speech-to-text
    - Real-time audio processing
    - Audio format conversion
    - Error handling with retry logic
    - Cost tracking for API usage
    """

    def __init__(self):
        """Initialize OpenAI integration service."""
        self.client: Optional[OpenAI] = None
        self.api_key: Optional[str] = None
        self.usage_tracking: Dict[str, int] = {
            "total_requests": 0,
            "total_audio_minutes": 0,
            "failed_requests": 0,
            "monthly_cost_cents": 0,
        }
        self._initialize_client()

    def _initialize_client(self):
        """Initialize OpenAI client with API key from config."""
        try:
            self.api_key = get_config("api_keys.openai_api_key")

            if not self.api_key:
                logger.warning("OpenAI API key not configured")
                return

            self.client = OpenAI(api_key=self.api_key)
            logger.info("OpenAI client initialized successfully")

            audit_logger_instance.log_system_event(
                action="OPENAI_CLIENT_INITIALIZED", result="SUCCESS"
            )

        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            audit_logger_instance.log_system_event(
                action="OPENAI_CLIENT_INITIALIZATION",
                result="FAILURE",
                additional_data={"error": str(e)},
            )

    async def transcribe_audio(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: str = "en",
        call_id: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Transcribe audio using OpenAI Whisper API.

        Args:
            audio_data: Raw audio data in bytes
            audio_format: Audio format (wav, mp3, etc.)
            language: Language code for transcription
            call_id: Optional call ID for tracking

        Returns:
            Dictionary with transcription results and metadata
        """
        try:
            if not self.client:
                raise ValueError("OpenAI client not initialized")

            # Create temporary file for audio data
            with tempfile.NamedTemporaryFile(
                suffix=f".{audio_format}", delete=False
            ) as temp_file:
                temp_file.write(audio_data)
                temp_file.flush()

                # Calculate audio duration for cost tracking
                audio_duration = self._calculate_audio_duration(
                    audio_data, audio_format
                )

                # Transcribe audio
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=open(temp_file.name, "rb"),
                    language=language,
                    response_format="verbose_json",
                    temperature=0.2,
                )

                # Update usage tracking
                self._update_usage_tracking(audio_duration, True)

                # Log successful transcription
                audit_logger_instance.log_system_event(
                    action="AUDIO_TRANSCRIPTION",
                    result="SUCCESS",
                    additional_data={
                        "call_id": call_id,
                        "audio_duration": audio_duration,
                        "language": language,
                        "confidence": getattr(response, "confidence", None),
                    },
                )

                result = {
                    "text": response.text,
                    "language": getattr(response, "language", language),
                    "duration": audio_duration,
                    "confidence": getattr(response, "confidence", None),
                    "segments": getattr(response, "segments", []),
                    "success": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                logger.info(
                    f"Audio transcription successful: {len(response.text)} characters"
                )
                return result

        except Exception as e:
            self._update_usage_tracking(0, False)
            logger.error(f"Audio transcription failed: {e}")

            audit_logger_instance.log_system_event(
                action="AUDIO_TRANSCRIPTION",
                result="FAILURE",
                additional_data={"call_id": call_id, "error": str(e)},
            )

            return {
                "text": "",
                "error": str(e),
                "success": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _calculate_audio_duration(self, audio_data: bytes, audio_format: str) -> float:
        """
        Calculate audio duration in minutes.

        This is a simplified calculation - in production you'd use
        audio processing libraries like librosa or pydub.

        Args:
            audio_data: Raw audio data
            audio_format: Audio format

        Returns:
            Duration in minutes
        """
        # Simplified calculation assuming 16kHz, 16-bit mono audio
        # In production, use proper audio analysis
        bytes_per_second = 16000 * 2  # 16kHz * 2 bytes per sample
        duration_seconds = len(audio_data) / bytes_per_second
        return duration_seconds / 60.0

    def _update_usage_tracking(self, duration_minutes: float, success: bool):
        """Update API usage tracking for cost monitoring."""
        self.usage_tracking["total_requests"] += 1

        if success:
            self.usage_tracking["total_audio_minutes"] += duration_minutes
            # Whisper pricing: $0.006 per minute
            cost_cents = int(duration_minutes * 0.6)  # Convert to cents
            self.usage_tracking["monthly_cost_cents"] += cost_cents
        else:
            self.usage_tracking["failed_requests"] += 1

    async def convert_audio_format(
        self, audio_data: bytes, from_format: str, to_format: str = "wav"
    ) -> bytes:
        """
        Convert audio format for OpenAI compatibility.

        Args:
            audio_data: Input audio data
            from_format: Source audio format
            to_format: Target audio format

        Returns:
            Converted audio data
        """
        try:
            # For MVP, we'll assume audio is already in compatible format
            # In production, use pydub or similar for format conversion
            if from_format.lower() == to_format.lower():
                return audio_data

            logger.warning(
                f"Audio format conversion from {from_format} to {to_format} "
                "not implemented"
            )
            return audio_data

        except Exception as e:
            logger.error(f"Audio format conversion failed: {e}")
            return audio_data

    async def process_streaming_audio(
        self, audio_stream: asyncio.Queue, call_id: str, chunk_duration: float = 3.0
    ) -> asyncio.Queue:
        """
        Process streaming audio for real-time transcription.

        Args:
            audio_stream: Queue of audio chunks
            call_id: Call identifier
            chunk_duration: Duration of each chunk to process

        Returns:
            Queue of transcription results
        """
        transcription_queue = asyncio.Queue()

        try:
            audio_buffer = io.BytesIO()
            buffer_duration = 0.0

            while True:
                try:
                    # Get audio chunk with timeout
                    audio_chunk = await asyncio.wait_for(
                        audio_stream.get(), timeout=30.0
                    )

                    if audio_chunk is None:  # End of stream signal
                        break

                    # Add chunk to buffer
                    audio_buffer.write(audio_chunk)
                    chunk_duration_estimate = len(audio_chunk) / (16000 * 2) / 60.0
                    buffer_duration += chunk_duration_estimate

                    # Process buffer when it reaches target duration
                    if buffer_duration >= chunk_duration:
                        audio_data = audio_buffer.getvalue()

                        # Transcribe accumulated audio
                        result = await self.transcribe_audio(
                            audio_data=audio_data, call_id=call_id
                        )

                        await transcription_queue.put(result)

                        # Reset buffer
                        audio_buffer = io.BytesIO()
                        buffer_duration = 0.0

                except asyncio.TimeoutError:
                    # Process any remaining buffer on timeout
                    if buffer_duration > 0:
                        audio_data = audio_buffer.getvalue()
                        result = await self.transcribe_audio(
                            audio_data=audio_data, call_id=call_id
                        )
                        await transcription_queue.put(result)
                    break

        except Exception as e:
            logger.error(f"Streaming audio processing failed: {e}")
            await transcription_queue.put(
                {
                    "error": str(e),
                    "success": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        return transcription_queue

    async def retry_transcription(
        self, audio_data: bytes, max_retries: int = 3, call_id: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Retry transcription with exponential backoff.

        Args:
            audio_data: Audio data to transcribe
            max_retries: Maximum number of retry attempts
            call_id: Optional call ID for tracking

        Returns:
            Transcription result
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                result = await self.transcribe_audio(audio_data, call_id=call_id)

                if result["success"]:
                    if attempt > 0:
                        logger.info(f"Transcription succeeded on attempt {attempt + 1}")
                    return result

                last_error = result.get("error", "Unknown error")

            except Exception as e:
                last_error = str(e)

            if attempt < max_retries:
                # Exponential backoff: 1s, 2s, 4s
                delay = 2**attempt
                logger.warning(
                    f"Transcription attempt {attempt + 1} failed, retrying in {delay}s"
                )
                await asyncio.sleep(delay)

        logger.error(f"Transcription failed after {max_retries + 1} attempts")
        return {
            "text": "",
            "error": f"Failed after {max_retries + 1} attempts: {last_error}",
            "success": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_usage_stats(self) -> Dict[str, any]:
        """
        Get current API usage statistics.

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
            "total_audio_minutes": 0,
            "failed_requests": 0,
            "monthly_cost_cents": 0,
        }

        audit_logger_instance.log_system_event(
            action="MONTHLY_USAGE_RESET", result="SUCCESS"
        )

    async def test_connection(self) -> bool:
        """
        Test OpenAI API connection.

        Returns:
            True if connection successful
        """
        try:
            if not self.client:
                return False

            # Test with a minimal audio file (1 second of silence)
            test_audio = b"\x00" * 32000  # 1 second of 16kHz mono silence

            result = await self.transcribe_audio(
                audio_data=test_audio, call_id="connection_test"
            )

            success = result.get("success", False)

            audit_logger_instance.log_system_event(
                action="OPENAI_CONNECTION_TEST",
                result="SUCCESS" if success else "FAILURE",
                additional_data={"error": result.get("error")},
            )

            logger.info(
                f"OpenAI connection test: {'successful' if success else 'failed'}"
            )
            return success

        except Exception as e:
            logger.error(f"OpenAI connection test failed: {e}")
            audit_logger_instance.log_system_event(
                action="OPENAI_CONNECTION_TEST",
                result="FAILURE",
                additional_data={"error": str(e)},
            )
            return False


# Global service instance
openai_service = OpenAIIntegrationService()
