"""
Audit Logging Module

HIPAA-compliant audit logging system for the Voice AI Platform.
Ensures secure logging with no PHI exposure and proper log rotation.
"""

import hashlib
import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Configure audit logger
audit_logger = logging.getLogger("audit")


class HIPAACompliantFormatter(logging.Formatter):
    """
    Custom formatter that ensures no PHI is logged and adds
    proper audit trail formatting.
    """

    def __init__(self):
        super().__init__()

    def format(self, record):
        """Format log record with HIPAA compliance."""
        # Ensure timestamp is in UTC
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc)

        # Create audit log entry
        audit_entry = {
            "timestamp": timestamp.isoformat(),
            "level": record.levelname,
            "event_type": getattr(record, "event_type", "SYSTEM"),
            "user_id": getattr(record, "user_id", "SYSTEM"),
            "session_id": getattr(record, "session_id", None),
            "action": getattr(record, "action", record.getMessage()),
            "resource": getattr(record, "resource", None),
            "result": getattr(record, "result", "SUCCESS"),
            "client_ip_hash": getattr(record, "client_ip_hash", None),
            "user_agent_hash": getattr(record, "user_agent_hash", None),
            "additional_data": getattr(record, "additional_data", {}),
        }

        # Remove None values to keep logs clean
        audit_entry = {k: v for k, v in audit_entry.items() if v is not None}

        return json.dumps(audit_entry)


class AuditLogger:
    """
    HIPAA-compliant audit logging system.

    Features:
    - Automatic log rotation
    - PHI-safe logging (hashes sensitive data)
    - Structured JSON format
    - Configurable retention
    """

    def __init__(
        self,
        log_file: str = "audit.log",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ):
        """
        Initialize audit logger.

        Args:
            log_file: Path to audit log file
            max_bytes: Maximum log file size before rotation (default: 10MB)
            backup_count: Number of backup files to keep
        """
        self.log_file = Path(log_file)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._setup_logger()

    def _setup_logger(self):
        """Set up the audit logger with rotation."""
        # Ensure log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Clear any existing handlers
        audit_logger.handlers.clear()

        # Set up rotating file handler
        handler = logging.handlers.RotatingFileHandler(
            filename=self.log_file,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )

        # Set formatter
        handler.setFormatter(HIPAACompliantFormatter())

        # Configure logger
        audit_logger.addHandler(handler)
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False

    def _hash_sensitive_data(self, data: Optional[str]) -> Optional[str]:
        """Hash sensitive data for audit logging."""
        if not data:
            return None
        return hashlib.sha256(data.encode()).hexdigest()[
            :16
        ]  # First 16 chars for readability

    def log_event(
        self,
        event_type: str,
        action: str,
        user_id: str = "SYSTEM",
        session_id: Optional[str] = None,
        resource: Optional[str] = None,
        result: str = "SUCCESS",
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Log an audit event.

        Args:
            event_type: Type of event (e.g., 'LOGIN', 'DATA_ACCESS', 'CONFIGURATION')
            action: Description of the action performed
            user_id: User identifier (hashed if sensitive)
            session_id: Session identifier
            resource: Resource being accessed
            result: Result of the action ('SUCCESS', 'FAILURE', 'ERROR')
            client_ip: Client IP address (will be hashed)
            user_agent: User agent string (will be hashed)
            additional_data: Additional non-sensitive data
        """
        # Create log record with extra fields
        extra = {
            "event_type": event_type,
            "user_id": user_id,
            "session_id": session_id,
            "action": action,
            "resource": resource,
            "result": result,
            "client_ip_hash": self._hash_sensitive_data(client_ip),
            "user_agent_hash": self._hash_sensitive_data(user_agent),
            "additional_data": additional_data or {},
        }

        audit_logger.info(action, extra=extra)

    def log_system_event(
        self,
        action: str,
        result: str = "SUCCESS",
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """Log a system event."""
        self.log_event(
            event_type="SYSTEM",
            action=action,
            result=result,
            additional_data=additional_data,
        )

    def log_configuration_change(
        self,
        action: str,
        user_id: str = "SYSTEM",
        result: str = "SUCCESS",
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """Log a configuration change."""
        self.log_event(
            event_type="CONFIGURATION",
            action=action,
            user_id=user_id,
            result=result,
            additional_data=additional_data,
        )

    def log_data_access(
        self,
        resource: str,
        action: str,
        user_id: str,
        session_id: Optional[str] = None,
        result: str = "SUCCESS",
    ):
        """Log data access (for future EMR integration)."""
        self.log_event(
            event_type="DATA_ACCESS",
            action=action,
            user_id=user_id,
            session_id=session_id,
            resource=resource,
            result=result,
        )

    def log_authentication(
        self,
        action: str,
        user_id: str,
        client_ip: Optional[str] = None,
        result: str = "SUCCESS",
    ):
        """Log authentication events."""
        self.log_event(
            event_type="AUTHENTICATION",
            action=action,
            user_id=user_id,
            client_ip=client_ip,
            result=result,
        )

    def log_voice_call(
        self,
        action: str,
        call_id: str,
        phone_hash: str,
        result: str = "SUCCESS",
        duration: Optional[int] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ):
        """Log voice call events with HIPAA-compliant data handling."""
        data = additional_data or {}
        if duration is not None:
            data["duration_seconds"] = duration

        self.log_event(
            event_type="VOICE_CALL",
            action=action,
            session_id=call_id,
            user_id=phone_hash,  # Phone number hash as user identifier
            result=result,
            additional_data=data,
        )

    def log_transcription_event(
        self,
        call_id: str,
        phone_hash: str,
        transcription_length: int,
        confidence: Optional[float] = None,
        result: str = "SUCCESS",
        error_details: Optional[str] = None,
    ):
        """Log speech-to-text transcription events with quality metrics."""
        additional_data = {
            "transcription_length": transcription_length,
            "confidence_score": confidence,
        }
        if error_details:
            additional_data["error_details"] = error_details

        self.log_event(
            event_type="VOICE_TRANSCRIPTION",
            action="AUDIO_TRANSCRIBED",
            session_id=call_id,
            user_id=phone_hash,
            result=result,
            additional_data=additional_data,
        )

    def log_api_usage_event(
        self,
        service: str,
        operation: str,
        cost_cents: int,
        usage_amount: float,
        usage_unit: str,
        result: str = "SUCCESS",
        session_id: Optional[str] = None,
    ):
        """Log API usage for cost tracking and monitoring."""
        additional_data = {
            "service": service,
            "operation": operation,
            "cost_cents": cost_cents,
            "usage_amount": usage_amount,
            "usage_unit": usage_unit,
        }

        self.log_event(
            event_type="API_USAGE",
            action=f"{service.upper()}_{operation.upper()}",
            session_id=session_id,
            user_id="SYSTEM",
            result=result,
            additional_data=additional_data,
        )

    def log_appointment_event(
        self,
        event_type: str,
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        result: str = "SUCCESS",
    ):
        """
        Log appointment-related events with HIPAA compliance.

        Args:
            event_type: Type of appointment event
            session_id: Voice call session ID
            details: Event details (PHI will be anonymized)
            result: Result of the operation
        """
        # Anonymize any PHI in details
        safe_details = {}
        if details:
            for key, value in details.items():
                if key in ["patient_id", "provider_id", "appointment_id"]:
                    # Hash sensitive IDs
                    safe_details[f"{key}_hash"] = self._hash_sensitive_data(str(value))
                elif key in ["error", "message", "status", "attempt", "retry_count"]:
                    # Keep non-sensitive data
                    safe_details[key] = value
                elif key == "start_time":
                    # Keep appointment time (not PHI by itself)
                    safe_details["appointment_time"] = value
                else:
                    # Include other non-sensitive data
                    if not any(
                        sensitive in str(key).lower()
                        for sensitive in ["name", "dob", "ssn", "mrn"]
                    ):
                        safe_details[key] = value

        self.log_event(
            event_type="APPOINTMENT",
            action=event_type,
            session_id=session_id,
            user_id="VOICE_SYSTEM",
            result=result,
            additional_data=safe_details,
        )

    def log_appointment_creation(
        self,
        appointment_id: str,
        patient_id: str,
        provider_id: str,
        appointment_time: str,
        session_id: Optional[str] = None,
        confirmation_number: Optional[str] = None,
        result: str = "SUCCESS",
    ):
        """Log successful appointment creation."""
        details = {
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "provider_id": provider_id,
            "start_time": appointment_time,
        }

        if confirmation_number:
            details["confirmation"] = (
                confirmation_number[:10] + "..."
            )  # Partial confirmation for audit

        self.log_appointment_event(
            event_type="appointment_created",
            session_id=session_id,
            details=details,
            result=result,
        )

    def log_appointment_retry(
        self,
        patient_id: str,
        provider_id: str,
        attempt: int,
        error: str,
        session_id: Optional[str] = None,
    ):
        """Log appointment creation retry attempt."""
        self.log_appointment_event(
            event_type="appointment_creation_retry",
            session_id=session_id,
            details={
                "patient_id": patient_id,
                "provider_id": provider_id,
                "attempt": attempt,
                "error": error,
            },
            result="RETRY",
        )

    def log_appointment_failure(
        self,
        patient_id: str,
        provider_id: str,
        error: str,
        retry_count: int,
        session_id: Optional[str] = None,
    ):
        """Log appointment creation failure."""
        self.log_appointment_event(
            event_type="appointment_creation_failed",
            session_id=session_id,
            details={
                "patient_id": patient_id,
                "provider_id": provider_id,
                "error": error,
                "retry_count": retry_count,
            },
            result="FAILURE",
        )

    def log_dashboard_access(self, user_id: str, action: str):
        """
        Log dashboard access event.

        Args:
            user_id: User accessing dashboard
            action: Type of dashboard access
        """
        self.log_event(
            event_type="dashboard_access",
            action=action,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def log_data_export(self, user_id: str, export_type: str):
        """
        Log data export event.

        Args:
            user_id: User exporting data
            export_type: Type of export (csv, pdf, etc.)
        """
        self.log_event(
            event_type="data_export",
            action=f"Exported {export_type}",
            user_id=user_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def test_logging(self) -> bool:
        """
        Test the audit logging system.

        Returns:
            True if logging works correctly
        """
        try:
            self.log_system_event("AUDIT_LOG_TEST", "SUCCESS", {"test": True})
            return True
        except Exception as e:
            print(f"Audit logging test failed: {e}")
            return False


# Global audit logger instance
audit_logger_instance = AuditLogger()


class SecurityAndAuditService:
    """
    Security and Audit Service wrapper for consistent interface.

    Provides a unified interface for audit logging with HIPAA compliance.
    """

    def __init__(self):
        """Initialize with global audit logger instance."""
        self.audit_logger = audit_logger_instance

    def log_event(self, event_type: str, action: str, **kwargs):
        """Log an audit event."""
        return self.audit_logger.log_event(event_type, action, **kwargs)

    def log_appointment_event(
        self,
        event_type: str,
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        result: str = "SUCCESS",
    ):
        """Log appointment-related events."""
        return self.audit_logger.log_appointment_event(
            event_type, session_id, details, result
        )

    def log_appointment_creation(
        self,
        appointment_id: str,
        patient_id: str,
        provider_id: str,
        appointment_time: str,
        session_id: Optional[str] = None,
        confirmation_number: Optional[str] = None,
        result: str = "SUCCESS",
    ):
        """Log successful appointment creation."""
        return self.audit_logger.log_appointment_creation(
            appointment_id,
            patient_id,
            provider_id,
            appointment_time,
            session_id,
            confirmation_number,
            result,
        )

    def log_appointment_retry(
        self,
        patient_id: str,
        provider_id: str,
        attempt: int,
        error: str,
        session_id: Optional[str] = None,
    ):
        """Log appointment creation retry."""
        return self.audit_logger.log_appointment_retry(
            patient_id, provider_id, attempt, error, session_id
        )

    def log_appointment_failure(
        self,
        patient_id: str,
        provider_id: str,
        error: str,
        retry_count: int,
        session_id: Optional[str] = None,
    ):
        """Log appointment creation failure."""
        return self.audit_logger.log_appointment_failure(
            patient_id, provider_id, error, retry_count, session_id
        )

    def log_dashboard_access(self, user_id: str, action: str):
        """Log dashboard access event."""
        return self.audit_logger.log_dashboard_access(user_id, action)

    def log_data_export(self, user_id: str, export_type: str):
        """Log data export event."""
        return self.audit_logger.log_data_export(user_id, export_type)


def log_audit_event(event_type: str, action: str, **kwargs):
    """
    Convenience function for logging audit events.

    Args:
        event_type: Type of event
        action: Description of the action
        **kwargs: Additional event parameters
    """
    audit_logger_instance.log_event(event_type, action, **kwargs)


def log_system_event(action: str, result: str = "SUCCESS", **kwargs):
    """Convenience function for logging system events."""
    audit_logger_instance.log_system_event(action, result, kwargs if kwargs else None)


def log_configuration_change(
    action: str, user_id: str = "SYSTEM", result: str = "SUCCESS", **kwargs
):
    """Convenience function for logging configuration changes."""
    audit_logger_instance.log_configuration_change(
        action, user_id, result, kwargs if kwargs else None
    )
