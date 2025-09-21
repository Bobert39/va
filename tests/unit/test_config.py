"""
Unit tests for configuration management system.

Tests the encrypted JSON configuration loading, validation,
and management functionality.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from src.config import ConfigurationManager


class TestConfigurationManager:
    """Test configuration management functionality."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            yield f.name
        # Cleanup
        if os.path.exists(f.name):
            os.unlink(f.name)

    @pytest.fixture
    def config_manager(self, temp_config_file):
        """Create a configuration manager with temporary file."""
        return ConfigurationManager(
            config_path=temp_config_file, password="test-password"
        )

    def test_config_encryption_decryption(self, config_manager):
        """Test configuration encryption/decryption roundtrip."""
        test_config = {
            "practice_name": "Test Practice",
            "emr_credentials": {
                "base_url": "https://test.com",
                "client_id": "test_id",
                "client_secret": "test_secret",
                "redirect_uri": "http://localhost:8000/callback",
            },
            "api_keys": {
                "openai_api_key": "test_key",
                "twilio_account_sid": "test_sid",
                "twilio_auth_token": "test_token",
                "azure_speech_key": "test_speech_key",
                "azure_speech_region": "test_region",
            },
            "operational_hours": {"monday": {"start": "09:00", "end": "17:00"}},
            "system_settings": {
                "log_level": "INFO",
                "max_call_duration_minutes": 10,
                "enable_audit_logging": True,
                "audit_log_rotation_mb": 10,
            },
        }

        # Save encrypted config
        config_manager.save_config(test_config, encrypt=True)

        # Load and verify
        loaded_config = config_manager.load_config()
        assert loaded_config["practice_name"] == "Test Practice"
        assert loaded_config["emr_credentials"]["client_id"] == "test_id"

    def test_config_validation(self, config_manager):
        """Test configuration validation rules."""
        # Valid config should pass
        valid_config = config_manager.get_default_config()
        assert config_manager.validate_config(valid_config) is True

        # Invalid config should fail
        invalid_config = {"invalid": "config"}
        with pytest.raises(ValueError, match="Missing required configuration section"):
            config_manager.validate_config(invalid_config)

    def test_missing_config_handling(self, config_manager):
        """Test graceful handling of missing configuration."""
        # When config file doesn't exist, should create default
        config = config_manager.load_config()
        assert config["practice_name"] == "Voice AI Practice"
        assert "emr_credentials" in config
        assert "api_keys" in config

    def test_config_get_set(self, config_manager):
        """Test configuration get/set operations."""
        # Load default config
        config_manager.load_config()

        # Test get with dot notation
        practice_name = config_manager.get("practice_name")
        assert practice_name == "Voice AI Practice"

        # Test get nested value
        base_url = config_manager.get("emr_credentials.base_url")
        assert base_url == "https://your-emr-instance.com"

        # Test set operation
        config_manager.set("practice_name", "Updated Practice")
        assert config_manager.get("practice_name") == "Updated Practice"

        # Test nested set
        config_manager.set("emr_credentials.base_url", "https://updated.com")
        assert config_manager.get("emr_credentials.base_url") == "https://updated.com"

    def test_config_default_values(self, config_manager):
        """Test default configuration structure."""
        default_config = config_manager.get_default_config()

        # Verify required sections exist
        required_sections = [
            "practice_name",
            "emr_credentials",
            "api_keys",
            "operational_hours",
            "system_settings",
        ]
        for section in required_sections:
            assert section in default_config

        # Verify EMR credentials structure
        emr_creds = default_config["emr_credentials"]
        emr_required = ["base_url", "client_id", "client_secret", "redirect_uri"]
        for field in emr_required:
            assert field in emr_creds

        # Verify API keys structure
        api_keys = default_config["api_keys"]
        api_required = [
            "openai_api_key",
            "twilio_account_sid",
            "twilio_auth_token",
            "azure_speech_key",
            "azure_speech_region",
        ]
        for field in api_required:
            assert field in api_keys
