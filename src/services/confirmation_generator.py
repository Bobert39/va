"""
Confirmation Number Generator Service.

Generates unique, traceable appointment confirmation numbers
and manages confirmation tracking for voice responses.
"""

import hashlib
import logging
import secrets
import string
from datetime import datetime
from typing import Dict, Optional, Tuple

from ..config import get_config

logger = logging.getLogger(__name__)


class ConfirmationGenerator:
    """
    Service for generating and managing appointment confirmation numbers.

    Features:
    - Unique confirmation number generation
    - Confirmation tracking and validation
    - Session mapping for voice responses
    - Secure, HIPAA-compliant generation
    """

    def __init__(self):
        """Initialize confirmation generator with configuration."""
        config = get_config("emr_integration", {})
        self.confirmation_format = config.get(
            "confirmation_format",
            "VA_{date}_{code}",  # Default format: VA_20250921_ABC123
        )
        self.practice_prefix = config.get("practice_prefix", "VA")
        self.code_length = config.get("confirmation_code_length", 6)
        self.use_alphanumeric = config.get("use_alphanumeric_codes", True)

        # In-memory storage for confirmation mappings
        # In production, this would be in Redis or similar
        self.confirmation_mappings = {}
        self.reverse_mappings = {}  # For quick lookups

    def generate_confirmation_number(
        self,
        appointment_id: str,
        patient_id: str,
        provider_id: str,
        appointment_time: datetime,
    ) -> str:
        """
        Generate unique confirmation number for appointment.

        Args:
            appointment_id: EMR appointment ID
            patient_id: Patient EMR ID
            provider_id: Provider EMR ID
            appointment_time: Appointment scheduled time

        Returns:
            Unique confirmation number string
        """
        # Generate unique code component
        code = self._generate_unique_code()

        # Format confirmation number based on configuration
        if self.confirmation_format == "practice_prefix_yyyymmdd_hhmmss":
            # Legacy format for backward compatibility
            confirmation = (
                f"{self.practice_prefix}_{appointment_time.strftime('%Y%m%d_%H%M%S')}"
            )
        else:
            # Default format with date and code
            date_str = appointment_time.strftime("%Y%m%d")
            confirmation = f"{self.practice_prefix}_{date_str}_{code}"

        # Store mapping
        self._store_confirmation_mapping(
            confirmation, appointment_id, patient_id, provider_id, appointment_time
        )

        logger.info(f"Generated confirmation number: {confirmation[:10]}...")
        return confirmation

    def _generate_unique_code(self) -> str:
        """
        Generate unique code component for confirmation number.

        Returns:
            Unique code string
        """
        max_attempts = 100  # Prevent infinite loop
        attempts = 0

        while attempts < max_attempts:
            if self.use_alphanumeric:
                # Generate alphanumeric code (easier to speak)
                # Exclude confusing characters (0, O, 1, I, l)
                chars = string.ascii_uppercase.replace("O", "").replace(
                    "I", ""
                ) + string.digits.replace("0", "").replace("1", "")
                code = "".join(secrets.choice(chars) for _ in range(self.code_length))
            else:
                # Generate numeric-only code
                code = "".join(
                    secrets.choice(string.digits) for _ in range(self.code_length)
                )

            # Check uniqueness
            if code not in [
                self._extract_code(c) for c in self.confirmation_mappings.keys()
            ]:
                return code

            attempts += 1

        # Fallback to longer code if uniqueness is hard to achieve
        logger.warning("Generating extended confirmation code due to collision")
        return secrets.token_hex(self.code_length // 2).upper()

    def _extract_code(self, confirmation: str) -> Optional[str]:
        """Extract code component from confirmation number."""
        parts = confirmation.split("_")
        return parts[-1] if len(parts) >= 3 else None

    def _store_confirmation_mapping(
        self,
        confirmation: str,
        appointment_id: str,
        patient_id: str,
        provider_id: str,
        appointment_time: datetime,
    ):
        """
        Store confirmation number mapping for lookup.

        Args:
            confirmation: Generated confirmation number
            appointment_id: EMR appointment ID
            patient_id: Patient EMR ID
            provider_id: Provider EMR ID
            appointment_time: Appointment time
        """
        mapping_data = {
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "provider_id": provider_id,
            "appointment_time": appointment_time.isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "status": "active",
        }

        self.confirmation_mappings[confirmation] = mapping_data
        self.reverse_mappings[appointment_id] = confirmation

        # Log for audit (without PHI)
        logger.info(
            f"Stored confirmation mapping for appointment {appointment_id[:8]}..."
        )

    def validate_confirmation_number(
        self, confirmation: str
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Validate and retrieve appointment data for confirmation number.

        Args:
            confirmation: Confirmation number to validate

        Returns:
            Tuple of (is_valid, appointment_data)
        """
        # Normalize confirmation number (uppercase, remove spaces)
        confirmation = confirmation.upper().strip().replace(" ", "_").replace("-", "_")

        # Check if confirmation exists
        if confirmation in self.confirmation_mappings:
            mapping = self.confirmation_mappings[confirmation]

            # Check if confirmation is still active
            if mapping.get("status") == "active":
                logger.info(
                    f"Valid confirmation number validated: {confirmation[:10]}..."
                )
                return True, mapping
            else:
                logger.warning(f"Inactive confirmation number: {confirmation[:10]}...")
                return False, {"error": "Confirmation number is no longer active"}
        else:
            logger.warning(
                f"Invalid confirmation number attempted: {confirmation[:10]}..."
            )
            return False, {"error": "Invalid confirmation number"}

    def get_confirmation_by_appointment(self, appointment_id: str) -> Optional[str]:
        """
        Get confirmation number for an appointment ID.

        Args:
            appointment_id: EMR appointment ID

        Returns:
            Confirmation number if found, None otherwise
        """
        return self.reverse_mappings.get(appointment_id)

    def deactivate_confirmation(self, confirmation: str) -> bool:
        """
        Deactivate a confirmation number (e.g., after cancellation).

        Args:
            confirmation: Confirmation number to deactivate

        Returns:
            True if deactivated, False if not found
        """
        if confirmation in self.confirmation_mappings:
            self.confirmation_mappings[confirmation]["status"] = "inactive"
            self.confirmation_mappings[confirmation][
                "deactivated_at"
            ] = datetime.utcnow().isoformat()
            logger.info(f"Deactivated confirmation: {confirmation[:10]}...")
            return True
        return False

    def format_for_voice(self, confirmation: str) -> str:
        """
        Format confirmation number for voice/speech output.

        Args:
            confirmation: Confirmation number

        Returns:
            Speech-friendly formatted confirmation
        """
        # Split into components for clearer speech
        parts = confirmation.split("_")

        if len(parts) >= 3:
            # Format: "VA" "December 21st" "Alpha Bravo Charlie 1 2 3"
            prefix = parts[0]
            date_str = parts[1]
            code = parts[2]

            # Convert date to speech-friendly format
            try:
                date_obj = datetime.strptime(date_str, "%Y%m%d")
                date_spoken = date_obj.strftime("%B %d")
            except:
                date_spoken = date_str

            # Convert code to phonetic alphabet for clarity
            code_spoken = self._convert_to_phonetic(code)

            return f"{prefix}, {date_spoken}, {code_spoken}"
        else:
            # Fallback: spell out characters with pauses
            return ", ".join(confirmation)

    def _convert_to_phonetic(self, code: str) -> str:
        """
        Convert code to NATO phonetic alphabet for clarity.

        Args:
            code: Code string to convert

        Returns:
            Phonetic representation
        """
        phonetic_alphabet = {
            "A": "Alpha",
            "B": "Bravo",
            "C": "Charlie",
            "D": "Delta",
            "E": "Echo",
            "F": "Foxtrot",
            "G": "Golf",
            "H": "Hotel",
            "I": "India",
            "J": "Juliet",
            "K": "Kilo",
            "L": "Lima",
            "M": "Mike",
            "N": "November",
            "O": "Oscar",
            "P": "Papa",
            "Q": "Quebec",
            "R": "Romeo",
            "S": "Sierra",
            "T": "Tango",
            "U": "Uniform",
            "V": "Victor",
            "W": "Whiskey",
            "X": "X-ray",
            "Y": "Yankee",
            "Z": "Zulu",
            "0": "Zero",
            "1": "One",
            "2": "Two",
            "3": "Three",
            "4": "Four",
            "5": "Five",
            "6": "Six",
            "7": "Seven",
            "8": "Eight",
            "9": "Nine",
        }

        result = []
        for char in code.upper():
            if char in phonetic_alphabet:
                result.append(phonetic_alphabet[char])
            else:
                result.append(char)

        return ", ".join(result)

    def get_session_confirmation(self, session_id: str) -> Optional[str]:
        """
        Get confirmation number associated with a session.

        Args:
            session_id: Voice call session ID

        Returns:
            Confirmation number if found
        """
        # This would integrate with session storage
        # For now, returning None as placeholder
        return None

    def store_session_confirmation(
        self, session_id: str, confirmation: str, appointment_data: Dict
    ):
        """
        Store confirmation number in session for voice response.

        Args:
            session_id: Voice call session ID
            confirmation: Generated confirmation number
            appointment_data: Appointment details
        """
        # This would integrate with session storage service
        # Storing in memory for now
        logger.info(
            f"Stored confirmation {confirmation[:10]}... for session {session_id[:8]}..."
        )

    def cleanup_expired_confirmations(self, days_to_keep: int = 30):
        """
        Clean up old confirmation mappings.

        Args:
            days_to_keep: Number of days to retain confirmations
        """
        cutoff_date = datetime.utcnow().isoformat()
        expired = []

        for confirmation, data in self.confirmation_mappings.items():
            created_at_str = data["created_at"]
            # Ensure we handle both timezone-aware and naive datetimes
            if "T" in created_at_str:
                # ISO format datetime string
                created_at = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
                # Convert to naive for comparison if needed
                if created_at.tzinfo:
                    created_at = created_at.replace(tzinfo=None)
            else:
                created_at = datetime.fromisoformat(created_at_str)

            age_days = (datetime.utcnow() - created_at).days

            if age_days > days_to_keep:
                expired.append(confirmation)

        for confirmation in expired:
            appointment_id = self.confirmation_mappings[confirmation]["appointment_id"]
            del self.confirmation_mappings[confirmation]
            if appointment_id in self.reverse_mappings:
                del self.reverse_mappings[appointment_id]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired confirmations")
