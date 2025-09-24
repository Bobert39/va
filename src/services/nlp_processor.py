"""
Natural Language Processing service for appointment extraction.
Handles entity extraction from patient voice input for appointment scheduling.
"""

import json
import logging
import re
import time as time_module
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from src.audit import audit_logger_instance
from src.config import get_config

logger = logging.getLogger(__name__)


class AppointmentType(Enum):
    """Standard appointment types supported by the system."""

    CHECKUP = "checkup"
    FOLLOW_UP = "follow_up"
    URGENT = "urgent"
    CONSULTATION = "consultation"
    WELLNESS = "wellness"
    PHYSICAL = "physical"
    UNKNOWN = "unknown"


class ConfidenceLevel(Enum):
    """Confidence levels for extracted entities."""

    HIGH = "high"  # 0.8 - 1.0
    MEDIUM = "medium"  # 0.5 - 0.79
    LOW = "low"  # 0.0 - 0.49


@dataclass
class ExtractedEntity:
    """Base class for extracted entities with confidence scoring."""

    value: Any
    confidence: float
    raw_text: str

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get confidence level enum based on score."""
        if self.confidence >= 0.8:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 0.5:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW


@dataclass
class PatientName(ExtractedEntity):
    """Patient name entity."""

    value: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@dataclass
class AppointmentDateTime(ExtractedEntity):
    """Date/time entity for appointments."""

    value: Optional[datetime]
    date_part: Optional[date] = None
    time_part: Optional[time] = None
    is_relative: bool = False  # "tomorrow", "next week"
    original_format: str = ""


@dataclass
class AppointmentTypeEntity(ExtractedEntity):
    """Appointment type entity."""

    value: AppointmentType
    estimated_duration: int = 30  # minutes
    priority_level: str = "normal"


@dataclass
class AppointmentReason(ExtractedEntity):
    """Reason for appointment entity."""

    value: str
    medical_keywords: List[str] = None
    urgency_indicators: List[str] = None

    def __post_init__(self):
        if self.medical_keywords is None:
            self.medical_keywords = []
        if self.urgency_indicators is None:
            self.urgency_indicators = []


@dataclass
class ExtractionResult:
    """Complete result of NLP entity extraction."""

    patient_name: Optional[PatientName] = None
    appointment_datetime: Optional[AppointmentDateTime] = None
    appointment_type: Optional[AppointmentTypeEntity] = None
    reason: Optional[AppointmentReason] = None

    # Metadata
    extraction_timestamp: datetime = None
    processing_time_ms: float = 0.0
    input_text: str = ""
    overall_confidence: float = 0.0

    def __post_init__(self):
        if self.extraction_timestamp is None:
            self.extraction_timestamp = datetime.utcnow()

        # Calculate overall confidence as average of non-None entities
        confidences = []
        for entity in [
            self.patient_name,
            self.appointment_datetime,
            self.appointment_type,
            self.reason,
        ]:
            if entity is not None:
                confidences.append(entity.confidence)

        self.overall_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "patient_name": asdict(self.patient_name) if self.patient_name else None,
            "appointment_datetime": asdict(self.appointment_datetime)
            if self.appointment_datetime
            else None,
            "appointment_type": asdict(self.appointment_type)
            if self.appointment_type
            else None,
            "reason": asdict(self.reason) if self.reason else None,
            "extraction_timestamp": self.extraction_timestamp.isoformat()
            if self.extraction_timestamp
            else None,
            "processing_time_ms": self.processing_time_ms,
            "input_text": self.input_text,
            "overall_confidence": self.overall_confidence,
        }

    def has_minimum_entities(self) -> bool:
        """Check if extraction has minimum required entities for appointment."""
        return (
            self.patient_name is not None
            and self.patient_name.confidence_level != ConfidenceLevel.LOW
        )

    def get_missing_entities(self) -> List[str]:
        """Get list of missing or low-confidence entities."""
        missing = []

        if (
            not self.patient_name
            or self.patient_name.confidence_level == ConfidenceLevel.LOW
        ):
            missing.append("patient_name")

        if (
            not self.appointment_datetime
            or self.appointment_datetime.confidence_level == ConfidenceLevel.LOW
        ):
            missing.append("preferred_date_time")

        if (
            not self.appointment_type
            or self.appointment_type.confidence_level == ConfidenceLevel.LOW
        ):
            missing.append("appointment_type")

        if not self.reason or self.reason.confidence_level == ConfidenceLevel.LOW:
            missing.append("appointment_reason")

        return missing


@dataclass
class ConversationContext:
    """Context for multi-turn conversation management."""

    call_id: str
    turn_count: int = 0
    accumulated_entities: Optional[ExtractionResult] = None
    last_clarification: str = ""
    clarification_history: List[str] = None
    context_retention_turns: int = 5  # Maximum turns to retain context

    def __post_init__(self):
        if self.clarification_history is None:
            self.clarification_history = []
        if self.accumulated_entities is None:
            self.accumulated_entities = ExtractionResult()

    def add_clarification(self, clarification: str):
        """Add clarification to history."""
        self.clarification_history.append(clarification)
        self.last_clarification = clarification

        # Keep only recent clarifications
        if len(self.clarification_history) > self.context_retention_turns:
            self.clarification_history = self.clarification_history[
                -self.context_retention_turns :
            ]

    def merge_entities(self, new_extraction: ExtractionResult):
        """Merge new extraction results with accumulated entities."""
        # Update entities with higher confidence or fill missing ones
        if new_extraction.patient_name and (
            not self.accumulated_entities.patient_name
            or new_extraction.patient_name.confidence
            > self.accumulated_entities.patient_name.confidence
        ):
            self.accumulated_entities.patient_name = new_extraction.patient_name

        if new_extraction.appointment_datetime and (
            not self.accumulated_entities.appointment_datetime
            or new_extraction.appointment_datetime.confidence
            > self.accumulated_entities.appointment_datetime.confidence
        ):
            self.accumulated_entities.appointment_datetime = (
                new_extraction.appointment_datetime
            )

        if new_extraction.appointment_type and (
            not self.accumulated_entities.appointment_type
            or new_extraction.appointment_type.confidence
            > self.accumulated_entities.appointment_type.confidence
        ):
            self.accumulated_entities.appointment_type = new_extraction.appointment_type

        if new_extraction.reason and (
            not self.accumulated_entities.reason
            or new_extraction.reason.confidence
            > self.accumulated_entities.reason.confidence
        ):
            self.accumulated_entities.reason = new_extraction.reason

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "call_id": self.call_id,
            "turn_count": self.turn_count,
            "accumulated_entities": self.accumulated_entities.to_dict()
            if self.accumulated_entities
            else None,
            "last_clarification": self.last_clarification,
            "clarification_history": self.clarification_history,
            "context_retention_turns": self.context_retention_turns,
        }


# Medical terminology dictionary for healthcare-specific processing
MEDICAL_TERMINOLOGY = {
    "appointment_types": {
        "checkup": [
            "checkup",
            "check up",
            "routine visit",
            "regular visit",
            "wellness visit",
        ],
        "follow_up": [
            "follow up",
            "followup",
            "follow-up",
            "return visit",
            "check back",
        ],
        "urgent": ["urgent", "emergency", "asap", "urgent care", "immediate"],
        "consultation": [
            "consultation",
            "consult",
            "second opinion",
            "specialist visit",
        ],
        "physical": ["physical", "annual physical", "yearly physical", "physical exam"],
        "wellness": ["wellness", "preventive", "screening", "health maintenance"],
    },
    "urgency_indicators": [
        "urgent",
        "emergency",
        "asap",
        "immediate",
        "right away",
        "soon as possible",
        "pain",
        "severe",
        "bad",
        "can't wait",
        "need today",
        "hurts",
    ],
    "medical_keywords": [
        "pain",
        "ache",
        "hurt",
        "sore",
        "swollen",
        "fever",
        "sick",
        "infection",
        "headache",
        "stomach",
        "back",
        "chest",
        "breathing",
        "cough",
        "cold",
        "medication",
        "prescription",
        "refill",
        "lab work",
        "blood work",
        "test",
    ],
}


class NLPProcessor:
    """
    Natural Language Processing service for appointment entity extraction.

    Integrates with OpenAI GPT for structured entity extraction with medical
    terminology support and cost optimization.
    """

    def __init__(self):
        """Initialize NLP processor with OpenAI client."""
        self.client: Optional[OpenAI] = None
        self.api_key: Optional[str] = None
        self.cost_tracking = {
            "total_tokens": 0,
            "total_requests": 0,
            "monthly_cost_cents": 0,
        }
        self._initialize_client()

    def _initialize_client(self):
        """Initialize OpenAI client for NLP processing."""
        try:
            self.api_key = get_config("api_keys.openai_api_key")
            if not self.api_key:
                logger.warning("OpenAI API key not configured for NLP")
                return

            self.client = OpenAI(api_key=self.api_key)
            logger.info("NLP OpenAI client initialized successfully")

            audit_logger_instance.log_system_event(
                action="NLP_CLIENT_INITIALIZED", result="SUCCESS"
            )

        except Exception as e:
            logger.error(f"Failed to initialize NLP OpenAI client: {e}")
            audit_logger_instance.log_system_event(
                action="NLP_CLIENT_INITIALIZATION",
                result="FAILURE",
                additional_data={"error": str(e)},
            )

    async def extract_entities(
        self, text: str, context: Optional[ConversationContext] = None
    ) -> ExtractionResult:
        """
        Extract appointment entities from natural language text.

        Args:
            text: Input text from patient
            context: Optional conversation context for multi-turn extraction

        Returns:
            ExtractionResult with extracted entities and confidence scores
        """
        start_time = time_module.time()

        try:
            if not self.client:
                raise ValueError("OpenAI client not initialized")

            # Build context-aware prompt
            prompt = self._build_extraction_prompt(text, context)

            # Make API call with cost optimization
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Cost-efficient model
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=500,  # Limit tokens for cost control
                response_format={"type": "json_object"},
            )

            # Track costs
            self._update_cost_tracking(response.usage)

            # Parse response
            extraction_data = json.loads(response.choices[0].message.content)

            # Convert to structured result
            result = self._parse_extraction_response(extraction_data, text)
            result.processing_time_ms = (time_module.time() - start_time) * 1000

            # Log successful extraction
            audit_logger_instance.log_system_event(
                action="NLP_ENTITY_EXTRACTION",
                result="SUCCESS",
                additional_data={
                    "input_length": len(text),
                    "entities_found": len(
                        [
                            e
                            for e in [
                                result.patient_name,
                                result.appointment_datetime,
                                result.appointment_type,
                                result.reason,
                            ]
                            if e
                        ]
                    ),
                    "overall_confidence": result.overall_confidence,
                    "processing_time_ms": result.processing_time_ms,
                },
            )

            return result

        except Exception as e:
            processing_time = (time_module.time() - start_time) * 1000
            logger.error(f"Entity extraction failed: {e}")

            audit_logger_instance.log_system_event(
                action="NLP_ENTITY_EXTRACTION",
                result="FAILURE",
                additional_data={
                    "error": str(e),
                    "processing_time_ms": processing_time,
                },
            )

            # Return empty result with error info
            return ExtractionResult(input_text=text, processing_time_ms=processing_time)

    def _get_system_prompt(self) -> str:
        """Get system prompt for entity extraction."""
        return """You are a medical appointment scheduling assistant. Extract entities from patient requests.

IMPORTANT: Return ONLY valid JSON in this exact format:
{
  "patient_name": {"value": "John Doe", "confidence": 0.9, "first_name": "John", "last_name": "Doe"},
  "appointment_datetime": {"value": "2024-01-15T14:30:00", "confidence": 0.8, "is_relative": false, "original_format": "January 15th at 2:30pm"},
  "appointment_type": {"value": "checkup", "confidence": 0.7, "estimated_duration": 30},
  "reason": {"value": "annual physical", "confidence": 0.9, "medical_keywords": ["physical"], "urgency_indicators": []}
}

Rules:
- Set confidence 0.0-1.0 based on clarity
- Use null for missing entities
- Map appointment types to: checkup, follow_up, urgent, consultation, physical, wellness, unknown
- For dates: convert to ISO format, mark is_relative true for "tomorrow", "next week" etc.
- Identify medical keywords and urgency indicators
- Extract first/last name when possible"""

    def _build_extraction_prompt(
        self, text: str, context: Optional[ConversationContext] = None
    ) -> str:
        """Build context-aware extraction prompt."""
        prompt = f'Patient says: "{text}"\n\n'

        if context and context.accumulated_entities:
            prompt += "Previous context:\n"
            acc = context.accumulated_entities

            if acc.patient_name:
                prompt += f"- Patient name: {acc.patient_name.value}\n"
            if acc.appointment_datetime:
                prompt += f"- Date/time: {acc.appointment_datetime.original_format}\n"
            if acc.appointment_type:
                prompt += f"- Appointment type: {acc.appointment_type.value.value}\n"
            if acc.reason:
                prompt += f"- Reason: {acc.reason.value}\n"

            prompt += "\nUpdate or fill missing information from this new input.\n"

        prompt += "\nExtract appointment entities:"
        return prompt

    def _parse_extraction_response(
        self, data: Dict[str, Any], original_text: str
    ) -> ExtractionResult:
        """Parse OpenAI response into ExtractionResult."""
        result = ExtractionResult(input_text=original_text)

        # Parse patient name
        if data.get("patient_name"):
            name_data = data["patient_name"]
            result.patient_name = PatientName(
                value=name_data.get("value", ""),
                confidence=name_data.get("confidence", 0.0),
                raw_text=original_text,
                first_name=name_data.get("first_name"),
                last_name=name_data.get("last_name"),
            )

        # Parse appointment datetime
        if data.get("appointment_datetime"):
            dt_data = data["appointment_datetime"]
            dt_value = None
            if dt_data.get("value"):
                try:
                    dt_value = datetime.fromisoformat(
                        dt_data["value"].replace("Z", "+00:00")
                    )
                except:
                    pass

            result.appointment_datetime = AppointmentDateTime(
                value=dt_value,
                confidence=dt_data.get("confidence", 0.0),
                raw_text=original_text,
                is_relative=dt_data.get("is_relative", False),
                original_format=dt_data.get("original_format", ""),
            )

        # Parse appointment type
        if data.get("appointment_type"):
            type_data = data["appointment_type"]
            type_value = AppointmentType.UNKNOWN
            try:
                type_value = AppointmentType(type_data.get("value", "unknown"))
            except ValueError:
                type_value = AppointmentType.UNKNOWN

            result.appointment_type = AppointmentTypeEntity(
                value=type_value,
                confidence=type_data.get("confidence", 0.0),
                raw_text=original_text,
                estimated_duration=type_data.get("estimated_duration", 30),
            )

        # Parse reason
        if data.get("reason"):
            reason_data = data["reason"]
            result.reason = AppointmentReason(
                value=reason_data.get("value", ""),
                confidence=reason_data.get("confidence", 0.0),
                raw_text=original_text,
                medical_keywords=reason_data.get("medical_keywords", []),
                urgency_indicators=reason_data.get("urgency_indicators", []),
            )

        return result

    def _update_cost_tracking(self, usage):
        """Update cost tracking from OpenAI usage."""
        if hasattr(usage, "total_tokens"):
            self.cost_tracking["total_tokens"] += usage.total_tokens
            # GPT-3.5-turbo pricing: ~$0.0015 per 1K tokens
            cost_cents = int((usage.total_tokens / 1000) * 0.15)  # Convert to cents
            self.cost_tracking["monthly_cost_cents"] += cost_cents

        self.cost_tracking["total_requests"] += 1

    def get_cost_stats(self) -> Dict[str, Any]:
        """Get current cost tracking statistics."""
        return {
            **self.cost_tracking,
            "cost_dollars": self.cost_tracking["monthly_cost_cents"] / 100.0,
            "avg_tokens_per_request": (
                self.cost_tracking["total_tokens"]
                / max(self.cost_tracking["total_requests"], 1)
            ),
        }

    def enhance_with_medical_terminology(
        self, result: ExtractionResult
    ) -> ExtractionResult:
        """
        Enhance extraction result with medical terminology processing.

        Args:
            result: Initial extraction result

        Returns:
            Enhanced result with medical terminology analysis
        """
        # Enhance appointment type with fuzzy matching
        if result.appointment_type and result.appointment_type.confidence < 0.7:
            enhanced_type = self._fuzzy_match_appointment_type(result.input_text)
            if (
                enhanced_type
                and enhanced_type.confidence > result.appointment_type.confidence
            ):
                result.appointment_type = enhanced_type

        # Enhance reason with medical keyword detection
        if result.reason:
            medical_keywords = self._extract_medical_keywords(result.input_text)
            urgency_indicators = self._extract_urgency_indicators(result.input_text)

            result.reason.medical_keywords.extend(medical_keywords)
            result.reason.urgency_indicators.extend(urgency_indicators)

            # Boost confidence if medical terms found
            if medical_keywords or urgency_indicators:
                result.reason.confidence = min(1.0, result.reason.confidence + 0.1)

        return result

    def _fuzzy_match_appointment_type(
        self, text: str
    ) -> Optional[AppointmentTypeEntity]:
        """Fuzzy match appointment type from text using medical terminology."""
        text_lower = text.lower()
        best_match = None
        best_confidence = 0.0

        for apt_type, keywords in MEDICAL_TERMINOLOGY["appointment_types"].items():
            for keyword in keywords:
                if keyword in text_lower:
                    confidence = 0.8 if keyword == apt_type else 0.6
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = AppointmentType(apt_type)

        if best_match:
            duration_map = {
                AppointmentType.CHECKUP: 30,
                AppointmentType.PHYSICAL: 60,
                AppointmentType.CONSULTATION: 45,
                AppointmentType.FOLLOW_UP: 20,
                AppointmentType.URGENT: 15,
                AppointmentType.WELLNESS: 30,
            }

            return AppointmentTypeEntity(
                value=best_match,
                confidence=best_confidence,
                raw_text=text,
                estimated_duration=duration_map.get(best_match, 30),
            )

        return None

    def _extract_medical_keywords(self, text: str) -> List[str]:
        """Extract medical keywords from text."""
        text_lower = text.lower()
        found_keywords = []

        for keyword in MEDICAL_TERMINOLOGY["medical_keywords"]:
            if keyword in text_lower:
                found_keywords.append(keyword)

        return found_keywords

    def _extract_urgency_indicators(self, text: str) -> List[str]:
        """Extract urgency indicators from text."""
        text_lower = text.lower()
        found_indicators = []

        for indicator in MEDICAL_TERMINOLOGY["urgency_indicators"]:
            if indicator in text_lower:
                found_indicators.append(indicator)

        return found_indicators

    def validate_extraction(self, result: ExtractionResult) -> Tuple[bool, List[str]]:
        """
        Validate extraction result and provide validation feedback.

        Args:
            result: Extraction result to validate

        Returns:
            Tuple of (is_valid, validation_errors)
        """
        errors = []

        # Validate patient name
        if result.patient_name:
            if len(result.patient_name.value.strip()) < 2:
                errors.append("Patient name too short")

            if result.patient_name.confidence < 0.3:
                errors.append("Patient name confidence too low")

            # Check for reasonable name pattern
            if not re.match(r"^[a-zA-Z\s\'-]+$", result.patient_name.value):
                errors.append("Patient name contains invalid characters")

        # Validate appointment datetime
        if result.appointment_datetime and result.appointment_datetime.value:
            # Check if date is not in the past (with some tolerance)
            if result.appointment_datetime.value < datetime.now().replace(
                hour=0, minute=0, second=0
            ):
                errors.append("Appointment date cannot be in the past")

            # Check if date is not too far in future (6 months)
            six_months_future = datetime.now().replace(day=1) + timedelta(days=180)
            if result.appointment_datetime.value > six_months_future:
                errors.append("Appointment date too far in future")

        # Validate appointment type confidence
        if result.appointment_type and result.appointment_type.confidence < 0.4:
            errors.append("Appointment type confidence too low")

        # Validate reason if provided
        if result.reason:
            if len(result.reason.value.strip()) < 3:
                errors.append("Appointment reason too vague")

        # Check overall confidence
        if result.overall_confidence < 0.5:
            errors.append("Overall extraction confidence too low")

        return len(errors) == 0, errors

    def calculate_confidence_score(self, result: ExtractionResult) -> float:
        """
        Calculate overall confidence score with weighted factors.

        Args:
            result: Extraction result

        Returns:
            Weighted confidence score (0.0-1.0)
        """
        # Weights for different entities
        weights = {
            "patient_name": 0.3,  # Most important
            "appointment_datetime": 0.25,
            "appointment_type": 0.25,
            "reason": 0.2,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        entities = [
            ("patient_name", result.patient_name),
            ("appointment_datetime", result.appointment_datetime),
            ("appointment_type", result.appointment_type),
            ("reason", result.reason),
        ]

        for entity_name, entity in entities:
            if entity is not None:
                weighted_sum += entity.confidence * weights[entity_name]
                total_weight += weights[entity_name]

        if total_weight == 0:
            return 0.0

        base_confidence = weighted_sum / total_weight

        # Apply bonuses and penalties
        bonus = 0.0
        penalty = 0.0

        # Bonus for medical terminology
        if result.reason and (
            result.reason.medical_keywords or result.reason.urgency_indicators
        ):
            bonus += 0.1

        # Bonus for complete information
        complete_entities = sum(1 for _, entity in entities if entity is not None)
        if complete_entities >= 3:
            bonus += 0.05

        # Penalty for validation errors
        is_valid, errors = self.validate_extraction(result)
        if not is_valid:
            penalty += 0.1 * len(errors)

        final_confidence = max(0.0, min(1.0, base_confidence + bonus - penalty))
        return final_confidence

    def get_clarification_questions(self, result: ExtractionResult) -> List[str]:
        """
        Generate clarification questions for missing or low-confidence entities.

        Args:
            result: Extraction result

        Returns:
            List of clarification questions
        """
        questions = []

        # Check for missing patient name
        if not result.patient_name or result.patient_name.confidence < 0.7:
            questions.append("Could you please tell me your full name?")

        # Check for missing date/time
        if (
            not result.appointment_datetime
            or result.appointment_datetime.confidence < 0.7
        ):
            questions.append(
                "What date and time would you prefer for your appointment?"
            )

        # Check for missing appointment type
        if not result.appointment_type or result.appointment_type.confidence < 0.7:
            questions.append(
                "What type of appointment do you need? For example: checkup, follow-up, or consultation?"
            )

        # Check for missing reason
        if not result.reason or result.reason.confidence < 0.7:
            questions.append(
                "Could you briefly describe the reason for your appointment?"
            )

        return questions


# Global NLP processor instance
nlp_processor = NLPProcessor()
