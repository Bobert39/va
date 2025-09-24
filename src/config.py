"""
Configuration Management Module

This module handles encrypted JSON configuration loading, validation,
and management for the Voice AI Platform. It provides secure storage
for practice settings, credentials, and operational parameters.
"""

import base64
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class ConfigurationManager:
    """
    Handles secure configuration management with encryption support.

    Features:
    - Encrypted storage of sensitive configuration data
    - Validation of configuration structure
    - Default configuration generation
    - Environment variable integration
    """

    def __init__(
        self, config_path: str = "config.json", password: Optional[str] = None
    ):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to configuration file
            password: Password for encryption (uses env var if not provided)
        """
        self.config_path = Path(config_path)
        self.password: str = (
            password or os.getenv("CONFIG_PASSWORD") or "default-dev-password"
        )
        self._config: Dict[str, Any] = {}
        self._encryption_key: Optional[bytes] = None

    def _generate_key(self, password: str, salt: bytes) -> bytes:
        """Generate encryption key from password and salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def _encrypt_data(self, data: Dict[str, Any]) -> str:
        """Encrypt configuration data."""
        # Generate a random salt
        salt = os.urandom(16)
        key = self._generate_key(self.password, salt)
        fernet = Fernet(key)

        # Encrypt the JSON data
        json_data = json.dumps(data).encode()
        encrypted_data = fernet.encrypt(json_data)

        # Combine salt and encrypted data
        combined = salt + encrypted_data
        return base64.urlsafe_b64encode(combined).decode()

    def _decrypt_data(self, encrypted_string: str) -> Dict[str, Any]:
        """Decrypt configuration data."""
        try:
            # Decode the base64 data
            combined = base64.urlsafe_b64decode(encrypted_string.encode())

            # Extract salt and encrypted data
            salt = combined[:16]
            encrypted_data = combined[16:]

            # Generate key and decrypt
            key = self._generate_key(self.password, salt)
            fernet = Fernet(key)

            decrypted_data = fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logger.error(f"Failed to decrypt configuration: {e}")
            raise ValueError("Invalid configuration file or password")

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration structure."""
        return {
            "practice_name": "Voice AI Practice",
            "emr_credentials": {
                "base_url": "https://your-emr-instance.com",
                "client_id": "",
                "client_secret": "",
                "redirect_uri": "http://localhost:8000/auth/callback",
            },
            "oauth_config": {
                "client_id": "",
                "client_secret": "",
                "redirect_uri": "http://localhost:8000/oauth/callback",
                "authorization_endpoint": "",
                "token_endpoint": "",
                "fhir_base_url": "",
                "scopes": [
                    "openid",
                    "fhirUser",
                    "patient/*.read",
                    "patient/*.write",
                    "Patient.read",
                    "Encounter.read",
                    "DiagnosticReport.read",
                    "Medication.read",
                    "Appointment.read",
                    "Appointment.write",
                ],
            },
            "oauth_tokens": {
                "access_token": "",
                "refresh_token": "",
                "token_type": "Bearer",
                "expires_at": "",
                "scope": "",
            },
            "api_keys": {
                "openai_api_key": "",
                "twilio_account_sid": "",
                "twilio_auth_token": "",
                "azure_speech_key": "",
                "azure_speech_region": "",
            },
            "operational_hours": {
                "monday": {"start": "09:00", "end": "17:00"},
                "tuesday": {"start": "09:00", "end": "17:00"},
                "wednesday": {"start": "09:00", "end": "17:00"},
                "thursday": {"start": "09:00", "end": "17:00"},
                "friday": {"start": "09:00", "end": "17:00"},
                "saturday": {"start": "09:00", "end": "13:00"},
                "sunday": {"closed": True},
            },
            "system_settings": {
                "log_level": "INFO",
                "max_call_duration_minutes": 10,
                "enable_audit_logging": True,
                "audit_log_rotation_mb": 10,
            },
            "providers": [
                {
                    "id": "provider_001",
                    "name": "Dr. Sample Provider",
                    "email": "provider@example.com",
                    "phone": "(555) 123-4567",
                    "specialty": "Family Medicine",
                    "active": True,
                    "schedule": {
                        "monday": {"start": "09:00", "end": "17:00", "available": True},
                        "tuesday": {
                            "start": "09:00",
                            "end": "17:00",
                            "available": True,
                        },
                        "wednesday": {
                            "start": "09:00",
                            "end": "17:00",
                            "available": True,
                        },
                        "thursday": {
                            "start": "09:00",
                            "end": "17:00",
                            "available": True,
                        },
                        "friday": {"start": "09:00", "end": "17:00", "available": True},
                        "saturday": {"available": False},
                        "sunday": {"available": False},
                    },
                    "preferences": {
                        "appointment_duration_minutes": 30,
                        "buffer_time_minutes": 15,
                        "max_appointments_per_day": 20,
                        "appointment_types": [
                            "consultation",
                            "follow_up",
                            "new_patient",
                        ],
                    },
                }
            ],
            "appointment_types": [
                {
                    "id": "consultation",
                    "name": "Consultation",
                    "duration_minutes": 30,
                    "description": "General consultation appointment",
                    "active": True,
                    "scheduling_rules": {
                        "advance_booking_days": 30,
                        "min_notice_hours": 24,
                        "allow_online_booking": True,
                    },
                },
                {
                    "id": "follow_up",
                    "name": "Follow-up",
                    "duration_minutes": 20,
                    "description": "Follow-up appointment for existing patients",
                    "active": True,
                    "scheduling_rules": {
                        "advance_booking_days": 14,
                        "min_notice_hours": 4,
                        "allow_online_booking": True,
                    },
                },
                {
                    "id": "new_patient",
                    "name": "New Patient",
                    "duration_minutes": 45,
                    "description": "Initial appointment for new patients",
                    "active": True,
                    "scheduling_rules": {
                        "advance_booking_days": 60,
                        "min_notice_hours": 48,
                        "allow_online_booking": False,
                    },
                },
            ],
            "practice_information": {
                "full_name": "Voice AI Practice - Complete Medical Care",
                "address": {
                    "street": "123 Medical Center Drive",
                    "city": "Healthcare City",
                    "state": "HC",
                    "zip_code": "12345",
                    "country": "USA",
                },
                "phone": "(555) 123-4567",
                "fax": "(555) 123-4568",
                "email": "contact@voiceaipractice.com",
                "website": "https://www.voiceaipractice.com",
                "departments": [
                    {
                        "name": "Primary Care",
                        "phone": "(555) 123-4567",
                        "location": "Main Building, Floor 1",
                    }
                ],
                "greeting_customization": {
                    "phone_greeting": "Thank you for calling Voice AI Practice. How may we help you today?",
                    "appointment_confirmation": "Hello, this is Voice AI Practice calling to confirm your appointment.",
                    "after_hours_message": "Thank you for calling Voice AI Practice. Our office is currently closed. Please call back during business hours or visit our website for more information.",
                },
            },
            "tts_configuration": {
                "provider": "openai",
                "voice_model": "alloy",
                "speaking_rate": 1.0,
                "practice_pronunciation": {
                    "practice_name": "",
                    "common_procedures": {
                        "checkup": "CHECK up",
                        "consultation": "con-sul-TAY-shun",
                        "follow up": "FOLLOW up",
                        "appointment": "a-POINT-ment",
                    },
                },
                "communication_style": {
                    "tone": "professional_friendly",
                    "greeting_template": "Hello, this is {practice_name}. I'm calling to confirm your upcoming appointment.",
                    "confirmation_template": "I have scheduled your {appointment_type} on {date} at {time} with {provider_name} at our {location} location. Please say 'yes' to confirm or 'no' if you need to make changes.",
                    "closing_template": "Thank you for choosing {practice_name}. We look forward to seeing you. Have a great day!",
                },
            },
        }

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate configuration structure and required fields.

        Args:
            config: Configuration dictionary to validate

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        required_sections = [
            "practice_name",
            "emr_credentials",
            "oauth_config",
            "oauth_tokens",
            "api_keys",
            "operational_hours",
            "system_settings",
            "providers",
            "appointment_types",
            "practice_information",
            "tts_configuration",
        ]

        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")

        # Validate EMR credentials structure
        emr_required = ["base_url", "client_id", "client_secret", "redirect_uri"]
        for field in emr_required:
            if field not in config["emr_credentials"]:
                raise ValueError(f"Missing EMR credential field: {field}")

        # Validate OAuth configuration structure
        oauth_config_required = [
            "client_id",
            "client_secret",
            "redirect_uri",
            "authorization_endpoint",
            "token_endpoint",
            "fhir_base_url",
            "scopes",
        ]
        for field in oauth_config_required:
            if field not in config["oauth_config"]:
                raise ValueError(f"Missing OAuth config field: {field}")

        # Validate OAuth tokens structure
        oauth_tokens_required = [
            "access_token",
            "refresh_token",
            "token_type",
            "expires_at",
            "scope",
        ]
        for field in oauth_tokens_required:
            if field not in config["oauth_tokens"]:
                raise ValueError(f"Missing OAuth tokens field: {field}")

        # Validate API keys structure
        api_keys_required = [
            "openai_api_key",
            "twilio_account_sid",
            "twilio_auth_token",
            "azure_speech_key",
            "azure_speech_region",
        ]
        for field in api_keys_required:
            if field not in config["api_keys"]:
                raise ValueError(f"Missing API key field: {field}")

        # Validate operational hours
        if not isinstance(config["operational_hours"], dict):
            raise ValueError("operational_hours must be a dictionary")

        # Validate TTS configuration structure
        tts_config_required = [
            "provider",
            "voice_model",
            "speaking_rate",
            "practice_pronunciation",
            "communication_style",
        ]
        for field in tts_config_required:
            if field not in config["tts_configuration"]:
                raise ValueError(f"Missing TTS configuration field: {field}")

        # Validate TTS communication style structure
        comm_style_required = [
            "tone",
            "greeting_template",
            "confirmation_template",
            "closing_template",
        ]
        for field in comm_style_required:
            if field not in config["tts_configuration"]["communication_style"]:
                raise ValueError(f"Missing TTS communication style field: {field}")

        # Validate providers structure
        if not isinstance(config["providers"], list):
            raise ValueError("providers must be a list")

        for i, provider in enumerate(config["providers"]):
            provider_required = ["id", "name", "active", "schedule", "preferences"]
            for field in provider_required:
                if field not in provider:
                    raise ValueError(
                        f"Missing provider field '{field}' in provider {i}"
                    )

        # Validate appointment types structure
        if not isinstance(config["appointment_types"], list):
            raise ValueError("appointment_types must be a list")

        for i, apt_type in enumerate(config["appointment_types"]):
            apt_type_required = ["id", "name", "duration_minutes", "active"]
            for field in apt_type_required:
                if field not in apt_type:
                    raise ValueError(
                        f"Missing appointment type field '{field}' in appointment type {i}"
                    )

        # Validate practice information structure
        practice_info_required = ["full_name", "address", "phone"]
        for field in practice_info_required:
            if field not in config["practice_information"]:
                raise ValueError(f"Missing practice information field: {field}")

        return True

    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file.

        Returns:
            Configuration dictionary
        """
        if not self.config_path.exists():
            logger.info("Configuration file not found, creating default configuration")
            default_config = self.get_default_config()
            self.save_config(default_config)
            return default_config

        try:
            with open(self.config_path, "r") as f:
                file_content = f.read().strip()

            # Check if file is encrypted (base64 encoded)
            try:
                # Try to decode as base64 first
                base64.urlsafe_b64decode(file_content.encode())
                # If successful, it's encrypted
                config = self._decrypt_data(file_content)
            except Exception:
                # If base64 decode fails, assume it's plain JSON
                config = json.loads(file_content)

            self.validate_config(config)
            self._config = config
            logger.info("Configuration loaded successfully")
            return config

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            logger.info("Loading default configuration")
            default_config = self.get_default_config()
            self.save_config(default_config)
            return default_config

    def save_config(self, config: Dict[str, Any], encrypt: bool = True) -> None:
        """
        Save configuration to file.

        Args:
            config: Configuration dictionary to save
            encrypt: Whether to encrypt the configuration (default: True)
        """
        self.validate_config(config)

        # Ensure config directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, "w") as f:
            if encrypt:
                encrypted_content = self._encrypt_data(config)
                f.write(encrypted_content)
            else:
                json.dump(config, f, indent=2)

        self._config = config
        logger.info(f"Configuration saved to {self.config_path}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Configuration key (supports dot notation,
            e.g., 'api_keys.openai_api_key')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if not self._config:
            self.load_config()

        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value by key.

        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        if not self._config:
            self.load_config()

        keys = key.split(".")
        config_ref = self._config

        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in config_ref:
                config_ref[k] = {}
            config_ref = config_ref[k]

        # Set the final value
        config_ref[keys[-1]] = value

        # Save the updated configuration
        self.save_config(self._config)

    def update_configuration_realtime(
        self, config_updates: Dict[str, Any], validate_first: bool = True
    ) -> Dict[str, Any]:
        """
        Update configuration with real-time changes and event notification.

        Args:
            config_updates: Dictionary of configuration updates
            validate_first: Whether to validate before applying changes

        Returns:
            Dictionary with update status and any errors
        """
        result = {
            "success": False,
            "message": "",
            "backup_created": False,
            "rollback_available": False,
            "errors": [],
        }

        try:
            # Load current configuration
            current_config = self.load_config()

            # Create backup before changes
            backup_config = self._create_configuration_backup(current_config)
            result["backup_created"] = True
            result["rollback_available"] = True

            # Create updated configuration by merging changes
            updated_config = self._merge_configuration_updates(
                current_config, config_updates
            )

            # Validate if requested
            if validate_first:
                validation_result = self._validate_configuration_changes(
                    updated_config, current_config
                )
                if not validation_result["valid"]:
                    result["errors"] = validation_result["errors"]
                    result["message"] = "Configuration validation failed"
                    return result

            # Apply changes with atomic operation
            self._apply_configuration_changes(updated_config)

            # Trigger configuration change events
            self._trigger_configuration_events(
                config_updates, current_config, updated_config
            )

            # Log the changes for audit
            self._log_configuration_changes(config_updates, backup_config["backup_id"])

            result["success"] = True
            result["message"] = "Configuration updated successfully"
            result["backup_id"] = backup_config["backup_id"]

        except Exception as e:
            logger.error(f"Configuration update failed: {e}")
            result["errors"].append(str(e))
            result["message"] = f"Configuration update failed: {str(e)}"

            # Attempt rollback if backup exists
            if result["backup_created"]:
                try:
                    self._rollback_configuration(backup_config["backup_id"])
                    result["message"] += " (automatically rolled back)"
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")
                    result["message"] += f" (rollback failed: {rollback_error})"

        return result

    def _create_configuration_backup(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a backup of current configuration."""
        import random
        import time

        # Use time, process ID, and random number to ensure uniqueness
        timestamp = int(time.time())
        random_suffix = random.randint(100000, 999999)
        backup_id = f"backup_{timestamp}_{random_suffix}"
        backup_path = Path(f"{self.config_path}.{backup_id}")

        # Save backup
        with open(backup_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Configuration backup created: {backup_path}")

        return {
            "backup_id": backup_id,
            "backup_path": str(backup_path),
            "timestamp": timestamp,
            "config": config.copy(),
        }

    def _merge_configuration_updates(
        self, current_config: Dict[str, Any], updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge configuration updates into current configuration."""
        import copy

        updated_config = copy.deepcopy(current_config)

        def deep_update(base_dict, update_dict):
            for key, value in update_dict.items():
                if (
                    key in base_dict
                    and isinstance(base_dict[key], dict)
                    and isinstance(value, dict)
                ):
                    deep_update(base_dict[key], value)
                else:
                    base_dict[key] = value

        deep_update(updated_config, updates)
        return updated_config

    def _validate_configuration_changes(
        self, new_config: Dict[str, Any], current_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate configuration changes before applying."""
        result = {"valid": True, "errors": [], "warnings": []}

        try:
            # Use existing validation method
            self.validate_config(new_config)

            # Additional real-time validation checks
            self._validate_provider_schedules(new_config.get("providers", []))
            self._validate_business_hours(new_config.get("operational_hours", {}))
            self._validate_appointment_types(new_config.get("appointment_types", []))

        except ValueError as e:
            result["valid"] = False
            result["errors"].append(str(e))
        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Validation error: {str(e)}")

        return result

    def _validate_provider_schedules(self, providers: List[Dict[str, Any]]):
        """Validate provider schedule configurations."""
        for provider in providers:
            if not provider.get("name", "").strip():
                raise ValueError(f"Provider name is required")

            # Validate provider ID uniqueness
            provider_ids = [p.get("id") for p in providers if p.get("id")]
            if len(provider_ids) != len(set(provider_ids)):
                raise ValueError("Provider IDs must be unique")

    def _validate_business_hours(self, hours: Dict[str, Any]):
        """Validate business hours configuration."""
        if not hours:
            return

        days = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        for day in days:
            if day in hours and hours[day].get("isOpen"):
                start_time = hours[day].get("start")
                end_time = hours[day].get("end")

                if not start_time or not end_time:
                    raise ValueError(f"Start and end times required for {day}")

                # Validate time format and logic
                from datetime import datetime

                try:
                    start = datetime.strptime(start_time, "%H:%M")
                    end = datetime.strptime(end_time, "%H:%M")
                    if start >= end:
                        raise ValueError(f"End time must be after start time for {day}")
                except ValueError as e:
                    # Re-raise specific error messages, or provide generic for parsing errors
                    error_msg = str(e)
                    if "End time must be after start time" in error_msg:
                        raise e
                    else:
                        raise ValueError(f"Invalid time format for {day}")

    def _validate_appointment_types(self, appointment_types: List[Dict[str, Any]]):
        """Validate appointment type configurations."""
        for apt_type in appointment_types:
            if not apt_type.get("name", "").strip():
                raise ValueError("Appointment type name is required")

            duration = apt_type.get("duration_minutes", 0)
            if not isinstance(duration, int) or duration < 5 or duration > 480:
                raise ValueError(
                    f"Invalid duration for appointment type '{apt_type.get('name')}': must be between 5-480 minutes"
                )

        # Validate unique IDs
        type_ids = [t.get("id") for t in appointment_types if t.get("id")]
        if len(type_ids) != len(set(type_ids)):
            raise ValueError("Appointment type IDs must be unique")

    def _apply_configuration_changes(self, new_config: Dict[str, Any]):
        """Apply configuration changes atomically."""
        # Save the new configuration
        self.save_config(new_config)

        # Update in-memory configuration
        self._config = new_config

        logger.info("Configuration changes applied successfully")

    def _apply_configuration_rollback(self, rollback_config: Dict[str, Any]):
        """Apply configuration rollback without validation (for error recovery)."""
        # Save the rollback configuration directly
        with open(self.config_path, "w") as f:
            encrypted_content = self._encrypt_data(rollback_config)
            f.write(encrypted_content)

        # Update in-memory configuration
        self._config = rollback_config

        logger.info("Configuration rollback applied successfully")

    def _trigger_configuration_events(
        self,
        updates: Dict[str, Any],
        old_config: Dict[str, Any],
        new_config: Dict[str, Any],
    ):
        """Trigger events for configuration changes."""
        # This is where you would integrate with an event system
        # For now, we'll log the events

        events = []

        # Check for specific changes and create events
        if "providers" in updates:
            events.append(
                {
                    "type": "providers_updated",
                    "timestamp": time.time(),
                    "old_count": len(old_config.get("providers", [])),
                    "new_count": len(new_config.get("providers", [])),
                }
            )

        if "operational_hours" in updates:
            events.append(
                {
                    "type": "business_hours_updated",
                    "timestamp": time.time(),
                    "changes": updates["operational_hours"],
                }
            )

        if "appointment_types" in updates:
            events.append(
                {
                    "type": "appointment_types_updated",
                    "timestamp": time.time(),
                    "old_count": len(old_config.get("appointment_types", [])),
                    "new_count": len(new_config.get("appointment_types", [])),
                }
            )

        if "practice_information" in updates:
            events.append(
                {
                    "type": "practice_info_updated",
                    "timestamp": time.time(),
                    "practice_name": new_config.get("practice_information", {}).get(
                        "full_name"
                    ),
                }
            )

        # Log events
        for event in events:
            logger.info(f"Configuration event: {event}")

        # Here you would typically publish events to subscribers
        # For example: event_bus.publish(event)

    def _log_configuration_changes(self, updates: Dict[str, Any], backup_id: str):
        """Log configuration changes for audit purposes."""
        from src.audit import log_audit_event

        try:
            # Create a summary of changes
            change_summary = []
            for section, changes in updates.items():
                if isinstance(changes, dict):
                    change_summary.append(f"{section}: {len(changes)} items updated")
                elif isinstance(changes, list):
                    change_summary.append(f"{section}: {len(changes)} items")
                else:
                    change_summary.append(f"{section}: updated")

            log_audit_event(
                event_type="configuration_update",
                action="Configuration updated via real-time API",
                user_id="system",
                additional_data={
                    "changes": change_summary,
                    "backup_id": backup_id,
                    "sections_updated": list(updates.keys()),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to log configuration changes: {e}")

    def rollback_configuration(self, backup_id: str) -> Dict[str, Any]:
        """Rollback configuration to a previous backup."""
        result = {"success": False, "message": ""}

        try:
            backup_path = Path(f"{self.config_path}.{backup_id}")

            if not backup_path.exists():
                result["message"] = f"Backup {backup_id} not found"
                return result

            # Load backup configuration
            with open(backup_path, "r") as f:
                backup_config = json.load(f)

            # Validate backup configuration
            self.validate_config(backup_config)

            # Create a backup of current state before rollback
            current_backup = self._create_configuration_backup(self.load_config())

            # Apply rollback
            self._apply_configuration_changes(backup_config)

            # Log rollback action
            from src.audit import log_audit_event

            log_audit_event(
                event_type="configuration_rollback",
                action="Configuration rolled back to previous backup",
                user_id="system",
                additional_data={
                    "rollback_to": backup_id,
                    "current_backup": current_backup["backup_id"],
                },
            )

            result["success"] = True
            result["message"] = f"Configuration rolled back to {backup_id}"
            result["current_backup"] = current_backup["backup_id"]

        except Exception as e:
            logger.error(f"Configuration rollback failed: {e}")
            result["message"] = f"Rollback failed: {str(e)}"

        return result

    def _rollback_configuration(self, backup_id: str):
        """Internal rollback method used by update_configuration_realtime."""
        backup_path = Path(f"{self.config_path}.{backup_id}")

        if backup_path.exists():
            with open(backup_path, "r") as f:
                backup_config = json.load(f)
            self._apply_configuration_rollback(backup_config)
            logger.info(f"Configuration automatically rolled back to {backup_id}")
        else:
            raise Exception(f"Backup {backup_id} not found for rollback")

    def get_configuration_backups(self) -> List[Dict[str, Any]]:
        """Get list of available configuration backups."""
        backups = []
        config_dir = self.config_path.parent

        for backup_file in config_dir.glob(f"{self.config_path.name}.backup_*"):
            try:
                backup_id = backup_file.name.split(".")[-1]
                timestamp = int(backup_id.split("_")[1])

                backups.append(
                    {
                        "backup_id": backup_id,
                        "timestamp": timestamp,
                        "file_path": str(backup_file),
                        "size": backup_file.stat().st_size,
                        "created": datetime.fromtimestamp(timestamp).isoformat(),
                    }
                )
            except (ValueError, IndexError):
                continue

        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x["timestamp"], reverse=True)
        return backups


# Global configuration manager instance
config_manager = ConfigurationManager()


def get_config(key: Optional[str] = None, default: Any = None) -> Any:
    """
    Get configuration value or entire configuration.

    Args:
        key: Configuration key (optional)
        default: Default value if key not found

    Returns:
        Configuration value or entire configuration
    """
    if key is None:
        return config_manager.load_config()
    return config_manager.get(key, default)


def set_config(key: str, value: Any) -> None:
    """
    Set configuration value.

    Args:
        key: Configuration key
        value: Value to set
    """
    config_manager.set(key, value)
