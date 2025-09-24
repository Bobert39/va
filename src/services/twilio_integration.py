"""
Twilio Voice Integration Service

Handles Twilio Voice API integration for phone system connection,
webhook endpoints, and voice call management.
"""

import hashlib
import logging
from typing import Dict, Optional

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from src.audit import audit_logger_instance
from src.config import get_config

logger = logging.getLogger(__name__)


class TwilioIntegrationService:
    """
    Handles Twilio Voice API integration for phone system connection.

    Features:
    - Webhook endpoints for voice call handling
    - Phone number configuration management
    - Call session management
    - Audio streaming setup for real-time processing
    """

    def __init__(self):
        """Initialize Twilio integration service."""
        self.client: Optional[Client] = None
        self.account_sid: Optional[str] = None
        self.auth_token: Optional[str] = None
        self.phone_number: Optional[str] = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Twilio client with credentials from config."""
        try:
            self.account_sid = get_config("api_keys.twilio_account_sid")
            self.auth_token = get_config("api_keys.twilio_auth_token")

            if not self.account_sid or not self.auth_token:
                logger.warning("Twilio credentials not configured")
                return

            self.client = Client(self.account_sid, self.auth_token)
            logger.info("Twilio client initialized successfully")

            audit_logger_instance.log_system_event(
                action="TWILIO_CLIENT_INITIALIZED", result="SUCCESS"
            )

        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")
            audit_logger_instance.log_system_event(
                action="TWILIO_CLIENT_INITIALIZATION",
                result="FAILURE",
                additional_data={"error": str(e)},
            )

    def configure_phone_number(self, phone_number: str, webhook_url: str) -> bool:
        """
        Configure Twilio phone number with webhook URL.

        Args:
            phone_number: Twilio phone number to configure
            webhook_url: URL for voice webhook callbacks

        Returns:
            True if configuration successful
        """
        try:
            if not self.client:
                raise ValueError("Twilio client not initialized")

            # Update phone number webhook configuration
            phone_numbers = self.client.incoming_phone_numbers.list(
                phone_number=phone_number
            )

            if not phone_numbers:
                raise ValueError(f"Phone number {phone_number} not found in account")

            phone_number_sid = phone_numbers[0].sid
            self.client.incoming_phone_numbers(phone_number_sid).update(
                voice_url=webhook_url, voice_method="POST"
            )

            self.phone_number = phone_number
            logger.info(
                f"Phone number {phone_number} configured with webhook {webhook_url}"
            )

            audit_logger_instance.log_configuration_change(
                action="PHONE_NUMBER_CONFIGURED",
                result="SUCCESS",
                additional_data={
                    "phone_number": self._hash_phone_number(phone_number),
                    "webhook_url": webhook_url,
                },
            )

            return True

        except Exception as e:
            logger.error(f"Failed to configure phone number: {e}")
            audit_logger_instance.log_configuration_change(
                action="PHONE_NUMBER_CONFIGURATION",
                result="FAILURE",
                additional_data={"error": str(e)},
            )
            return False

    def _hash_phone_number(self, phone_number: str) -> str:
        """Hash phone number for privacy-compliant logging."""
        return hashlib.sha256(phone_number.encode()).hexdigest()[:16]

    def handle_incoming_call(self, call_sid: str, from_number: str) -> VoiceResponse:
        """
        Handle incoming voice call and set up audio streaming.

        Args:
            call_sid: Twilio call SID
            from_number: Caller's phone number

        Returns:
            TwiML response for call handling
        """
        try:
            # Create TwiML response
            response = VoiceResponse()

            # Log call initiation
            phone_hash = self._hash_phone_number(from_number)
            audit_logger_instance.log_voice_call(
                action="INCOMING_CALL_RECEIVED",
                call_id=call_sid,
                phone_hash=phone_hash,
                result="SUCCESS",
            )

            # Welcome message
            response.say("Hello! Please state your appointment request after the tone.")

            # Set up audio streaming for real-time processing
            # This will stream audio to our webhook for processing
            connect = response.connect()
            connect.stream(
                url=f"wss://your-domain.com/voice/stream/{call_sid}", track="inbound"
            )

            logger.info(f"Incoming call handled: {call_sid}")

            return response

        except Exception as e:
            logger.error(f"Failed to handle incoming call: {e}")
            audit_logger_instance.log_voice_call(
                action="INCOMING_CALL_HANDLING",
                call_id=call_sid,
                phone_hash=self._hash_phone_number(from_number),
                result="FAILURE",
            )

            # Return error response
            response = VoiceResponse()
            response.say(
                "Sorry, we're experiencing technical difficulties. "
                "Please try again later."
            )
            response.hangup()
            return response

    def create_conference_call(self, call_sid: str) -> Dict[str, str]:
        """
        Create a conference for call recording and processing.

        Args:
            call_sid: Twilio call SID

        Returns:
            Conference details
        """
        try:
            conference_name = f"voice_processing_{call_sid}"

            response = VoiceResponse()
            response.say("Connecting you to our voice assistant.")

            dial = response.dial()
            dial.conference(
                conference_name,
                start_conference_on_enter=True,
                end_conference_on_exit=True,
                record="record-from-start",
            )

            return {"conference_name": conference_name, "twiml": str(response)}

        except Exception as e:
            logger.error(f"Failed to create conference call: {e}")
            return {}

    def end_call(self, call_sid: str, reason: str = "completed") -> bool:
        """
        End an active call.

        Args:
            call_sid: Twilio call SID
            reason: Reason for ending call

        Returns:
            True if call ended successfully
        """
        try:
            if not self.client:
                raise ValueError("Twilio client not initialized")

            # Update call status to completed
            self.client.calls(call_sid).update(status="completed")

            audit_logger_instance.log_voice_call(
                action="CALL_ENDED",
                call_id=call_sid,
                phone_hash="unknown",
                result="SUCCESS",
                additional_data={"reason": reason},
            )

            logger.info(f"Call {call_sid} ended: {reason}")
            return True

        except Exception as e:
            logger.error(f"Failed to end call {call_sid}: {e}")
            audit_logger_instance.log_voice_call(
                action="CALL_END_ATTEMPT",
                call_id=call_sid,
                phone_hash="unknown",
                result="FAILURE",
            )
            return False

    def get_call_details(self, call_sid: str) -> Optional[Dict]:
        """
        Get details for a specific call.

        Args:
            call_sid: Twilio call SID

        Returns:
            Call details dictionary or None if not found
        """
        try:
            if not self.client:
                raise ValueError("Twilio client not initialized")

            call = self.client.calls(call_sid).fetch()

            return {
                "sid": call.sid,
                "status": call.status,
                "duration": call.duration,
                "start_time": call.start_time,
                "end_time": call.end_time,
                "direction": call.direction,
                "from_number_hash": self._hash_phone_number(call.from_),
                "to_number_hash": self._hash_phone_number(call.to),
            }

        except Exception as e:
            logger.error(f"Failed to get call details for {call_sid}: {e}")
            return None

    def test_connection(self) -> bool:
        """
        Test Twilio API connection.

        Returns:
            True if connection successful
        """
        try:
            if not self.client:
                return False

            # Test connection by fetching account details
            account = self.client.api.accounts(self.account_sid).fetch()

            audit_logger_instance.log_system_event(
                action="TWILIO_CONNECTION_TEST",
                result="SUCCESS",
                additional_data={"account_sid": account.sid},
            )

            logger.info("Twilio connection test successful")
            return True

        except Exception as e:
            logger.error(f"Twilio connection test failed: {e}")
            audit_logger_instance.log_system_event(
                action="TWILIO_CONNECTION_TEST",
                result="FAILURE",
                additional_data={"error": str(e)},
            )
            return False


# Global service instance
twilio_service = TwilioIntegrationService()
