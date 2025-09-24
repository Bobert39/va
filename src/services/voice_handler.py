"""
Voice Call Handler Service

Main component for voice call processing that orchestrates Twilio integration,
OpenAI speech-to-text, conversation management, and timeout handling.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from src.audit import SecurityAndAuditService, audit_logger_instance
from src.services.appointment_creator import AppointmentCreator
from src.services.confirmation_generator import ConfirmationGenerator
from src.services.conversation_manager import conversation_manager
from src.services.emr import EMROAuthClient
from src.services.openai_integration import openai_service
from src.services.tts_service import tts_service
from src.services.twilio_integration import twilio_service

logger = logging.getLogger(__name__)


class VoiceCallHandler:
    """
    Main voice call processing component.

    Features:
    - Call session management in active_calls dictionary
    - Conversation timeout logic (30-second silence detection)
    - Audio feedback generation for error states
    - Graceful error handling with human handoff option
    - Integration with Twilio and OpenAI services
    """

    def __init__(self):
        """Initialize voice call handler."""
        self.active_calls: Dict[str, Dict] = {}
        self.timeout_seconds = 30
        self.max_call_duration_minutes = 10

        # Initialize appointment services
        self.emr_client = EMROAuthClient()
        self.audit_service = SecurityAndAuditService()
        self.appointment_creator = AppointmentCreator(
            emr_client=self.emr_client, audit_service=self.audit_service
        )
        self.confirmation_generator = ConfirmationGenerator()

    def _hash_phone_number(self, phone_number: str) -> str:
        """Hash phone number for privacy-compliant logging."""
        return hashlib.sha256(phone_number.encode()).hexdigest()[:16]

    async def start_call_session(
        self, call_sid: str, from_number: str, to_number: str
    ) -> Dict[str, any]:
        """
        Start a new voice call session.

        Args:
            call_sid: Twilio call SID
            from_number: Caller's phone number
            to_number: Called number

        Returns:
            Session details dictionary
        """
        try:
            phone_hash = self._hash_phone_number(from_number)
            start_time = datetime.now(timezone.utc)

            # Create session entry
            session = {
                "call_sid": call_sid,
                "start_time": start_time,
                "phone_hash": phone_hash,
                "from_number_hash": self._hash_phone_number(from_number),
                "to_number_hash": self._hash_phone_number(to_number),
                "status": "active",
                "last_activity": start_time,
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

            self.active_calls[call_sid] = session

            # Log session start
            audit_logger_instance.log_voice_call(
                action="CALL_SESSION_STARTED",
                call_id=call_sid,
                phone_hash=phone_hash,
                result="SUCCESS",
            )

            logger.info(f"Call session started: {call_sid}")

            return {
                "success": True,
                "session_id": call_sid,
                "message": "Call session initialized successfully",
            }

        except Exception as e:
            logger.error(f"Failed to start call session: {e}")
            audit_logger_instance.log_voice_call(
                action="CALL_SESSION_START",
                call_id=call_sid,
                phone_hash=self._hash_phone_number(from_number),
                result="FAILURE",
            )

            return {
                "success": False,
                "error": str(e),
                "message": "Failed to initialize call session",
            }

    async def process_audio_chunk(
        self, call_sid: str, audio_data: bytes, audio_format: str = "wav"
    ) -> Dict[str, any]:
        """
        Process incoming audio chunk for transcription.

        Args:
            call_sid: Call session ID
            audio_data: Raw audio data
            audio_format: Audio format

        Returns:
            Processing result dictionary
        """
        try:
            if call_sid not in self.active_calls:
                raise ValueError(f"No active session found for call {call_sid}")

            session = self.active_calls[call_sid]

            # Update last activity timestamp
            session["last_activity"] = datetime.now(timezone.utc)

            # Transcribe audio using OpenAI
            transcription_result = await openai_service.retry_transcription(
                audio_data=audio_data, call_id=call_sid
            )

            # Store transcription result
            if transcription_result["success"]:
                session["transcription_results"].append(transcription_result)

                # Log successful transcription
                audit_logger_instance.log_voice_call(
                    action="AUDIO_TRANSCRIBED",
                    call_id=call_sid,
                    phone_hash=session["phone_hash"],
                    result="SUCCESS",
                    additional_data={
                        "text_length": len(transcription_result["text"]),
                        "confidence": transcription_result.get("confidence"),
                    },
                )

                logger.info(
                    f"Audio transcribed for call {call_sid}: {transcription_result['text'][:100]}"
                )

                # Determine intent and process if appointment request
                intent = self._determine_intent(transcription_result["text"])
                session["conversation_state"] = intent

                # Process based on intent
                if intent == "appointment_booking":
                    # Process appointment request
                    appointment_result = await self.process_appointment_request(
                        call_sid, transcription_result["text"]
                    )

                    return {
                        "success": appointment_result["success"],
                        "transcription": transcription_result["text"],
                        "confidence": transcription_result.get("confidence"),
                        "next_action": "appointment_created"
                        if appointment_result["success"]
                        else "human_handoff",
                        "appointment_id": appointment_result.get("appointment_id"),
                        "confirmation_number": appointment_result.get(
                            "confirmation_number"
                        ),
                        "confirmation_audio": appointment_result.get(
                            "spoken_confirmation"
                        ),
                        "feedback": appointment_result.get("message"),
                    }
                else:
                    return {
                        "success": True,
                        "transcription": transcription_result["text"],
                        "confidence": transcription_result.get("confidence"),
                        "next_action": self._determine_next_action(
                            call_sid, transcription_result["text"]
                        ),
                    }

            else:
                session["error_count"] += 1
                logger.warning(
                    f"Transcription failed for call {call_sid}: {transcription_result.get('error')}"
                )

                return {
                    "success": False,
                    "error": transcription_result.get("error"),
                    "next_action": "request_repeat"
                    if session["error_count"] < 3
                    else "human_handoff",
                }

        except Exception as e:
            logger.error(f"Audio processing failed for call {call_sid}: {e}")
            return {"success": False, "error": str(e), "next_action": "error_feedback"}

    def _determine_next_action(self, call_sid: str, transcription_text: str) -> str:
        """
        Determine next action based on transcription content.

        Args:
            call_sid: Call session ID
            transcription_text: Transcribed text

        Returns:
            Next action to take
        """
        if not transcription_text.strip():
            return "silence_detected"

        # Simple keyword detection for MVP
        appointment_keywords = [
            "appointment",
            "schedule",
            "book",
            "visit",
            "doctor",
            "see",
        ]
        emergency_keywords = ["emergency", "urgent", "pain", "help", "emergency room"]

        text_lower = transcription_text.lower()

        if any(keyword in text_lower for keyword in emergency_keywords):
            return "emergency_transfer"
        elif any(keyword in text_lower for keyword in appointment_keywords):
            return "appointment_booking"
        else:
            return "clarification_needed"

    async def handle_silence_timeout(self, call_sid: str) -> Dict[str, any]:
        """
        Handle conversation timeout after 30 seconds of silence.

        Args:
            call_sid: Call session ID

        Returns:
            Timeout handling result
        """
        try:
            if call_sid not in self.active_calls:
                return {"success": False, "error": "Session not found"}

            session = self.active_calls[call_sid]
            session["timeout_warnings"] += 1

            # Log timeout event
            audit_logger_instance.log_voice_call(
                action="SILENCE_TIMEOUT",
                call_id=call_sid,
                phone_hash=session["phone_hash"],
                result="SUCCESS",
                additional_data={"warning_count": session["timeout_warnings"]},
            )

            if session["timeout_warnings"] >= 3:
                # End call after 3 timeout warnings
                return await self.end_call_session(call_sid, "timeout_exceeded")
            else:
                # Provide timeout warning
                return {
                    "success": True,
                    "action": "timeout_warning",
                    "message": "I didn't hear anything. Please state your appointment request.",
                    "warnings_remaining": 3 - session["timeout_warnings"],
                }

        except Exception as e:
            logger.error(f"Silence timeout handling failed: {e}")
            return {"success": False, "error": str(e)}

    async def create_appointment_from_voice(
        self, call_sid: str, appointment_data: Dict[str, any]
    ) -> Dict[str, any]:
        """
        Create appointment from voice call data.

        Args:
            call_sid: Call session ID
            appointment_data: Parsed appointment data

        Returns:
            Appointment creation result
        """
        try:
            if call_sid not in self.active_calls:
                raise ValueError(f"No active session found for call {call_sid}")

            session = self.active_calls[call_sid]

            # Create appointment with retry logic
            result = await self.appointment_creator.create_appointment_with_retry(
                appointment_data=appointment_data, session_id=call_sid
            )

            if result["status"] == "created":
                # Generate confirmation number
                confirmation = self.confirmation_generator.generate_confirmation_number(
                    appointment_id=result["emr_appointment_id"],
                    patient_id=appointment_data["patient_id"],
                    provider_id=appointment_data["provider_id"],
                    appointment_time=appointment_data["start_time"],
                )

                # Store in session
                session["appointment_data"] = appointment_data
                session["confirmation_number"] = confirmation
                self.confirmation_generator.store_session_confirmation(
                    call_sid, confirmation, appointment_data
                )

                # Log successful creation
                await self.audit_service.log_appointment_creation(
                    appointment_id=result["emr_appointment_id"],
                    patient_id=appointment_data["patient_id"],
                    provider_id=appointment_data["provider_id"],
                    appointment_time=appointment_data["start_time"].isoformat(),
                    session_id=call_sid,
                    confirmation_number=confirmation,
                    result="SUCCESS",
                )

                # Format confirmation for voice
                spoken_confirmation = self.confirmation_generator.format_for_voice(
                    confirmation
                )

                return {
                    "success": True,
                    "appointment_id": result["emr_appointment_id"],
                    "confirmation_number": confirmation,
                    "spoken_confirmation": spoken_confirmation,
                    "message": f"Your appointment has been scheduled. Your confirmation number is {spoken_confirmation}",
                    "status": "created",
                }

            elif result["status"] == "pending_retry":
                # Appointment pending retry
                session["appointment_data"] = appointment_data

                return {
                    "success": False,
                    "status": "pending_retry",
                    "message": "Your appointment request has been received and will be processed shortly. Please call back to confirm.",
                    "retry_after": result.get("retry_after"),
                }

            else:
                # Creation failed
                error_msg = result.get("error", "Unknown error")

                await self.audit_service.log_appointment_failure(
                    patient_id=appointment_data["patient_id"],
                    provider_id=appointment_data["provider_id"],
                    error=error_msg,
                    retry_count=result.get("retry_count", 0),
                    session_id=call_sid,
                )

                return {
                    "success": False,
                    "status": "failed",
                    "error": error_msg,
                    "message": "I apologize, but I wasn't able to schedule your appointment. Let me connect you with our staff.",
                    "action": "human_handoff",
                }

        except Exception as e:
            logger.error(f"Appointment creation from voice failed: {e}")

            self.audit_service.log_appointment_event(
                event_type="appointment_creation_error",
                session_id=call_sid,
                details={"error": str(e)},
                result="ERROR",
            )

            return {
                "success": False,
                "error": str(e),
                "message": "A technical error occurred. Let me connect you with our staff.",
                "action": "human_handoff",
            }

    async def process_appointment_request(
        self, call_sid: str, transcribed_text: str
    ) -> Dict[str, any]:
        """
        Process appointment request from transcribed text.

        Args:
            call_sid: Call session ID
            transcribed_text: Transcribed appointment request

        Returns:
            Processing result with appointment creation status
        """
        try:
            if call_sid not in self.active_calls:
                raise ValueError(f"No active session found for call {call_sid}")

            session = self.active_calls[call_sid]

            # Parse appointment request (this would integrate with NLP processor)
            # For now, using placeholder data
            appointment_data = {
                "patient_id": "placeholder_patient_id",
                "provider_id": "placeholder_provider_id",
                "start_time": datetime.now(timezone.utc),
                "duration_minutes": 30,
                "appointment_type": "routine",
                "reason": transcribed_text,
                "notes": f"Voice appointment request: {transcribed_text}",
            }

            # Create appointment
            result = await self.create_appointment_from_voice(
                call_sid, appointment_data
            )

            # Update conversation state
            if result["success"]:
                session["conversation_state"] = "appointment_confirmed"
            else:
                session["conversation_state"] = "appointment_failed"

            return result

        except Exception as e:
            logger.error(f"Failed to process appointment request: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to process your appointment request",
            }

    async def generate_audio_feedback(
        self, call_sid: str, feedback_type: str, context: Optional[Dict] = None
    ) -> Dict[str, any]:
        """
        Generate audio feedback for different scenarios.

        Args:
            call_sid: Call session ID
            feedback_type: Type of feedback needed
            context: Additional context for feedback

        Returns:
            Audio feedback details
        """
        try:
            feedback_messages = {
                "greeting": "Hello! Please state your appointment request after the tone.",
                "timeout_warning": "I didn't hear anything. Please state your appointment request.",
                "clarification": "I didn't understand. Could you please repeat your appointment request?",
                "error": "Sorry, we're experiencing technical difficulties. Please try again.",
                "human_handoff": "Let me connect you with one of our staff members who can help you.",
                "emergency": "This sounds like an emergency. Please hang up and call 911 immediately.",
                "goodbye": "Thank you for calling. Have a great day!",
                "appointment_confirmed": "Your appointment has been successfully scheduled.",
                "appointment_pending": "Your appointment request has been received and will be processed shortly.",
                "appointment_failed": "I apologize, but I wasn't able to schedule your appointment. Let me connect you with our staff.",
            }

            message = feedback_messages.get(feedback_type, feedback_messages["error"])

            # Log feedback generation
            audit_logger_instance.log_voice_call(
                action="AUDIO_FEEDBACK_GENERATED",
                call_id=call_sid,
                phone_hash=self.active_calls.get(call_sid, {}).get(
                    "phone_hash", "unknown"
                ),
                result="SUCCESS",
                additional_data={"feedback_type": feedback_type},
            )

            return {
                "success": True,
                "message": message,
                "feedback_type": feedback_type,
                "twiml": f"<Response><Say>{message}</Say></Response>",
            }

        except Exception as e:
            logger.error(f"Audio feedback generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Technical error occurred",
            }

    async def end_call_session(
        self, call_sid: str, reason: str = "completed"
    ) -> Dict[str, any]:
        """
        End an active call session.

        Args:
            call_sid: Call session ID
            reason: Reason for ending call

        Returns:
            Session end result
        """
        try:
            if call_sid not in self.active_calls:
                return {"success": False, "error": "Session not found"}

            session = self.active_calls[call_sid]
            end_time = datetime.now(timezone.utc)
            duration = (end_time - session["start_time"]).total_seconds()

            # Log call end
            audit_logger_instance.log_voice_call(
                action="CALL_SESSION_ENDED",
                call_id=call_sid,
                phone_hash=session["phone_hash"],
                result="SUCCESS",
                duration=int(duration),
                additional_data={
                    "reason": reason,
                    "transcription_count": len(session["transcription_results"]),
                    "error_count": session["error_count"],
                    "timeout_warnings": session["timeout_warnings"],
                },
            )

            # End Twilio call
            twilio_service.end_call(call_sid, reason)

            # Clean up session
            del self.active_calls[call_sid]

            logger.info(
                f"Call session ended: {call_sid}, duration: {duration}s, reason: {reason}"
            )

            return {
                "success": True,
                "duration_seconds": duration,
                "reason": reason,
                "session_summary": {
                    "transcription_count": len(session["transcription_results"]),
                    "error_count": session["error_count"],
                    "timeout_warnings": session["timeout_warnings"],
                },
            }

        except Exception as e:
            logger.error(f"Failed to end call session: {e}")
            return {"success": False, "error": str(e)}

    async def monitor_active_calls(self):
        """Monitor active calls for timeouts and cleanup."""
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                calls_to_timeout = []

                for call_sid, session in self.active_calls.items():
                    # Check for silence timeout
                    silence_duration = (
                        current_time - session["last_activity"]
                    ).total_seconds()

                    if silence_duration >= self.timeout_seconds:
                        calls_to_timeout.append(call_sid)

                    # Check for maximum call duration
                    total_duration = (
                        current_time - session["start_time"]
                    ).total_seconds()
                    if total_duration >= (self.max_call_duration_minutes * 60):
                        calls_to_timeout.append(call_sid)

                # Handle timeouts
                for call_sid in calls_to_timeout:
                    await self.handle_silence_timeout(call_sid)

                # Sleep before next check
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Call monitoring error: {e}")
                await asyncio.sleep(10)

    def get_session_details(self, call_sid: str) -> Optional[Dict]:
        """Get details for a specific call session."""
        return self.active_calls.get(call_sid)

    def get_active_sessions_count(self) -> int:
        """Get count of currently active sessions."""
        return len(self.active_calls)

    def get_all_sessions_summary(self) -> Dict[str, any]:
        """Get summary of all active sessions."""
        return {
            "active_count": len(self.active_calls),
            "sessions": [
                {
                    "call_sid": call_sid,
                    "start_time": session["start_time"].isoformat(),
                    "status": session["status"],
                    "duration": (
                        datetime.now(timezone.utc) - session["start_time"]
                    ).total_seconds(),
                    "transcription_count": len(session["transcription_results"]),
                }
                for call_sid, session in self.active_calls.items()
            ],
        }

    async def start_tts_confirmation_flow(
        self, call_sid: str, appointment_details: Dict[str, any]
    ) -> Dict[str, any]:
        """
        Start TTS confirmation flow for appointment details.

        Args:
            call_sid: Call session ID
            appointment_details: Appointment information to confirm

        Returns:
            TTS confirmation flow result
        """
        try:
            if call_sid not in self.active_calls:
                raise ValueError(f"No active session found for call {call_sid}")

            session = self.active_calls[call_sid]

            # Start conversation session if not exists
            if not session.get("conversation_session_id"):
                session_id = await conversation_manager.start_session(
                    call_id=call_sid, phone_number_hash=session["phone_hash"]
                )
                session["conversation_session_id"] = session_id

            # Start confirmation flow in conversation manager
            confirmation_flow = await conversation_manager.start_confirmation_flow(
                session_id=session["conversation_session_id"],
                appointment_details=appointment_details,
            )

            # Generate TTS audio for confirmation
            tts_result = await tts_service.generate_confirmation_audio(
                appointment_details=appointment_details, call_id=call_sid
            )

            if tts_result["success"]:
                session["tts_confirmation_state"] = "pending"
                session[
                    "confirmation_audio_url"
                ] = None  # For HIPAA compliance, don't store
                session["appointment_data"] = appointment_details

                # Log TTS confirmation start
                audit_logger_instance.log_voice_call(
                    action="TTS_CONFIRMATION_STARTED",
                    call_id=call_sid,
                    phone_hash=session["phone_hash"],
                    result="SUCCESS",
                    additional_data={
                        "appointment_id": appointment_details.get("appointment_id"),
                        "exchange_count": confirmation_flow["exchange_count"],
                    },
                )

                return {
                    "success": True,
                    "confirmation_audio": tts_result["audio_data"],
                    "confirmation_text": tts_result["text"],
                    "duration_estimate": tts_result["duration_estimate"],
                    "exchange_count": confirmation_flow["exchange_count"],
                    "remaining_exchanges": confirmation_flow["remaining_exchanges"],
                    "next_action": "play_confirmation_audio",
                    "twiml": f"<Response><Play>{tts_result.get('audio_url', '')}</Play><Pause length='2'/><Record action='/voice/confirmation-response' maxLength='10' timeout='5'/></Response>",
                }
            else:
                # TTS generation failed, fall back to text-based confirmation
                session["tts_confirmation_state"] = "fallback"

                fallback_message = (
                    f"I have scheduled your appointment for {appointment_details.get('date', 'your requested date')} "
                    f"at {appointment_details.get('time', 'your requested time')} "
                    f"with {appointment_details.get('provider_name', 'your provider')}. "
                    "Please say 'yes' to confirm or 'no' if you need to make changes."
                )

                return {
                    "success": True,
                    "confirmation_text": fallback_message,
                    "fallback_mode": True,
                    "next_action": "play_fallback_confirmation",
                    "twiml": f"<Response><Say>{fallback_message}</Say><Record action='/voice/confirmation-response' maxLength='10' timeout='5'/></Response>",
                }

        except Exception as e:
            logger.error(f"TTS confirmation flow failed: {e}")
            audit_logger_instance.log_voice_call(
                action="TTS_CONFIRMATION_START",
                call_id=call_sid,
                phone_hash=session.get("phone_hash", "unknown"),
                result="FAILURE",
                additional_data={"error": str(e)},
            )

            return {
                "success": False,
                "error": str(e),
                "next_action": "human_handoff",
                "message": "I apologize, but I'm having trouble confirming your appointment. Let me connect you with our staff.",
            }

    async def process_tts_confirmation_response(
        self, call_sid: str, user_response: str
    ) -> Dict[str, any]:
        """
        Process patient response to TTS appointment confirmation.

        Args:
            call_sid: Call session ID
            user_response: Patient's voice response

        Returns:
            Response processing result
        """
        try:
            if call_sid not in self.active_calls:
                raise ValueError(f"No active session found for call {call_sid}")

            session = self.active_calls[call_sid]

            if session["tts_confirmation_state"] not in ["pending", "fallback"]:
                raise ValueError(f"Call {call_sid} not in confirmation state")

            # Process response through conversation manager
            response_result = await conversation_manager.process_confirmation_response(
                session_id=session["conversation_session_id"],
                user_response=user_response,
            )

            # Update session state
            session["tts_confirmation_state"] = response_result["confirmation_state"]

            # Determine next action based on response
            if response_result["next_action"] == "complete_appointment":
                # Appointment confirmed - finalize it
                session["conversation_state"] = "appointment_confirmed"

                # Generate completion audio
                completion_audio = await tts_service.create_practice_greeting_audio(
                    practice_name=None, call_id=call_sid  # Will use config default
                )

                if completion_audio["success"]:
                    completion_message = "Thank you for confirming your appointment. We look forward to seeing you. Have a great day!"
                else:
                    completion_message = "Thank you for confirming your appointment. We look forward to seeing you. Have a great day!"

                audit_logger_instance.log_voice_call(
                    action="TTS_CONFIRMATION_COMPLETED",
                    call_id=call_sid,
                    phone_hash=session["phone_hash"],
                    result="SUCCESS",
                    additional_data={
                        "appointment_id": session["appointment_data"].get(
                            "appointment_id"
                        ),
                        "final_state": "confirmed",
                    },
                )

                return {
                    "success": True,
                    "confirmation_state": "confirmed",
                    "next_action": "complete_call",
                    "message": completion_message,
                    "completion_audio": completion_audio.get("audio_data"),
                    "twiml": f"<Response><Say>{completion_message}</Say><Hangup/></Response>",
                }

            elif response_result["next_action"] == "cancel_appointment":
                # Patient declined appointment
                session["conversation_state"] = "appointment_cancelled"

                cancellation_message = "I understand you'd like to cancel. Your appointment request has been cancelled. Is there anything else I can help you with?"

                audit_logger_instance.log_voice_call(
                    action="TTS_CONFIRMATION_CANCELLED",
                    call_id=call_sid,
                    phone_hash=session["phone_hash"],
                    result="SUCCESS",
                    additional_data={
                        "appointment_id": session["appointment_data"].get(
                            "appointment_id"
                        ),
                        "final_state": "cancelled",
                    },
                )

                return {
                    "success": True,
                    "confirmation_state": "declined",
                    "next_action": "handle_cancellation",
                    "message": cancellation_message,
                    "twiml": f"<Response><Say>{cancellation_message}</Say><Record action='/voice/additional-request' maxLength='10' timeout='5'/></Response>",
                }

            elif response_result["next_action"] == "request_changes":
                # Patient wants to make changes
                session["conversation_state"] = "appointment_changes_requested"

                changes_message = "I understand you'd like to make changes. Please tell me what you'd like to change about your appointment."

                return {
                    "success": True,
                    "confirmation_state": "needs_changes",
                    "next_action": "gather_changes",
                    "message": changes_message,
                    "twiml": f"<Response><Say>{changes_message}</Say><Record action='/voice/appointment-changes' maxLength='30' timeout='10'/></Response>",
                }

            elif response_result["next_action"] == "request_clarification":
                # Unclear response, ask for clarification
                exchange_limit = conversation_manager.check_exchange_limit(
                    session["conversation_session_id"]
                )

                if exchange_limit["should_complete"]:
                    # Exceeded exchange limit, hand off to human
                    return await self._handle_exchange_limit_exceeded(call_sid)

                clarification_message = "I didn't quite understand. Please say 'yes' to confirm your appointment or 'no' if you need to make changes."

                return {
                    "success": True,
                    "confirmation_state": "pending",
                    "next_action": "request_clarification",
                    "message": clarification_message,
                    "remaining_exchanges": exchange_limit["remaining_exchanges"],
                    "twiml": f"<Response><Say>{clarification_message}</Say><Record action='/voice/confirmation-response' maxLength='10' timeout='5'/></Response>",
                }

            elif response_result["next_action"] == "human_handoff":
                # Hand off to human staff
                return await self._handle_exchange_limit_exceeded(call_sid)

            else:
                # Unexpected state
                raise ValueError(
                    f"Unexpected next action: {response_result['next_action']}"
                )

        except Exception as e:
            logger.error(f"TTS confirmation response processing failed: {e}")
            audit_logger_instance.log_voice_call(
                action="TTS_CONFIRMATION_RESPONSE",
                call_id=call_sid,
                phone_hash=session.get("phone_hash", "unknown"),
                result="FAILURE",
                additional_data={"error": str(e)},
            )

            return {
                "success": False,
                "error": str(e),
                "next_action": "human_handoff",
                "message": "I'm having trouble processing your response. Let me connect you with our staff.",
            }

    async def handle_tts_mid_conversation_hangup(self, call_sid: str) -> Dict[str, any]:
        """
        Handle graceful mid-conversation hangup during TTS confirmation flow.

        Args:
            call_sid: Call session ID

        Returns:
            Hangup handling result
        """
        try:
            if call_sid not in self.active_calls:
                return {"success": False, "error": "Session not found"}

            session = self.active_calls[call_sid]

            # Handle hangup in conversation manager if session exists
            hangup_result = {"status": "not_found"}
            if session.get("conversation_session_id"):
                hangup_result = (
                    await conversation_manager.handle_mid_conversation_hangup(
                        session_id=session["conversation_session_id"]
                    )
                )

            # Log the hangup event
            audit_logger_instance.log_voice_call(
                action="TTS_CONFIRMATION_HANGUP",
                call_id=call_sid,
                phone_hash=session.get("phone_hash", "unknown"),
                result="SUCCESS",
                additional_data={
                    "tts_confirmation_state": session.get("tts_confirmation_state"),
                    "had_partial_data": hangup_result.get(
                        "follow_up_recommended", False
                    ),
                },
            )

            # End the call session
            end_result = await self.end_call_session(
                call_sid, "mid_conversation_hangup"
            )

            return {
                "success": True,
                "call_ended": end_result["success"],
                "hangup_handled": hangup_result.get("status") == "hangup_handled",
                "follow_up_recommended": hangup_result.get(
                    "follow_up_recommended", False
                ),
                "partial_data": hangup_result.get("partial_data"),
            }

        except Exception as e:
            logger.error(f"TTS mid-conversation hangup handling failed: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_exchange_limit_exceeded(self, call_sid: str) -> Dict[str, any]:
        """
        Handle when exchange limit is exceeded per AC requirement.

        Args:
            call_sid: Call session ID

        Returns:
            Human handoff result
        """
        handoff_message = "I want to make sure you get the best service. Let me connect you with one of our staff members who can help complete your appointment."

        audit_logger_instance.log_voice_call(
            action="TTS_EXCHANGE_LIMIT_EXCEEDED",
            call_id=call_sid,
            phone_hash=self.active_calls.get(call_sid, {}).get("phone_hash", "unknown"),
            result="SUCCESS",
            additional_data={"reason": "exchange_limit_exceeded"},
        )

        return {
            "success": True,
            "confirmation_state": "exchange_limit_exceeded",
            "next_action": "human_handoff",
            "message": handoff_message,
            "twiml": f"<Response><Say>{handoff_message}</Say><Dial>+1234567890</Dial></Response>",  # Replace with actual staff number
        }


# Global service instance
voice_call_handler = VoiceCallHandler()
