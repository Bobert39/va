"""
Conversation Context Manager for multi-turn appointment scheduling conversations.
Manages conversation state, context retention, and clarification workflows.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.audit import audit_logger_instance
from src.services.datetime_parser import datetime_parser
from src.services.nlp_processor import (
    ConversationContext,
    ExtractionResult,
    nlp_processor,
)

logger = logging.getLogger(__name__)


@dataclass
class ConversationSession:
    """Active conversation session data."""

    session_id: str
    call_id: str
    phone_number_hash: str
    start_time: datetime
    last_activity: datetime
    context: ConversationContext
    status: str = "active"  # active, completed, expired, error
    max_turns: int = 5
    timeout_minutes: int = 10
    confirmation_state: str = (
        "none"  # none, pending, confirmed, declined, needs_changes
    )
    exchange_count: int = 0  # Track voice exchanges for confirmation flow
    max_exchanges: int = 5  # Maximum exchanges per AC requirement


class ConversationManager:
    """
    Manages multi-turn conversation sessions for appointment scheduling.

    Features:
    - Session lifecycle management
    - Context retention across turns
    - Intelligent clarification generation
    - Confirmation dialog workflows
    - Session timeout handling
    """

    def __init__(self):
        """Initialize conversation manager."""
        self.active_sessions: Dict[str, ConversationSession] = {}
        self.session_cleanup_interval = 300  # 5 minutes
        self.max_sessions = 100  # Memory management
        self._cleanup_task = None

    async def start_session(self, call_id: str, phone_number_hash: str) -> str:
        """
        Start a new conversation session.

        Args:
            call_id: Unique call identifier
            phone_number_hash: Hashed phone number for privacy

        Returns:
            Session ID for the new conversation
        """
        try:
            session_id = str(uuid.uuid4())
            now = datetime.utcnow()

            context = ConversationContext(call_id=call_id)

            session = ConversationSession(
                session_id=session_id,
                call_id=call_id,
                phone_number_hash=phone_number_hash,
                start_time=now,
                last_activity=now,
                context=context,
            )

            self.active_sessions[session_id] = session

            # Start cleanup task if not running
            if self._cleanup_task is None:
                self._cleanup_task = asyncio.create_task(self._session_cleanup_loop())

            audit_logger_instance.log_system_event(
                action="CONVERSATION_SESSION_STARTED",
                result="SUCCESS",
                additional_data={
                    "session_id": session_id,
                    "call_id": call_id,
                    "phone_hash": phone_number_hash,
                },
            )

            logger.info(f"Started conversation session {session_id} for call {call_id}")
            return session_id

        except Exception as e:
            logger.error(f"Failed to start conversation session: {e}")
            audit_logger_instance.log_system_event(
                action="CONVERSATION_SESSION_START",
                result="FAILURE",
                additional_data={"call_id": call_id, "error": str(e)},
            )
            raise

    async def process_turn(self, session_id: str, user_input: str) -> Dict[str, Any]:
        """
        Process a conversation turn with entity extraction and context management.

        Args:
            session_id: Active session identifier
            user_input: User's voice input text

        Returns:
            Dictionary with extracted entities, clarifications, and next actions
        """
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found or expired")

            if session.status != "active":
                raise ValueError(
                    f"Session {session_id} is not active (status: {session.status})"
                )

            # Update session activity
            session.last_activity = datetime.utcnow()
            session.context.turn_count += 1

            # Check turn limit
            if session.context.turn_count > session.max_turns:
                session.status = "expired"
                raise ValueError(
                    f"Session {session_id} exceeded maximum turns ({session.max_turns})"
                )

            # Extract entities with conversation context
            extraction_result = await nlp_processor.extract_entities(
                user_input, session.context
            )

            # Enhance with medical terminology
            extraction_result = nlp_processor.enhance_with_medical_terminology(
                extraction_result
            )

            # Merge entities into conversation context
            session.context.merge_entities(extraction_result)

            # Calculate updated confidence score
            overall_confidence = nlp_processor.calculate_confidence_score(
                session.context.accumulated_entities
            )
            session.context.accumulated_entities.overall_confidence = overall_confidence

            # Validate extraction and get clarifications if needed
            is_valid, validation_errors = nlp_processor.validate_extraction(
                session.context.accumulated_entities
            )
            clarification_questions = nlp_processor.get_clarification_questions(
                session.context.accumulated_entities
            )

            # Determine next action
            next_action = self._determine_next_action(
                session, extraction_result, clarification_questions
            )

            response = {
                "session_id": session_id,
                "turn_count": session.context.turn_count,
                "extracted_entities": extraction_result.to_dict(),
                "accumulated_entities": session.context.accumulated_entities.to_dict(),
                "overall_confidence": overall_confidence,
                "is_valid": is_valid,
                "validation_errors": validation_errors,
                "clarification_questions": clarification_questions,
                "next_action": next_action,
                "processing_time_ms": extraction_result.processing_time_ms,
            }

            # Log successful turn processing
            audit_logger_instance.log_system_event(
                action="CONVERSATION_TURN_PROCESSED",
                result="SUCCESS",
                additional_data={
                    "session_id": session_id,
                    "turn_count": session.context.turn_count,
                    "overall_confidence": overall_confidence,
                    "entities_found": len(
                        [
                            e
                            for e in [
                                session.context.accumulated_entities.patient_name,
                                session.context.accumulated_entities.appointment_datetime,
                                session.context.accumulated_entities.appointment_type,
                                session.context.accumulated_entities.reason,
                            ]
                            if e
                        ]
                    ),
                    "next_action": next_action,
                },
            )

            return response

        except Exception as e:
            logger.error(f"Failed to process conversation turn: {e}")

            if session_id in self.active_sessions:
                self.active_sessions[session_id].status = "error"

            audit_logger_instance.log_system_event(
                action="CONVERSATION_TURN_PROCESSING",
                result="FAILURE",
                additional_data={"session_id": session_id, "error": str(e)},
            )
            raise

    def _determine_next_action(
        self,
        session: ConversationSession,
        extraction_result: ExtractionResult,
        clarification_questions: List[str],
    ) -> str:
        """
        Determine the next action based on extraction results and session state.

        Args:
            session: Current conversation session
            extraction_result: Latest extraction result
            clarification_questions: List of clarification questions

        Returns:
            Next action string
        """
        accumulated = session.context.accumulated_entities

        # Check if we have minimum required information
        if accumulated.has_minimum_entities() and accumulated.overall_confidence >= 0.7:
            if len(clarification_questions) == 0:
                return "confirm_appointment"
            elif len(clarification_questions) <= 2:
                return "request_clarification"
            else:
                return "gather_information"

        # Check if we're making progress
        if accumulated.overall_confidence >= 0.5:
            if clarification_questions:
                return "request_clarification"
            else:
                return "gather_information"

        # Low confidence or missing critical information
        if session.context.turn_count >= 3:
            return "human_handoff"
        else:
            return "gather_information"

    async def generate_confirmation_dialog(self, session_id: str) -> Dict[str, Any]:
        """
        Generate confirmation dialog for appointment details.

        Args:
            session_id: Active session identifier

        Returns:
            Confirmation dialog content
        """
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            accumulated = session.context.accumulated_entities

            # Validate that we have sufficient information
            if not accumulated.has_minimum_entities():
                missing = accumulated.get_missing_entities()
                raise ValueError(
                    f"Insufficient information for confirmation. Missing: {missing}"
                )

            # Build confirmation text
            confirmation_parts = []

            if accumulated.patient_name:
                confirmation_parts.append(
                    f"Patient name: {accumulated.patient_name.value}"
                )

            if (
                accumulated.appointment_datetime
                and accumulated.appointment_datetime.value
            ):
                # Validate business hours
                is_valid_time, time_reason = datetime_parser.validate_business_hours(
                    accumulated.appointment_datetime.value
                )

                if not is_valid_time:
                    # Suggest alternatives
                    alternatives = datetime_parser.suggest_alternative_times(
                        accumulated.appointment_datetime.value
                    )
                    return {
                        "session_id": session_id,
                        "confirmation_type": "schedule_conflict",
                        "conflict_reason": time_reason,
                        "suggested_times": [
                            datetime_parser.format_datetime_human(alt)
                            for alt in alternatives
                        ],
                        "original_requested": datetime_parser.format_datetime_human(
                            accumulated.appointment_datetime.value
                        ),
                    }

                formatted_datetime = datetime_parser.format_datetime_human(
                    accumulated.appointment_datetime.value
                )
                confirmation_parts.append(f"Date and time: {formatted_datetime}")

            if accumulated.appointment_type:
                type_name = accumulated.appointment_type.value.value.replace(
                    "_", " "
                ).title()
                duration = accumulated.appointment_type.estimated_duration
                confirmation_parts.append(
                    f"Appointment type: {type_name} ({duration} minutes)"
                )

            if accumulated.reason:
                confirmation_parts.append(f"Reason: {accumulated.reason.value}")

            confirmation_text = (
                "Please confirm these appointment details:\\n"
                + "\\n".join(confirmation_parts)
            )

            return {
                "session_id": session_id,
                "confirmation_type": "appointment_details",
                "confirmation_text": confirmation_text,
                "appointment_details": accumulated.to_dict(),
                "confidence_score": accumulated.overall_confidence,
            }

        except Exception as e:
            logger.error(f"Failed to generate confirmation dialog: {e}")
            raise

    async def add_clarification(self, session_id: str, clarification: str):
        """
        Add clarification to conversation context.

        Args:
            session_id: Active session identifier
            clarification: Clarification question or response
        """
        session = self.active_sessions.get(session_id)
        if session:
            session.context.add_clarification(clarification)
            session.last_activity = datetime.utcnow()

    async def end_session(
        self, session_id: str, reason: str = "completed"
    ) -> Dict[str, Any]:
        """
        End a conversation session.

        Args:
            session_id: Session to end
            reason: Reason for ending session

        Returns:
            Session summary
        """
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            session.status = reason
            end_time = datetime.utcnow()
            duration = (end_time - session.start_time).total_seconds()

            summary = {
                "session_id": session_id,
                "call_id": session.call_id,
                "duration_seconds": duration,
                "turn_count": session.context.turn_count,
                "final_status": reason,
                "final_entities": session.context.accumulated_entities.to_dict(),
                "confidence_score": session.context.accumulated_entities.overall_confidence,
            }

            # Remove from active sessions
            del self.active_sessions[session_id]

            audit_logger_instance.log_system_event(
                action="CONVERSATION_SESSION_ENDED",
                result="SUCCESS",
                additional_data={
                    "session_id": session_id,
                    "reason": reason,
                    "duration_seconds": duration,
                    "turn_count": session.context.turn_count,
                },
            )

            logger.info(
                f"Ended conversation session {session_id} with reason: {reason}"
            )
            return summary

        except Exception as e:
            logger.error(f"Failed to end conversation session: {e}")
            raise

    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get current status of a conversation session.

        Args:
            session_id: Session identifier

        Returns:
            Session status information
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return {"session_id": session_id, "exists": False, "status": "not_found"}

        return {
            "session_id": session_id,
            "exists": True,
            "status": session.status,
            "turn_count": session.context.turn_count,
            "duration_seconds": (
                datetime.utcnow() - session.start_time
            ).total_seconds(),
            "last_activity_ago_seconds": (
                datetime.utcnow() - session.last_activity
            ).total_seconds(),
            "accumulated_entities": session.context.accumulated_entities.to_dict(),
            "confidence_score": session.context.accumulated_entities.overall_confidence,
        }

    async def _session_cleanup_loop(self):
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self.session_cleanup_interval)
                await self._cleanup_expired_sessions()
            except Exception as e:
                logger.error(f"Session cleanup loop error: {e}")

    async def _cleanup_expired_sessions(self):
        """Clean up expired and inactive sessions."""
        now = datetime.utcnow()
        expired_sessions = []

        for session_id, session in self.active_sessions.items():
            # Check for timeout
            time_since_activity = (now - session.last_activity).total_seconds()
            if time_since_activity > (session.timeout_minutes * 60):
                expired_sessions.append((session_id, "timeout"))
                continue

            # Check for error status
            if session.status in ["error", "expired"]:
                expired_sessions.append((session_id, session.status))

        # Remove expired sessions
        for session_id, reason in expired_sessions:
            try:
                await self.end_session(session_id, reason)
                logger.info(f"Cleaned up session {session_id} due to {reason}")
            except Exception as e:
                logger.error(f"Failed to cleanup session {session_id}: {e}")
                # Force remove from active sessions
                if session_id in self.active_sessions:
                    del self.active_sessions[session_id]

        # Memory management - remove oldest sessions if too many
        if len(self.active_sessions) > self.max_sessions:
            oldest_sessions = sorted(
                self.active_sessions.items(), key=lambda x: x[1].start_time
            )[: len(self.active_sessions) - self.max_sessions]

            for session_id, _ in oldest_sessions:
                try:
                    await self.end_session(session_id, "memory_limit")
                except Exception as e:
                    logger.error(f"Failed to cleanup old session {session_id}: {e}")

        if expired_sessions:
            audit_logger_instance.log_system_event(
                action="CONVERSATION_SESSIONS_CLEANUP",
                result="SUCCESS",
                additional_data={
                    "expired_count": len(expired_sessions),
                    "active_count": len(self.active_sessions),
                },
            )

    def get_active_sessions_count(self) -> int:
        """Get count of active sessions."""
        return len(self.active_sessions)

    def get_session_statistics(self) -> Dict[str, Any]:
        """Get conversation session statistics."""
        if not self.active_sessions:
            return {
                "active_sessions": 0,
                "average_turns": 0,
                "average_duration_seconds": 0,
            }

        total_turns = sum(s.context.turn_count for s in self.active_sessions.values())
        total_duration = sum(
            (datetime.utcnow() - s.start_time).total_seconds()
            for s in self.active_sessions.values()
        )

        return {
            "active_sessions": len(self.active_sessions),
            "average_turns": total_turns / len(self.active_sessions),
            "average_duration_seconds": total_duration / len(self.active_sessions),
            "session_statuses": {
                status: len(
                    [s for s in self.active_sessions.values() if s.status == status]
                )
                for status in set(s.status for s in self.active_sessions.values())
            },
        }

    async def start_confirmation_flow(
        self, session_id: str, appointment_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Start TTS confirmation flow for appointment details.

        Args:
            session_id: Active session identifier
            appointment_details: Appointment information to confirm

        Returns:
            Confirmation flow status and next steps
        """
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            # Check exchange count limit
            if session.exchange_count >= session.max_exchanges:
                session.status = "expired"
                raise ValueError(
                    f"Session {session_id} exceeded maximum exchanges ({session.max_exchanges})"
                )

            session.confirmation_state = "pending"
            session.exchange_count += 1
            session.last_activity = datetime.utcnow()

            # Store appointment details for confirmation
            session.context.appointment_details = appointment_details

            audit_logger_instance.log_system_event(
                action="TTS_CONFIRMATION_FLOW_STARTED",
                result="SUCCESS",
                additional_data={
                    "session_id": session_id,
                    "exchange_count": session.exchange_count,
                    "appointment_id": appointment_details.get("appointment_id"),
                },
            )

            return {
                "session_id": session_id,
                "confirmation_state": session.confirmation_state,
                "exchange_count": session.exchange_count,
                "remaining_exchanges": session.max_exchanges - session.exchange_count,
                "appointment_details": appointment_details,
                "next_action": "play_confirmation_audio",
            }

        except Exception as e:
            logger.error(f"Failed to start confirmation flow: {e}")
            audit_logger_instance.log_system_event(
                action="TTS_CONFIRMATION_FLOW_START",
                result="FAILURE",
                additional_data={"session_id": session_id, "error": str(e)},
            )
            raise

    async def process_confirmation_response(
        self, session_id: str, user_response: str
    ) -> Dict[str, Any]:
        """
        Process patient response to appointment confirmation.

        Args:
            session_id: Active session identifier
            user_response: Patient's voice response

        Returns:
            Response processing result and next action
        """
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            if session.confirmation_state != "pending":
                raise ValueError(f"Session {session_id} not in confirmation state")

            session.exchange_count += 1
            session.last_activity = datetime.utcnow()

            # Process response to determine intent
            response_lower = user_response.lower().strip()

            # Check for confirmation keywords
            confirm_keywords = [
                "yes",
                "confirm",
                "correct",
                "that's right",
                "ok",
                "okay",
                "sounds good",
            ]
            decline_keywords = ["no", "incorrect", "wrong", "cancel", "not right"]
            change_keywords = [
                "change",
                "different",
                "reschedule",
                "modify",
                "another time",
            ]

            if any(keyword in response_lower for keyword in confirm_keywords):
                session.confirmation_state = "confirmed"
                next_action = "complete_appointment"
            elif any(keyword in response_lower for keyword in decline_keywords):
                session.confirmation_state = "declined"
                next_action = "cancel_appointment"
            elif any(keyword in response_lower for keyword in change_keywords):
                session.confirmation_state = "needs_changes"
                next_action = "request_changes"
            else:
                # Unclear response, ask for clarification
                if session.exchange_count >= session.max_exchanges:
                    session.status = "expired"
                    next_action = "human_handoff"
                else:
                    next_action = "request_clarification"

            audit_logger_instance.log_system_event(
                action="TTS_CONFIRMATION_RESPONSE_PROCESSED",
                result="SUCCESS",
                additional_data={
                    "session_id": session_id,
                    "confirmation_state": session.confirmation_state,
                    "exchange_count": session.exchange_count,
                    "next_action": next_action,
                },
            )

            return {
                "session_id": session_id,
                "confirmation_state": session.confirmation_state,
                "exchange_count": session.exchange_count,
                "remaining_exchanges": session.max_exchanges - session.exchange_count,
                "user_response": user_response,
                "next_action": next_action,
                "interpretation": {
                    "confirmed": session.confirmation_state == "confirmed",
                    "declined": session.confirmation_state == "declined",
                    "needs_changes": session.confirmation_state == "needs_changes",
                },
            }

        except Exception as e:
            logger.error(f"Failed to process confirmation response: {e}")
            audit_logger_instance.log_system_event(
                action="TTS_CONFIRMATION_RESPONSE_PROCESSING",
                result="FAILURE",
                additional_data={"session_id": session_id, "error": str(e)},
            )
            raise

    async def handle_mid_conversation_hangup(self, session_id: str) -> Dict[str, Any]:
        """
        Handle graceful mid-conversation hangup during confirmation flow.

        Args:
            session_id: Session identifier

        Returns:
            Hangup handling result
        """
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                logger.warning(f"Hangup attempt on non-existent session {session_id}")
                return {"session_id": session_id, "status": "not_found"}

            # Save partial progress if in confirmation state
            partial_data = None
            if session.confirmation_state == "pending" and hasattr(
                session.context, "appointment_details"
            ):
                partial_data = {
                    "appointment_details": session.context.appointment_details,
                    "exchange_count": session.exchange_count,
                    "confirmation_state": session.confirmation_state,
                }

            # End session with hangup reason
            summary = await self.end_session(session_id, "mid_conversation_hangup")

            audit_logger_instance.log_system_event(
                action="TTS_CONFIRMATION_HANGUP_HANDLED",
                result="SUCCESS",
                additional_data={
                    "session_id": session_id,
                    "had_partial_data": partial_data is not None,
                    "exchange_count": session.exchange_count,
                },
            )

            return {
                "session_id": session_id,
                "status": "hangup_handled",
                "summary": summary,
                "partial_data": partial_data,
                "follow_up_recommended": partial_data is not None,
            }

        except Exception as e:
            logger.error(f"Failed to handle mid-conversation hangup: {e}")
            audit_logger_instance.log_system_event(
                action="TTS_CONFIRMATION_HANGUP_HANDLING",
                result="FAILURE",
                additional_data={"session_id": session_id, "error": str(e)},
            )
            raise

    def check_exchange_limit(self, session_id: str) -> Dict[str, Any]:
        """
        Check if session is within exchange limits per AC requirement.

        Args:
            session_id: Session identifier

        Returns:
            Exchange limit status
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return {"session_id": session_id, "exists": False}

        within_limit = session.exchange_count < session.max_exchanges
        remaining = max(0, session.max_exchanges - session.exchange_count)

        return {
            "session_id": session_id,
            "exchange_count": session.exchange_count,
            "max_exchanges": session.max_exchanges,
            "within_limit": within_limit,
            "remaining_exchanges": remaining,
            "should_complete": not within_limit,
        }


# Global conversation manager instance
conversation_manager = ConversationManager()
