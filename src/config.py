"""
Configuration Management Module

This module handles encrypted JSON configuration loading, validation,
and management for the Voice AI Platform. It provides secure storage
for practice settings, credentials, and operational parameters.
"""

import json
import os
import base64
from pathlib import Path
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import logging

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
        self.password = password or os.getenv("CONFIG_PASSWORD", "default-dev-password")
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
            "api_keys",
            "operational_hours",
            "system_settings",
        ]

        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")

        # Validate EMR credentials structure
        emr_required = ["base_url", "client_id", "client_secret", "redirect_uri"]
        for field in emr_required:
            if field not in config["emr_credentials"]:
                raise ValueError(f"Missing EMR credential field: {field}")

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
            except:
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
            key: Configuration key (supports dot notation, e.g., 'api_keys.openai_api_key')
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


# Global configuration manager instance
config_manager = ConfigurationManager()


def get_config(key: str = None, default: Any = None) -> Any:
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
