"""
Unit tests for Conversation Manager with TTS Confirmation Flow

Tests conversation management, confirmation flow states, exchange counting,
and graceful hangup handling.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.conversation_manager import ConversationManager, ConversationSession


class TestConversationManagerTTSFlow:
    """Test suite for TTS confirmation flow in Conversation Manager."""

    @pytest.fixture
    def conversation_manager_instance(self):
        """Create a clean conversation manager instance for testing."""
        return ConversationManager()

    @pytest.fixture
    def sample_session_id(self, conversation_manager_instance):
        """Create a sample conversation session for testing."""
        # Mock the dependencies
        with patch(
            "src.services.conversation_manager.ConversationContext"
        ) as MockContext:
            mock_context = Mock()
            MockContext.return_value = mock_context

            session_id = "test-session-123"
            phone_hash = "test-phone-hash"

            # Manually create session for testing
            session = ConversationSession(
                session_id=session_id,
                call_id="test-call-123",
                phone_number_hash=phone_hash,
                start_time=datetime.utcnow(),
                last_activity=datetime.utcnow(),
                context=mock_context,
                status="active",
                confirmation_state="none",
                exchange_count=0,
                max_exchanges=5,
            )

            conversation_manager_instance.active_sessions[session_id] = session
            return session_id

    @pytest.fixture
    def sample_appointment_details(self):
        """Sample appointment details for testing."""
        return {
            "appointment_id": "appt-123",
            "date": "2024-03-15",
            "time": "14:30",
            "provider_name": "Dr. Smith",
            "location": "Main Clinic",
            "appointment_type": "checkup",
        }

    @pytest.mark.asyncio
    async def test_start_session_with_tts_fields(self, conversation_manager_instance):
        """Test session creation includes TTS-specific fields."""
        with patch(
            "src.services.conversation_manager.ConversationContext"
        ) as MockContext:
            mock_context = Mock()
            MockContext.return_value = mock_context

            session_id = await conversation_manager_instance.start_session(
                call_id="test-call-123", phone_number_hash="test-hash"
            )

            session = conversation_manager_instance.active_sessions[session_id]

            assert session.confirmation_state == "none"
            assert session.exchange_count == 0
            assert session.max_exchanges == 5
            assert session.status == "active"

    @pytest.mark.asyncio
    async def test_start_confirmation_flow_success(
        self,
        conversation_manager_instance,
        sample_session_id,
        sample_appointment_details,
    ):
        """Test successful start of TTS confirmation flow."""
        result = await conversation_manager_instance.start_confirmation_flow(
            session_id=sample_session_id, appointment_details=sample_appointment_details
        )

        session = conversation_manager_instance.active_sessions[sample_session_id]

        assert result["session_id"] == sample_session_id
        assert result["confirmation_state"] == "pending"
        assert result["exchange_count"] == 1
        assert result["remaining_exchanges"] == 4
        assert result["next_action"] == "play_confirmation_audio"
        assert session.confirmation_state == "pending"
        assert session.exchange_count == 1

    @pytest.mark.asyncio
    async def test_start_confirmation_flow_exchange_limit_exceeded(
        self,
        conversation_manager_instance,
        sample_session_id,
        sample_appointment_details,
    ):
        """Test starting confirmation flow when exchange limit is exceeded."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.exchange_count = 5  # At limit

        with pytest.raises(ValueError, match="exceeded maximum exchanges"):
            await conversation_manager_instance.start_confirmation_flow(
                session_id=sample_session_id,
                appointment_details=sample_appointment_details,
            )

        assert session.status == "expired"

    @pytest.mark.asyncio
    async def test_start_confirmation_flow_session_not_found(
        self, conversation_manager_instance, sample_appointment_details
    ):
        """Test starting confirmation flow with non-existent session."""
        with pytest.raises(ValueError, match="Session .* not found"):
            await conversation_manager_instance.start_confirmation_flow(
                session_id="non-existent-session",
                appointment_details=sample_appointment_details,
            )

    @pytest.mark.asyncio
    async def test_process_confirmation_response_confirmed(
        self, conversation_manager_instance, sample_session_id
    ):
        """Test processing confirmation response - confirmed."""
        # Set up session in pending state
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.confirmation_state = "pending"
        session.exchange_count = 1

        test_responses = [
            "yes",
            "confirm",
            "correct",
            "that's right",
            "ok",
            "sounds good",
        ]

        for response in test_responses:
            session.confirmation_state = "pending"  # Reset
            session.exchange_count = 1

            result = await conversation_manager_instance.process_confirmation_response(
                session_id=sample_session_id, user_response=response
            )

            assert result["confirmation_state"] == "confirmed"
            assert result["next_action"] == "complete_appointment"
            assert result["interpretation"]["confirmed"] is True
            assert result["exchange_count"] == 2

    @pytest.mark.asyncio
    async def test_process_confirmation_response_declined(
        self, conversation_manager_instance, sample_session_id
    ):
        """Test processing confirmation response - declined."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.confirmation_state = "pending"
        session.exchange_count = 1

        test_responses = ["no", "incorrect", "wrong", "cancel", "not right"]

        for response in test_responses:
            session.confirmation_state = "pending"  # Reset
            session.exchange_count = 1

            result = await conversation_manager_instance.process_confirmation_response(
                session_id=sample_session_id, user_response=response
            )

            assert result["confirmation_state"] == "declined"
            assert result["next_action"] == "cancel_appointment"
            assert result["interpretation"]["declined"] is True

    @pytest.mark.asyncio
    async def test_process_confirmation_response_needs_changes(
        self, conversation_manager_instance, sample_session_id
    ):
        """Test processing confirmation response - needs changes."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.confirmation_state = "pending"
        session.exchange_count = 1

        test_responses = ["change", "different", "reschedule", "modify", "another time"]

        for response in test_responses:
            session.confirmation_state = "pending"  # Reset
            session.exchange_count = 1

            result = await conversation_manager_instance.process_confirmation_response(
                session_id=sample_session_id, user_response=response
            )

            assert result["confirmation_state"] == "needs_changes"
            assert result["next_action"] == "request_changes"
            assert result["interpretation"]["needs_changes"] is True

    @pytest.mark.asyncio
    async def test_process_confirmation_response_unclear(
        self, conversation_manager_instance, sample_session_id
    ):
        """Test processing unclear confirmation response."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.confirmation_state = "pending"
        session.exchange_count = 1

        result = await conversation_manager_instance.process_confirmation_response(
            session_id=sample_session_id,
            user_response="I'm not sure about something else",
        )

        assert result["next_action"] == "request_clarification"
        assert result["exchange_count"] == 2

    @pytest.mark.asyncio
    async def test_process_confirmation_response_exchange_limit_reached(
        self, conversation_manager_instance, sample_session_id
    ):
        """Test processing response when exchange limit is reached."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.confirmation_state = "pending"
        session.exchange_count = 4  # One away from limit

        result = await conversation_manager_instance.process_confirmation_response(
            session_id=sample_session_id, user_response="unclear response"
        )

        assert result["next_action"] == "human_handoff"
        assert session.status == "expired"

    @pytest.mark.asyncio
    async def test_process_confirmation_response_not_in_confirmation_state(
        self, conversation_manager_instance, sample_session_id
    ):
        """Test processing response when not in confirmation state."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.confirmation_state = "none"

        with pytest.raises(ValueError, match="not in confirmation state"):
            await conversation_manager_instance.process_confirmation_response(
                session_id=sample_session_id, user_response="yes"
            )

    @pytest.mark.asyncio
    async def test_handle_mid_conversation_hangup_with_partial_data(
        self,
        conversation_manager_instance,
        sample_session_id,
        sample_appointment_details,
    ):
        """Test graceful hangup handling with partial confirmation data."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.confirmation_state = "pending"
        session.exchange_count = 2
        session.context.appointment_details = sample_appointment_details

        result = await conversation_manager_instance.handle_mid_conversation_hangup(
            session_id=sample_session_id
        )

        assert result["status"] == "hangup_handled"
        assert result["follow_up_recommended"] is True
        assert result["partial_data"] is not None
        assert (
            result["partial_data"]["appointment_details"] == sample_appointment_details
        )
        assert result["partial_data"]["exchange_count"] == 2
        assert sample_session_id not in conversation_manager_instance.active_sessions

    @pytest.mark.asyncio
    async def test_handle_mid_conversation_hangup_no_partial_data(
        self, conversation_manager_instance, sample_session_id
    ):
        """Test graceful hangup handling without partial confirmation data."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.confirmation_state = "none"

        result = await conversation_manager_instance.handle_mid_conversation_hangup(
            session_id=sample_session_id
        )

        assert result["status"] == "hangup_handled"
        assert result["follow_up_recommended"] is False
        assert result["partial_data"] is None

    @pytest.mark.asyncio
    async def test_handle_mid_conversation_hangup_non_existent_session(
        self, conversation_manager_instance
    ):
        """Test hangup handling for non-existent session."""
        result = await conversation_manager_instance.handle_mid_conversation_hangup(
            session_id="non-existent-session"
        )

        assert result["session_id"] == "non-existent-session"
        assert result["status"] == "not_found"

    def test_check_exchange_limit_within_limit(
        self, conversation_manager_instance, sample_session_id
    ):
        """Test exchange limit checking - within limit."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.exchange_count = 2

        result = conversation_manager_instance.check_exchange_limit(sample_session_id)

        assert result["exchange_count"] == 2
        assert result["max_exchanges"] == 5
        assert result["within_limit"] is True
        assert result["remaining_exchanges"] == 3
        assert result["should_complete"] is False

    def test_check_exchange_limit_at_limit(
        self, conversation_manager_instance, sample_session_id
    ):
        """Test exchange limit checking - at limit."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        session.exchange_count = 5

        result = conversation_manager_instance.check_exchange_limit(sample_session_id)

        assert result["within_limit"] is False
        assert result["remaining_exchanges"] == 0
        assert result["should_complete"] is True

    def test_check_exchange_limit_non_existent_session(
        self, conversation_manager_instance
    ):
        """Test exchange limit checking for non-existent session."""
        result = conversation_manager_instance.check_exchange_limit("non-existent")

        assert result["exists"] is False

    @pytest.mark.asyncio
    async def test_conversation_session_dataclass_fields(self):
        """Test that ConversationSession has all required TTS fields."""
        mock_context = Mock()

        session = ConversationSession(
            session_id="test-123",
            call_id="call-123",
            phone_number_hash="hash-123",
            start_time=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            context=mock_context,
        )

        # Test default values
        assert session.confirmation_state == "none"
        assert session.exchange_count == 0
        assert session.max_exchanges == 5
        assert session.status == "active"
        assert session.max_turns == 5
        assert session.timeout_minutes == 10

    @pytest.mark.asyncio
    async def test_confirmation_flow_audit_logging(
        self,
        conversation_manager_instance,
        sample_session_id,
        sample_appointment_details,
    ):
        """Test that confirmation flow operations are properly audited."""
        with patch(
            "src.services.conversation_manager.audit_logger_instance"
        ) as mock_audit:
            # Test start confirmation flow logging
            await conversation_manager_instance.start_confirmation_flow(
                session_id=sample_session_id,
                appointment_details=sample_appointment_details,
            )

            mock_audit.log_system_event.assert_called()
            call_args = mock_audit.log_system_event.call_args
            assert call_args[1]["action"] == "TTS_CONFIRMATION_FLOW_STARTED"
            assert call_args[1]["result"] == "SUCCESS"

            # Test process response logging
            session = conversation_manager_instance.active_sessions[sample_session_id]
            session.confirmation_state = "pending"

            await conversation_manager_instance.process_confirmation_response(
                session_id=sample_session_id, user_response="yes"
            )

            # Should have been called again for response processing
            assert mock_audit.log_system_event.call_count >= 2

    @pytest.mark.asyncio
    async def test_last_activity_updates(
        self,
        conversation_manager_instance,
        sample_session_id,
        sample_appointment_details,
    ):
        """Test that last_activity is updated during confirmation flow."""
        session = conversation_manager_instance.active_sessions[sample_session_id]
        initial_activity = session.last_activity

        # Start confirmation flow
        await conversation_manager_instance.start_confirmation_flow(
            session_id=sample_session_id, appointment_details=sample_appointment_details
        )

        assert session.last_activity > initial_activity

        # Process response
        updated_activity = session.last_activity
        session.confirmation_state = "pending"

        await conversation_manager_instance.process_confirmation_response(
            session_id=sample_session_id, user_response="yes"
        )

        assert session.last_activity > updated_activity


class TestConversationManagerTTSIntegration:
    """Integration tests for TTS confirmation flow with other components."""

    @pytest.mark.asyncio
    async def test_confirmation_flow_with_appointment_storage(self):
        """Test that appointment details are properly stored during confirmation flow."""
        manager = ConversationManager()

        with patch(
            "src.services.conversation_manager.ConversationContext"
        ) as MockContext:
            mock_context = Mock()
            MockContext.return_value = mock_context

            # Start session
            session_id = await manager.start_session("call-123", "hash-123")

            appointment_details = {
                "appointment_id": "appt-456",
                "date": "2024-03-20",
                "provider_name": "Dr. Johnson",
            }

            # Start confirmation flow
            await manager.start_confirmation_flow(session_id, appointment_details)

            # Verify appointment details are stored in context
            session = manager.active_sessions[session_id]
            assert hasattr(session.context, "appointment_details")
            assert session.context.appointment_details == appointment_details

    @pytest.mark.asyncio
    async def test_error_handling_in_confirmation_flow(self):
        """Test error handling throughout the confirmation flow."""
        manager = ConversationManager()

        # Test with completely invalid session
        with pytest.raises(ValueError):
            await manager.start_confirmation_flow("invalid", {})

        with pytest.raises(ValueError):
            await manager.process_confirmation_response("invalid", "yes")


if __name__ == "__main__":
    pytest.main([__file__])
