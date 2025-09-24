"""
Unit tests for NLP Processor service.
Tests entity extraction, medical terminology processing, and validation.
"""

import json
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.nlp_processor import (
    MEDICAL_TERMINOLOGY,
    AppointmentDateTime,
    AppointmentReason,
    AppointmentType,
    AppointmentTypeEntity,
    ConfidenceLevel,
    ConversationContext,
    ExtractionResult,
    NLPProcessor,
    PatientName,
)


class TestNLPProcessor:
    """Test cases for NLP Processor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.nlp = NLPProcessor()
        # Mock OpenAI client for testing
        self.nlp.client = Mock()

    def test_initialization(self):
        """Test NLP processor initialization."""
        assert self.nlp is not None
        assert hasattr(self.nlp, "cost_tracking")
        assert self.nlp.cost_tracking["total_requests"] == 0

    @pytest.mark.asyncio
    async def test_extract_entities_success(self):
        """Test successful entity extraction."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(
            {
                "patient_name": {
                    "value": "John Doe",
                    "confidence": 0.9,
                    "first_name": "John",
                    "last_name": "Doe",
                },
                "appointment_datetime": {
                    "value": "2024-01-15T14:30:00",
                    "confidence": 0.8,
                    "is_relative": False,
                    "original_format": "January 15th at 2:30pm",
                },
                "appointment_type": {
                    "value": "checkup",
                    "confidence": 0.7,
                    "estimated_duration": 30,
                },
                "reason": {
                    "value": "annual physical",
                    "confidence": 0.9,
                    "medical_keywords": ["physical"],
                    "urgency_indicators": [],
                },
            }
        )
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 100

        self.nlp.client.chat.completions.create = Mock(return_value=mock_response)

        result = await self.nlp.extract_entities(
            "I'm John Doe and I need a checkup on January 15th at 2:30pm"
        )

        assert result.patient_name is not None
        assert result.patient_name.value == "John Doe"
        assert result.patient_name.first_name == "John"
        assert result.patient_name.last_name == "Doe"
        assert result.patient_name.confidence == 0.9

        assert result.appointment_datetime is not None
        assert result.appointment_datetime.original_format == "January 15th at 2:30pm"
        assert not result.appointment_datetime.is_relative

        assert result.appointment_type is not None
        assert result.appointment_type.value == AppointmentType.CHECKUP
        assert result.appointment_type.estimated_duration == 30

        assert result.reason is not None
        assert result.reason.value == "annual physical"
        assert "physical" in result.reason.medical_keywords

    @pytest.mark.asyncio
    async def test_extract_entities_with_context(self):
        """Test entity extraction with conversation context."""
        # Create conversation context
        context = ConversationContext(call_id="test_call")
        context.accumulated_entities.patient_name = PatientName(
            value="Jane Smith", confidence=0.9, raw_text="Previous context"
        )

        # Mock OpenAI response with partial new information
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(
            {
                "appointment_datetime": {
                    "value": "2024-01-20T10:00:00",
                    "confidence": 0.8,
                    "is_relative": True,
                    "original_format": "tomorrow at 10am",
                },
                "appointment_type": {
                    "value": "follow_up",
                    "confidence": 0.7,
                    "estimated_duration": 20,
                },
            }
        )
        mock_response.usage = Mock()
        mock_response.usage.total_tokens = 80

        self.nlp.client.chat.completions.create = Mock(return_value=mock_response)

        result = await self.nlp.extract_entities(
            "I need a follow-up tomorrow at 10am", context
        )

        # Should have appointment info from new extraction
        assert result.appointment_datetime is not None
        assert result.appointment_datetime.is_relative
        assert result.appointment_type.value == AppointmentType.FOLLOW_UP

    def test_enhance_with_medical_terminology(self):
        """Test medical terminology enhancement."""
        # Create initial result with low confidence appointment type
        result = ExtractionResult(
            input_text="I need urgent care for my headache",
            appointment_type=AppointmentTypeEntity(
                value=AppointmentType.UNKNOWN,
                confidence=0.3,
                raw_text="I need urgent care for my headache",
            ),
            reason=AppointmentReason(
                value="headache",
                confidence=0.7,
                raw_text="I need urgent care for my headache",
                medical_keywords=[],
                urgency_indicators=[],
            ),
        )

        enhanced = self.nlp.enhance_with_medical_terminology(result)

        # Should detect urgent appointment type
        assert enhanced.appointment_type.value == AppointmentType.URGENT
        assert enhanced.appointment_type.confidence > 0.3

        # Should detect medical keywords and urgency indicators
        assert "headache" in enhanced.reason.medical_keywords
        assert "urgent" in enhanced.reason.urgency_indicators
        assert enhanced.reason.confidence > 0.7  # Boosted confidence

    def test_fuzzy_match_appointment_type(self):
        """Test fuzzy matching for appointment types."""
        # Test exact match
        result = self.nlp._fuzzy_match_appointment_type("I need a checkup")
        assert result is not None
        assert result.value == AppointmentType.CHECKUP
        assert result.confidence == 0.8

        # Test synonym match
        result = self.nlp._fuzzy_match_appointment_type("I need a routine visit")
        assert result is not None
        assert result.value == AppointmentType.CHECKUP
        assert result.confidence == 0.6

        # Test no match
        result = self.nlp._fuzzy_match_appointment_type("I need something random")
        assert result is None

    def test_extract_medical_keywords(self):
        """Test medical keyword extraction."""
        keywords = self.nlp._extract_medical_keywords(
            "I have a bad headache and stomach pain"
        )
        assert "headache" in keywords
        assert "pain" in keywords
        assert "stomach" in keywords
        assert "bad" not in keywords  # Not a medical keyword

    def test_extract_urgency_indicators(self):
        """Test urgency indicator extraction."""
        indicators = self.nlp._extract_urgency_indicators(
            "This is urgent, I'm in severe pain"
        )
        assert "urgent" in indicators
        assert "severe" in indicators
        assert "pain" in indicators

    def test_validate_extraction_valid(self):
        """Test validation of valid extraction result."""
        # Use future date to avoid past date validation error
        future_date = datetime.now() + timedelta(days=30)

        result = ExtractionResult(
            patient_name=PatientName(
                value="John Smith", confidence=0.9, raw_text="John Smith"
            ),
            appointment_datetime=AppointmentDateTime(
                value=future_date, confidence=0.8, raw_text="June 15th at 2:30pm"
            ),
            appointment_type=AppointmentTypeEntity(
                value=AppointmentType.CHECKUP, confidence=0.7, raw_text="checkup"
            ),
            reason=AppointmentReason(
                value="annual physical exam",
                confidence=0.8,
                raw_text="annual physical exam",
            ),
            overall_confidence=0.8,
        )

        is_valid, errors = self.nlp.validate_extraction(result)
        assert is_valid
        assert len(errors) == 0

    def test_validate_extraction_invalid(self):
        """Test validation of invalid extraction result."""
        result = ExtractionResult(
            patient_name=PatientName(
                value="X", confidence=0.2, raw_text="X"  # Too short  # Too low
            ),
            appointment_datetime=AppointmentDateTime(
                value=datetime(2020, 1, 1, 14, 30),  # In the past
                confidence=0.8,
                raw_text="January 1st 2020",
            ),
            overall_confidence=0.3,  # Too low
        )

        is_valid, errors = self.nlp.validate_extraction(result)
        assert not is_valid
        assert len(errors) > 0
        assert any("too short" in error.lower() for error in errors)
        assert any("past" in error.lower() for error in errors)
        assert any("confidence too low" in error.lower() for error in errors)

    def test_calculate_confidence_score(self):
        """Test confidence score calculation."""
        result = ExtractionResult(
            patient_name=PatientName(value="John Doe", confidence=0.9, raw_text=""),
            appointment_datetime=AppointmentDateTime(
                value=datetime.now(), confidence=0.8, raw_text=""
            ),
            appointment_type=AppointmentTypeEntity(
                value=AppointmentType.CHECKUP, confidence=0.7, raw_text=""
            ),
            reason=AppointmentReason(
                value="checkup",
                confidence=0.6,
                raw_text="",
                medical_keywords=["pain"],  # Should boost confidence
                urgency_indicators=[],
            ),
        )

        confidence = self.nlp.calculate_confidence_score(result)
        assert 0.0 <= confidence <= 1.0
        assert (
            confidence > 0.7
        )  # Should be high due to complete entities and medical keywords

    def test_get_clarification_questions(self):
        """Test clarification question generation."""
        # Result missing patient name and date/time
        result = ExtractionResult(
            appointment_type=AppointmentTypeEntity(
                value=AppointmentType.CHECKUP, confidence=0.8, raw_text="checkup"
            )
        )

        questions = self.nlp.get_clarification_questions(result)
        assert len(questions) > 0
        assert any("name" in question.lower() for question in questions)
        assert any("date" in question.lower() for question in questions)

    def test_cost_tracking(self):
        """Test cost tracking functionality."""
        initial_cost = self.nlp.cost_tracking["monthly_cost_cents"]

        # Mock usage object
        mock_usage = Mock()
        mock_usage.total_tokens = 1000

        self.nlp._update_cost_tracking(mock_usage)

        assert self.nlp.cost_tracking["total_tokens"] == 1000
        assert self.nlp.cost_tracking["total_requests"] == 1
        # Cost should be calculated: (1000 tokens / 1000) * 0.15 = 0.15 cents, converted to int = 0
        # But let's check that it's at least non-negative
        assert self.nlp.cost_tracking["monthly_cost_cents"] >= initial_cost

        stats = self.nlp.get_cost_stats()
        assert "cost_dollars" in stats
        assert "avg_tokens_per_request" in stats
        assert stats["avg_tokens_per_request"] == 1000


class TestConversationContext:
    """Test cases for conversation context management."""

    def test_context_initialization(self):
        """Test context initialization."""
        context = ConversationContext(call_id="test_call")
        assert context.call_id == "test_call"
        assert context.turn_count == 0
        assert context.accumulated_entities is not None
        assert isinstance(context.clarification_history, list)

    def test_add_clarification(self):
        """Test adding clarification to context."""
        context = ConversationContext(call_id="test_call")
        context.add_clarification("Please provide your name")
        context.add_clarification("What date would you prefer?")

        assert context.last_clarification == "What date would you prefer?"
        assert len(context.clarification_history) == 2
        assert "Please provide your name" in context.clarification_history

    def test_merge_entities(self):
        """Test merging entities in context."""
        context = ConversationContext(call_id="test_call")

        # First extraction
        extraction1 = ExtractionResult(
            patient_name=PatientName(value="John Doe", confidence=0.9, raw_text="")
        )
        context.merge_entities(extraction1)

        assert context.accumulated_entities.patient_name.value == "John Doe"

        # Second extraction with higher confidence name and new appointment type
        extraction2 = ExtractionResult(
            patient_name=PatientName(value="John Smith", confidence=0.95, raw_text=""),
            appointment_type=AppointmentTypeEntity(
                value=AppointmentType.CHECKUP, confidence=0.8, raw_text=""
            ),
        )
        context.merge_entities(extraction2)

        # Should update name (higher confidence) and add appointment type
        assert context.accumulated_entities.patient_name.value == "John Smith"
        assert (
            context.accumulated_entities.appointment_type.value
            == AppointmentType.CHECKUP
        )

    def test_context_to_dict(self):
        """Test context serialization."""
        context = ConversationContext(call_id="test_call")
        context.turn_count = 3
        context.add_clarification("Test clarification")

        context_dict = context.to_dict()
        assert context_dict["call_id"] == "test_call"
        assert context_dict["turn_count"] == 3
        assert context_dict["last_clarification"] == "Test clarification"


class TestExtractedEntities:
    """Test cases for extracted entity classes."""

    def test_confidence_level_property(self):
        """Test confidence level enum property."""
        high_conf = PatientName(value="John Doe", confidence=0.9, raw_text="")
        assert high_conf.confidence_level == ConfidenceLevel.HIGH

        medium_conf = PatientName(value="John Doe", confidence=0.6, raw_text="")
        assert medium_conf.confidence_level == ConfidenceLevel.MEDIUM

        low_conf = PatientName(value="John Doe", confidence=0.3, raw_text="")
        assert low_conf.confidence_level == ConfidenceLevel.LOW

    def test_extraction_result_missing_entities(self):
        """Test missing entities detection."""
        # Empty result
        result = ExtractionResult()
        missing = result.get_missing_entities()
        assert len(missing) == 4  # All entities missing

        # Partial result
        result.patient_name = PatientName(value="John Doe", confidence=0.9, raw_text="")
        missing = result.get_missing_entities()
        assert len(missing) == 3  # 3 entities still missing
        assert "patient_name" not in missing

    def test_extraction_result_minimum_entities(self):
        """Test minimum entities check."""
        result = ExtractionResult()
        assert not result.has_minimum_entities()

        result.patient_name = PatientName(value="John Doe", confidence=0.9, raw_text="")
        assert result.has_minimum_entities()

        # Low confidence should fail
        result.patient_name.confidence = 0.2
        assert not result.has_minimum_entities()

    def test_extraction_result_to_dict(self):
        """Test extraction result serialization."""
        result = ExtractionResult(
            patient_name=PatientName(value="John Doe", confidence=0.9, raw_text=""),
            input_text="Test input",
        )
        # overall_confidence is calculated automatically in __post_init__

        result_dict = result.to_dict()
        assert result_dict["input_text"] == "Test input"
        # overall_confidence is auto-calculated as average of non-None entities
        assert (
            result_dict["overall_confidence"] == 0.9
        )  # Only patient_name exists with 0.9
        assert result_dict["patient_name"]["value"] == "John Doe"
        assert result_dict["patient_name"]["confidence"] == 0.9


if __name__ == "__main__":
    pytest.main([__file__])
