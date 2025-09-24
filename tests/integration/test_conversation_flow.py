"""
Integration tests for conversation flow and multi-turn context retention.
Tests the complete NLP + conversation management workflow.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.conversation_manager import ConversationSession, conversation_manager
from src.services.nlp_processor import (
    AppointmentDateTime,
    AppointmentReason,
    AppointmentType,
    AppointmentTypeEntity,
    ExtractionResult,
    PatientName,
)


class TestConversationFlow:
    """Integration tests for conversation flow."""

    def setup_method(self):
        """Set up test fixtures."""
        # Clear any existing sessions
        conversation_manager.active_sessions.clear()

    @pytest.mark.asyncio
    async def test_complete_conversation_flow(self):
        """Test a complete conversation from start to finish."""
        # Mock NLP processor responses for different turns
        mock_responses = [
            # Turn 1: Patient provides name
            ExtractionResult(
                patient_name=PatientName(
                    value="John Smith",
                    confidence=0.9,
                    raw_text="Hi, this is John Smith",
                ),
                input_text="Hi, this is John Smith",
                overall_confidence=0.9,
            ),
            # Turn 2: Patient provides appointment type and date
            ExtractionResult(
                appointment_datetime=AppointmentDateTime(
                    value=datetime(2024, 6, 15, 14, 30),
                    confidence=0.8,
                    raw_text="I need a checkup tomorrow at 2:30pm",
                    is_relative=True,
                    original_format="tomorrow at 2:30pm",
                ),
                appointment_type=AppointmentTypeEntity(
                    value=AppointmentType.CHECKUP,
                    confidence=0.8,
                    raw_text="I need a checkup tomorrow at 2:30pm",
                ),
                input_text="I need a checkup tomorrow at 2:30pm",
                overall_confidence=0.8,
            ),
            # Turn 3: Patient provides reason
            ExtractionResult(
                reason=AppointmentReason(
                    value="annual physical exam",
                    confidence=0.9,
                    raw_text="It's for my annual physical",
                    medical_keywords=["physical"],
                    urgency_indicators=[],
                ),
                input_text="It's for my annual physical",
                overall_confidence=0.9,
            ),
        ]

        with patch(
            "src.services.nlp_processor.nlp_processor.extract_entities"
        ) as mock_extract, patch(
            "src.services.nlp_processor.nlp_processor.enhance_with_medical_terminology"
        ) as mock_enhance:
            # Set up mock responses
            mock_extract.side_effect = mock_responses
            mock_enhance.side_effect = lambda x: x  # Return unchanged

            # Start conversation session
            session_id = await conversation_manager.start_session(
                call_id="test_call_123", phone_number_hash="hash_abc123"
            )

            assert session_id is not None
            assert len(conversation_manager.active_sessions) == 1

            # Turn 1: Patient introduces themselves
            response1 = await conversation_manager.process_turn(
                session_id, "Hi, this is John Smith"
            )

            assert response1["session_id"] == session_id
            assert response1["turn_count"] == 1
            assert response1["next_action"] == "gather_information"
            assert (
                response1["accumulated_entities"]["patient_name"]["value"]
                == "John Smith"
            )

            # Turn 2: Patient provides appointment details
            response2 = await conversation_manager.process_turn(
                session_id, "I need a checkup tomorrow at 2:30pm"
            )

            assert response2["turn_count"] == 2
            assert response2["next_action"] in [
                "request_clarification",
                "gather_information",
            ]

            # Should have accumulated patient name from previous turn
            assert (
                response2["accumulated_entities"]["patient_name"]["value"]
                == "John Smith"
            )
            assert (
                response2["accumulated_entities"]["appointment_type"]["value"]
                == "checkup"
            )

            # Turn 3: Patient provides reason
            response3 = await conversation_manager.process_turn(
                session_id, "It's for my annual physical"
            )

            assert response3["turn_count"] == 3
            assert response3["next_action"] in [
                "confirm_appointment",
                "request_clarification",
            ]

            # Should have all entities accumulated
            accumulated = response3["accumulated_entities"]
            assert accumulated["patient_name"]["value"] == "John Smith"
            assert accumulated["appointment_type"]["value"] == "checkup"
            assert accumulated["reason"]["value"] == "annual physical exam"

            # End session
            summary = await conversation_manager.end_session(session_id, "completed")
            assert summary["session_id"] == session_id
            assert summary["turn_count"] == 3
            assert summary["final_status"] == "completed"

    @pytest.mark.asyncio
    async def test_conversation_context_retention(self):
        """Test that conversation context is retained across turns."""
        with patch(
            "src.services.nlp_processor.nlp_processor.extract_entities"
        ) as mock_extract, patch(
            "src.services.nlp_processor.nlp_processor.enhance_with_medical_terminology"
        ) as mock_enhance:
            mock_enhance.side_effect = lambda x: x

            # Start session
            session_id = await conversation_manager.start_session(
                "call_456", "hash_def456"
            )

            # Turn 1: Only extract name
            mock_extract.return_value = ExtractionResult(
                patient_name=PatientName(
                    value="Jane Doe", confidence=0.9, raw_text="Jane Doe"
                ),
                input_text="This is Jane Doe",
                overall_confidence=0.9,
            )

            response1 = await conversation_manager.process_turn(
                session_id, "This is Jane Doe"
            )

            # Turn 2: Only extract appointment type, name should be retained
            mock_extract.return_value = ExtractionResult(
                appointment_type=AppointmentTypeEntity(
                    value=AppointmentType.URGENT,
                    confidence=0.8,
                    raw_text="I need urgent care",
                ),
                input_text="I need urgent care",
                overall_confidence=0.8,
            )

            response2 = await conversation_manager.process_turn(
                session_id, "I need urgent care"
            )

            # Verify context retention
            accumulated = response2["accumulated_entities"]
            assert (
                accumulated["patient_name"]["value"] == "Jane Doe"
            )  # Retained from turn 1
            assert accumulated["appointment_type"]["value"] == "urgent"  # From turn 2

    @pytest.mark.asyncio
    async def test_conversation_timeout_handling(self):
        """Test conversation timeout and cleanup."""
        session_id = await conversation_manager.start_session(
            "call_timeout", "hash_timeout"
        )

        # Manually set last activity to expired time
        session = conversation_manager.active_sessions[session_id]
        session.last_activity = datetime.utcnow() - timedelta(minutes=15)  # Expired

        # Run cleanup
        await conversation_manager._cleanup_expired_sessions()

        # Session should be removed
        assert session_id not in conversation_manager.active_sessions

    @pytest.mark.asyncio
    async def test_session_turn_limit(self):
        """Test that sessions respect turn limits."""
        with patch(
            "src.services.nlp_processor.nlp_processor.extract_entities"
        ) as mock_extract, patch(
            "src.services.nlp_processor.nlp_processor.enhance_with_medical_terminology"
        ) as mock_enhance:
            mock_extract.return_value = ExtractionResult(
                input_text="test", overall_confidence=0.3
            )
            mock_enhance.side_effect = lambda x: x

            session_id = await conversation_manager.start_session(
                "call_limit", "hash_limit"
            )

            # Set low turn limit for testing
            conversation_manager.active_sessions[session_id].max_turns = 3

            # Process turns up to limit
            for i in range(3):
                await conversation_manager.process_turn(session_id, f"Turn {i+1}")

            # Next turn should fail
            with pytest.raises(ValueError, match="exceeded maximum turns"):
                await conversation_manager.process_turn(session_id, "Excess turn")

    @pytest.mark.asyncio
    async def test_confirmation_dialog_generation(self):
        """Test appointment confirmation dialog generation."""
        session_id = await conversation_manager.start_session(
            "call_confirm", "hash_confirm"
        )

        # Set up session with complete appointment information
        session = conversation_manager.active_sessions[session_id]
        future_date = datetime.now() + timedelta(days=1)

        session.context.accumulated_entities.patient_name = PatientName(
            value="Test Patient", confidence=0.9, raw_text="Test Patient"
        )
        session.context.accumulated_entities.appointment_datetime = AppointmentDateTime(
            value=future_date.replace(hour=10, minute=0),
            confidence=0.8,
            raw_text="tomorrow at 10am",
        )
        session.context.accumulated_entities.appointment_type = AppointmentTypeEntity(
            value=AppointmentType.CHECKUP, confidence=0.8, raw_text="checkup"
        )
        session.context.accumulated_entities.reason = AppointmentReason(
            value="routine visit", confidence=0.7, raw_text="routine visit"
        )

        # Generate confirmation dialog
        confirmation = await conversation_manager.generate_confirmation_dialog(
            session_id
        )

        assert confirmation["session_id"] == session_id
        assert confirmation["confirmation_type"] == "appointment_details"
        assert "Test Patient" in confirmation["confirmation_text"]
        assert "Checkup" in confirmation["confirmation_text"]

    @pytest.mark.asyncio
    async def test_clarification_workflow(self):
        """Test clarification question generation and handling."""
        with patch(
            "src.services.nlp_processor.nlp_processor.get_clarification_questions"
        ) as mock_clarify:
            mock_clarify.return_value = [
                "Could you please tell me your full name?",
                "What date and time would you prefer?",
            ]

            session_id = await conversation_manager.start_session(
                "call_clarify", "hash_clarify"
            )

            # Add clarifications
            await conversation_manager.add_clarification(
                session_id, "Could you please tell me your full name?"
            )

            session = conversation_manager.active_sessions[session_id]
            assert len(session.context.clarification_history) == 1
            assert (
                session.context.last_clarification
                == "Could you please tell me your full name?"
            )

    @pytest.mark.asyncio
    async def test_session_statistics(self):
        """Test session statistics collection."""
        # Create multiple sessions
        session1 = await conversation_manager.start_session("call_1", "hash_1")
        session2 = await conversation_manager.start_session("call_2", "hash_2")

        # Process some turns
        with patch(
            "src.services.nlp_processor.nlp_processor.extract_entities"
        ) as mock_extract, patch(
            "src.services.nlp_processor.nlp_processor.enhance_with_medical_terminology"
        ) as mock_enhance:
            mock_extract.return_value = ExtractionResult(
                input_text="test", overall_confidence=0.5
            )
            mock_enhance.side_effect = lambda x: x

            await conversation_manager.process_turn(session1, "Hello")
            await conversation_manager.process_turn(session1, "I need help")
            await conversation_manager.process_turn(session2, "Hi there")

        # Check statistics
        stats = conversation_manager.get_session_statistics()

        assert stats["active_sessions"] == 2
        assert stats["average_turns"] == 1.5  # (2 + 1) / 2
        assert "average_duration_seconds" in stats
        assert "session_statuses" in stats

    @pytest.mark.asyncio
    async def test_error_handling_in_conversation(self):
        """Test error handling during conversation processing."""
        session_id = await conversation_manager.start_session(
            "call_error", "hash_error"
        )

        # Mock NLP processor to raise exception
        with patch(
            "src.services.nlp_processor.nlp_processor.extract_entities"
        ) as mock_extract:
            mock_extract.side_effect = Exception("NLP processing failed")

            # Should raise exception and mark session as error
            with pytest.raises(Exception, match="NLP processing failed"):
                await conversation_manager.process_turn(session_id, "Test input")

            # Session should be marked as error
            session = conversation_manager.active_sessions.get(session_id)
            assert session.status == "error"

    @pytest.mark.asyncio
    async def test_session_status_tracking(self):
        """Test session status tracking and retrieval."""
        session_id = await conversation_manager.start_session(
            "call_status", "hash_status"
        )

        # Check initial status
        status = await conversation_manager.get_session_status(session_id)
        assert status["exists"]
        assert status["status"] == "active"
        assert status["turn_count"] == 0

        # Process a turn
        with patch(
            "src.services.nlp_processor.nlp_processor.extract_entities"
        ) as mock_extract, patch(
            "src.services.nlp_processor.nlp_processor.enhance_with_medical_terminology"
        ) as mock_enhance:
            mock_extract.return_value = ExtractionResult(
                input_text="test", overall_confidence=0.5
            )
            mock_enhance.side_effect = lambda x: x

            await conversation_manager.process_turn(session_id, "Hello")

        # Check updated status
        status = await conversation_manager.get_session_status(session_id)
        assert status["turn_count"] == 1
        assert status["duration_seconds"] > 0

        # Check non-existent session
        status = await conversation_manager.get_session_status("non_existent")
        assert not status["exists"]
        assert status["status"] == "not_found"


if __name__ == "__main__":
    pytest.main([__file__])
