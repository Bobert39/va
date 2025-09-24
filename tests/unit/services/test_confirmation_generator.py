"""
Unit tests for ConfirmationGenerator service.

Tests confirmation number generation, validation, formatting,
and session management for voice-scheduled appointments.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.services.confirmation_generator import ConfirmationGenerator


class TestConfirmationGenerator:
    """Test suite for ConfirmationGenerator."""

    @pytest.fixture
    def confirmation_generator(self):
        """Create ConfirmationGenerator instance."""
        with patch("src.services.confirmation_generator.get_config") as mock_config:
            mock_config.return_value = {
                "confirmation_format": "VA_{date}_{code}",
                "practice_prefix": "VA",
                "confirmation_code_length": 6,
                "use_alphanumeric_codes": True,
            }
            return ConfirmationGenerator()

    @pytest.fixture
    def appointment_data(self):
        """Sample appointment data for testing."""
        return {
            "appointment_id": "appt123",
            "patient_id": "patient456",
            "provider_id": "provider789",
            "appointment_time": datetime(2025, 1, 20, 10, 30, tzinfo=timezone.utc),
        }

    def test_generate_confirmation_number(
        self, confirmation_generator, appointment_data
    ):
        """Test confirmation number generation."""
        confirmation = confirmation_generator.generate_confirmation_number(
            appointment_id=appointment_data["appointment_id"],
            patient_id=appointment_data["patient_id"],
            provider_id=appointment_data["provider_id"],
            appointment_time=appointment_data["appointment_time"],
        )

        # Check format
        assert confirmation.startswith("VA_")
        assert "20250120" in confirmation  # Date component
        parts = confirmation.split("_")
        assert len(parts) == 3
        assert len(parts[2]) == 6  # Code length

        # Check storage
        assert confirmation in confirmation_generator.confirmation_mappings
        assert (
            appointment_data["appointment_id"]
            in confirmation_generator.reverse_mappings
        )

    def test_generate_unique_code_alphanumeric(self, confirmation_generator):
        """Test unique alphanumeric code generation."""
        code = confirmation_generator._generate_unique_code()

        assert len(code) == 6
        # Check no confusing characters
        assert "O" not in code
        assert "I" not in code
        assert "0" not in code
        assert "1" not in code

    def test_generate_unique_code_numeric_only(self, confirmation_generator):
        """Test numeric-only code generation."""
        confirmation_generator.use_alphanumeric = False
        code = confirmation_generator._generate_unique_code()

        assert len(code) == 6
        assert code.isdigit()

    def test_generate_unique_code_collision_handling(self, confirmation_generator):
        """Test unique code generation with collision handling."""
        # Pre-populate with codes to force collision
        existing_codes = ["ABC123", "DEF456", "GHJ789"]
        for i, code in enumerate(existing_codes):
            confirmation = f"VA_20250120_{code}"
            confirmation_generator.confirmation_mappings[confirmation] = {"test": i}

        # Generate new code - should be different from existing
        new_code = confirmation_generator._generate_unique_code()
        assert new_code not in existing_codes

    def test_extract_code(self, confirmation_generator):
        """Test code extraction from confirmation number."""
        confirmation = "VA_20250120_ABC123"
        code = confirmation_generator._extract_code(confirmation)
        assert code == "ABC123"

        # Test invalid format
        invalid = "INVALID"
        code = confirmation_generator._extract_code(invalid)
        assert code is None

    def test_validate_confirmation_number_valid(
        self, confirmation_generator, appointment_data
    ):
        """Test validation of valid confirmation number."""
        # Generate confirmation
        confirmation = confirmation_generator.generate_confirmation_number(
            **appointment_data
        )

        # Validate
        is_valid, data = confirmation_generator.validate_confirmation_number(
            confirmation
        )

        assert is_valid is True
        assert data["appointment_id"] == "appt123"
        assert data["patient_id"] == "patient456"
        assert data["status"] == "active"

    def test_validate_confirmation_number_invalid(self, confirmation_generator):
        """Test validation of invalid confirmation number."""
        is_valid, data = confirmation_generator.validate_confirmation_number(
            "INVALID123"
        )

        assert is_valid is False
        assert "error" in data
        assert "Invalid confirmation number" in data["error"]

    def test_validate_confirmation_number_inactive(
        self, confirmation_generator, appointment_data
    ):
        """Test validation of inactive confirmation number."""
        # Generate and deactivate
        confirmation = confirmation_generator.generate_confirmation_number(
            **appointment_data
        )
        confirmation_generator.deactivate_confirmation(confirmation)

        # Validate
        is_valid, data = confirmation_generator.validate_confirmation_number(
            confirmation
        )

        assert is_valid is False
        assert "no longer active" in data["error"]

    def test_validate_confirmation_number_normalization(
        self, confirmation_generator, appointment_data
    ):
        """Test confirmation number normalization during validation."""
        # Generate confirmation
        confirmation = confirmation_generator.generate_confirmation_number(
            **appointment_data
        )

        # Test with spaces and lowercase
        test_variations = [
            confirmation.lower(),
            confirmation.replace("_", " "),
            confirmation.replace("_", "-"),
            f"  {confirmation}  ",  # With whitespace
        ]

        for variation in test_variations:
            is_valid, data = confirmation_generator.validate_confirmation_number(
                variation
            )
            assert is_valid is True

    def test_get_confirmation_by_appointment(
        self, confirmation_generator, appointment_data
    ):
        """Test retrieving confirmation by appointment ID."""
        # Generate confirmation
        confirmation = confirmation_generator.generate_confirmation_number(
            **appointment_data
        )

        # Retrieve by appointment ID
        retrieved = confirmation_generator.get_confirmation_by_appointment("appt123")
        assert retrieved == confirmation

        # Test non-existent appointment
        missing = confirmation_generator.get_confirmation_by_appointment("missing")
        assert missing is None

    def test_deactivate_confirmation(self, confirmation_generator, appointment_data):
        """Test confirmation deactivation."""
        # Generate confirmation
        confirmation = confirmation_generator.generate_confirmation_number(
            **appointment_data
        )

        # Deactivate
        result = confirmation_generator.deactivate_confirmation(confirmation)
        assert result is True

        # Check status
        mapping = confirmation_generator.confirmation_mappings[confirmation]
        assert mapping["status"] == "inactive"
        assert "deactivated_at" in mapping

        # Deactivate non-existent
        result = confirmation_generator.deactivate_confirmation("INVALID")
        assert result is False

    def test_format_for_voice_standard(self, confirmation_generator):
        """Test formatting confirmation for voice output."""
        confirmation = "VA_20250120_ABC123"
        spoken = confirmation_generator.format_for_voice(confirmation)

        assert "VA" in spoken
        assert "January 20" in spoken
        assert "Alpha" in spoken  # NATO phonetic
        assert "Bravo" in spoken
        assert "Charlie" in spoken

    def test_format_for_voice_fallback(self, confirmation_generator):
        """Test voice formatting fallback for non-standard format."""
        confirmation = "NONSTANDARD"
        spoken = confirmation_generator.format_for_voice(confirmation)

        # Should spell out characters
        expected = ", ".join(confirmation)
        assert spoken == expected

    def test_convert_to_phonetic(self, confirmation_generator):
        """Test NATO phonetic alphabet conversion."""
        code = "AB12Z"
        phonetic = confirmation_generator._convert_to_phonetic(code)

        assert "Alpha" in phonetic
        assert "Bravo" in phonetic
        assert "One" in phonetic
        assert "Two" in phonetic
        assert "Zulu" in phonetic

    def test_convert_to_phonetic_special_chars(self, confirmation_generator):
        """Test phonetic conversion with special characters."""
        code = "A-B_C"
        phonetic = confirmation_generator._convert_to_phonetic(code)

        assert "Alpha" in phonetic
        assert "Bravo" in phonetic
        assert "Charlie" in phonetic
        assert "-" in phonetic  # Special chars preserved
        assert "_" in phonetic

    def test_store_session_confirmation(self, confirmation_generator):
        """Test storing confirmation in session."""
        session_id = "session123"
        confirmation = "VA_20250120_ABC123"
        appointment_data = {"test": "data"}

        # Should not raise exception
        confirmation_generator.store_session_confirmation(
            session_id, confirmation, appointment_data
        )

    def test_get_session_confirmation(self, confirmation_generator):
        """Test retrieving session confirmation (placeholder)."""
        result = confirmation_generator.get_session_confirmation("session123")
        assert result is None  # Placeholder implementation

    def test_cleanup_expired_confirmations(
        self, confirmation_generator, appointment_data
    ):
        """Test cleanup of expired confirmations."""
        # Create old confirmation
        old_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        old_confirmation = confirmation_generator.generate_confirmation_number(
            appointment_id="old123",
            patient_id="patient_old",
            provider_id="provider_old",
            appointment_time=old_time,
        )

        # Manually set created_at to old date
        confirmation_generator.confirmation_mappings[old_confirmation][
            "created_at"
        ] = datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat()

        # Create recent confirmation
        recent_confirmation = confirmation_generator.generate_confirmation_number(
            **appointment_data
        )

        # Run cleanup
        confirmation_generator.cleanup_expired_confirmations(days_to_keep=30)

        # Old should be removed, recent should remain
        assert old_confirmation not in confirmation_generator.confirmation_mappings
        assert recent_confirmation in confirmation_generator.confirmation_mappings
        assert "old123" not in confirmation_generator.reverse_mappings

    def test_legacy_format_support(self):
        """Test legacy confirmation format support."""
        with patch("src.services.confirmation_generator.get_config") as mock_config:
            mock_config.return_value = {
                "confirmation_format": "practice_prefix_yyyymmdd_hhmmss",
                "practice_prefix": "CLINIC",
            }
            generator = ConfirmationGenerator()

            confirmation = generator.generate_confirmation_number(
                appointment_id="test123",
                patient_id="patient456",
                provider_id="provider789",
                appointment_time=datetime(2025, 1, 20, 14, 30, 15, tzinfo=timezone.utc),
            )

            assert confirmation == "CLINIC_20250120_143015"
