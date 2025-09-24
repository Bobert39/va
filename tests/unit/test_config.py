"""
Unit tests for configuration management system.

Tests the encrypted JSON configuration loading, validation,
and management functionality.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

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
            "oauth_config": {
                "client_id": "test_oauth_id",
                "client_secret": "test_oauth_secret",
                "redirect_uri": "http://localhost:8000/oauth/callback",
                "authorization_endpoint": "https://test.com/auth",
                "token_endpoint": "https://test.com/token",
                "fhir_base_url": "https://test.com/fhir",
                "scopes": ["openid", "fhirUser", "patient/*.read"],
            },
            "oauth_tokens": {
                "access_token": "",
                "refresh_token": "",
                "token_type": "Bearer",
                "expires_at": 0,
                "scope": "",
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
            "providers": [],
            "appointment_types": [],
            "practice_information": {},
            "tts_configuration": {
                "provider": "azure",
                "voice_model": "jenny",
                "speaking_rate": "medium",
                "practice_pronunciation": {},
                "communication_style": "professional",
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


class TestConfigurationManagerRealTimeUpdates:
    """Test real-time configuration update functionality."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary config file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            yield f.name
        # Cleanup
        if os.path.exists(f.name):
            os.unlink(f.name)

        # Cleanup any backup files created during testing
        backup_pattern = f"{f.name}.backup_*"
        import glob

        for backup_file in glob.glob(backup_pattern):
            try:
                os.unlink(backup_file)
            except:
                pass

    @pytest.fixture
    def config_manager(self, temp_config_file):
        """Create a configuration manager with temporary file."""
        return ConfigurationManager(
            config_path=temp_config_file, password="test-password"
        )

    @pytest.fixture
    def sample_config_updates(self):
        """Sample configuration updates for testing."""
        return {
            "providers": [
                {
                    "id": "provider_1",
                    "name": "Dr. Smith",
                    "specialization": "Family Medicine",
                    "active": True,
                    "schedule": {"monday": {"start": "09:00", "end": "17:00"}},
                    "preferences": {"default_appointment_duration": 30},
                }
            ],
            "appointment_types": [
                {
                    "id": "apt_1",
                    "name": "Consultation",
                    "duration_minutes": 30,
                    "description": "General consultation",
                    "active": True,
                }
            ],
            "operational_hours": {
                "monday": {"isOpen": True, "start": "08:00", "end": "18:00"},
                "tuesday": {"isOpen": True, "start": "08:00", "end": "18:00"},
            },
            "practice_information": {
                "full_name": "Test Medical Center",
                "address": {
                    "street": "123 Main St",
                    "city": "Springfield",
                    "state": "NY",
                    "zip": "12345",
                },
                "phone": "(555) 123-4567",
            },
        }

    def test_real_time_configuration_update_success(
        self, config_manager, sample_config_updates
    ):
        """Test successful real-time configuration update."""
        # Initialize with default configuration
        config_manager.load_config()

        # Perform real-time update
        result = config_manager.update_configuration_realtime(sample_config_updates)

        # Verify success
        assert result["success"] is True
        assert result["backup_created"] is True
        assert result["rollback_available"] is True
        assert "backup_id" in result

        # Verify changes were applied
        updated_config = config_manager.load_config()
        assert len(updated_config["providers"]) == 1
        assert updated_config["providers"][0]["name"] == "Dr. Smith"
        assert (
            updated_config["practice_information"]["full_name"] == "Test Medical Center"
        )

    def test_real_time_update_validation_failure(self, config_manager):
        """Test real-time update with validation failure."""
        # Initialize with default configuration
        config_manager.load_config()

        # Invalid updates (duplicate provider IDs)
        invalid_updates = {
            "providers": [
                {
                    "id": "provider_1",
                    "name": "Dr. Smith",
                    "active": True,
                    "schedule": {},
                    "preferences": {},
                },
                {
                    "id": "provider_1",
                    "name": "Dr. Jones",
                    "active": True,
                    "schedule": {},
                    "preferences": {},
                },  # Duplicate ID
            ]
        }

        # Perform update (should fail validation)
        result = config_manager.update_configuration_realtime(invalid_updates)

        # Verify failure
        assert result["success"] is False
        assert "Provider IDs must be unique" in str(result["errors"])

        # Verify original configuration unchanged (should be default providers)
        current_config = config_manager.load_config()
        assert (
            len(current_config["providers"]) == 1
        )  # Should still have default provider

    def test_configuration_backup_creation(self, config_manager, sample_config_updates):
        """Test that backups are created properly."""
        # Initialize and update configuration
        config_manager.load_config()
        result = config_manager.update_configuration_realtime(sample_config_updates)

        # Verify backup was created
        assert result["backup_created"] is True
        backup_id = result["backup_id"]

        # Check backup file exists
        backup_path = Path(f"{config_manager.config_path}.{backup_id}")
        assert backup_path.exists()

        # Verify backup contains original configuration
        with open(backup_path, "r") as f:
            backup_config = json.load(f)
        assert backup_config["practice_name"] == "Voice AI Practice"  # Default value

    def test_configuration_rollback(self, config_manager, sample_config_updates):
        """Test configuration rollback functionality."""
        # Initialize with default configuration
        original_config = config_manager.load_config()
        original_practice_name = original_config["practice_name"]

        # Perform update
        result = config_manager.update_configuration_realtime(sample_config_updates)
        backup_id = result["backup_id"]

        # Verify changes were applied
        updated_config = config_manager.load_config()
        assert (
            updated_config["practice_information"]["full_name"] == "Test Medical Center"
        )

        # Perform rollback
        rollback_result = config_manager.rollback_configuration(backup_id)

        # Verify rollback success
        assert rollback_result["success"] is True

        # Verify configuration was restored
        restored_config = config_manager.load_config()
        assert restored_config["practice_name"] == original_practice_name
        assert (
            restored_config.get("practice_information", {}).get("full_name")
            != "Test Medical Center"
        )

    def test_configuration_rollback_invalid_backup(self, config_manager):
        """Test rollback with invalid backup ID."""
        config_manager.load_config()

        # Try to rollback to non-existent backup
        result = config_manager.rollback_configuration("invalid_backup_id")

        # Verify failure
        assert result["success"] is False
        assert "not found" in result["message"]

    def test_configuration_backups_list(self, config_manager, sample_config_updates):
        """Test listing configuration backups."""
        # Initialize configuration
        config_manager.load_config()

        # Perform multiple updates to create multiple backups
        result1 = config_manager.update_configuration_realtime(sample_config_updates)
        assert result1["success"] is True

        # Create a completely new updates dict for second backup
        second_updates = {
            "practice_information": {
                "full_name": "Updated Medical Center",
                "address": "456 New Street",
                "phone": "555-9999",
                "email": "updated@test.com",
            }
        }
        result2 = config_manager.update_configuration_realtime(second_updates)
        assert result2["success"] is True

        # Get backups list
        backups = config_manager.get_configuration_backups()

        # Verify backups exist
        assert len(backups) >= 2
        for backup in backups:
            assert "backup_id" in backup
            assert "timestamp" in backup
            assert "file_path" in backup
            assert "size" in backup
            assert "created" in backup

    def test_provider_validation(self, config_manager):
        """Test provider-specific validation."""
        config_manager.load_config()

        # Test valid providers
        valid_providers = [
            {
                "id": "p1",
                "name": "Dr. Smith",
                "specialization": "Cardiology",
                "active": True,
                "schedule": {},
                "preferences": {},
            },
            {
                "id": "p2",
                "name": "Dr. Jones",
                "specialization": "Pediatrics",
                "active": True,
                "schedule": {},
                "preferences": {},
            },
        ]
        updates = {"providers": valid_providers}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is True

        # Test invalid providers (duplicate IDs)
        invalid_providers = [
            {
                "id": "p1",
                "name": "Dr. Smith",
                "active": True,
                "schedule": {},
                "preferences": {},
            },
            {
                "id": "p1",
                "name": "Dr. Jones",
                "active": True,
                "schedule": {},
                "preferences": {},
            },  # Duplicate ID
        ]
        updates = {"providers": invalid_providers}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is False
        assert "Provider IDs must be unique" in str(result["errors"])

        # Test missing provider name
        invalid_providers = [
            {
                "id": "p1",
                "name": "",
                "specialization": "Cardiology",
                "active": True,
                "schedule": {},
                "preferences": {},
            }
        ]
        updates = {"providers": invalid_providers}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is False
        assert "Provider name is required" in str(result["errors"])

    def test_business_hours_validation(self, config_manager):
        """Test business hours validation."""
        config_manager.load_config()

        # Test valid business hours
        valid_hours = {
            "monday": {"isOpen": True, "start": "09:00", "end": "17:00"},
            "tuesday": {"isOpen": False, "start": "09:00", "end": "17:00"},
        }
        updates = {"operational_hours": valid_hours}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is True

        # Test invalid time format
        invalid_hours = {"monday": {"isOpen": True, "start": "25:00", "end": "17:00"}}
        updates = {"operational_hours": invalid_hours}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is False
        assert "Invalid time format" in str(result["errors"])

        # Test end time before start time (with valid time format)
        invalid_hours = {"monday": {"isOpen": True, "start": "17:00", "end": "09:00"}}
        updates = {"operational_hours": invalid_hours}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is False
        assert "End time must be after start time" in str(result["errors"])

    def test_appointment_types_validation(self, config_manager):
        """Test appointment types validation."""
        config_manager.load_config()

        # Test valid appointment types
        valid_types = [
            {
                "id": "t1",
                "name": "Consultation",
                "duration_minutes": 30,
                "active": True,
            },
            {"id": "t2", "name": "Follow-up", "duration_minutes": 20, "active": True},
        ]
        updates = {"appointment_types": valid_types}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is True

        # Test duplicate IDs
        invalid_types = [
            {
                "id": "t1",
                "name": "Consultation",
                "duration_minutes": 30,
                "active": True,
            },
            {
                "id": "t1",
                "name": "Follow-up",
                "duration_minutes": 20,
                "active": True,
            },  # Duplicate ID
        ]
        updates = {"appointment_types": invalid_types}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is False
        assert "Appointment type IDs must be unique" in str(result["errors"])

        # Test invalid duration
        invalid_types = [
            {
                "id": "t1",
                "name": "Consultation",
                "duration_minutes": 600,
                "active": True,
            }  # Too long
        ]
        updates = {"appointment_types": invalid_types}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is False
        assert "must be between 5-480 minutes" in str(result["errors"])

        # Test missing name
        invalid_types = [
            {"id": "t1", "name": "", "duration_minutes": 30, "active": True}
        ]
        updates = {"appointment_types": invalid_types}
        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is False
        assert "Appointment type name is required" in str(result["errors"])

    def test_automatic_rollback_on_failure(self, config_manager):
        """Test automatic rollback when update fails after backup creation."""
        config_manager.load_config()

        # Mock a scenario where backup is created but update fails
        # This would typically happen if there's an unexpected error during application

        # We'll simulate this by temporarily breaking the save functionality
        original_save = config_manager.save_config

        def failing_save(*args, **kwargs):
            raise Exception("Simulated save failure")

        # Replace save method temporarily
        config_manager.save_config = failing_save

        # Attempt update
        updates = {"practice_information": {"full_name": "Test Practice"}}
        result = config_manager.update_configuration_realtime(updates)

        # Restore original save method
        config_manager.save_config = original_save

        # Verify automatic rollback occurred
        assert result["success"] is False
        assert "automatically rolled back" in result["message"]

        # Verify configuration wasn't changed
        current_config = config_manager.load_config()
        assert (
            current_config["practice_name"] == "Voice AI Practice"
        )  # Should be unchanged

    def test_merge_configuration_updates(self, config_manager):
        """Test configuration merging functionality."""
        # Load default configuration
        config_manager.load_config()

        # Test deep merge of nested structures
        updates = {
            "practice_information": {
                "full_name": "Updated Practice",
                "address": {
                    "street": "456 Oak Ave"
                    # Other address fields should be preserved
                },
            },
            "providers": [
                {
                    "id": "p1",
                    "name": "Dr. New",
                    "active": True,
                    "schedule": {},
                    "preferences": {},
                }
            ],
        }

        result = config_manager.update_configuration_realtime(updates)
        assert result["success"] is True

        # Verify merge worked correctly
        updated_config = config_manager.load_config()
        assert updated_config["practice_information"]["full_name"] == "Updated Practice"
        # Original sections should still exist
        assert "emr_credentials" in updated_config
        assert "api_keys" in updated_config

    def test_configuration_events_logging(self, config_manager, sample_config_updates):
        """Test that configuration events are properly logged."""
        # This test verifies the event logging functionality
        # In a real implementation, you'd mock the audit logging

        config_manager.load_config()

        # Perform update
        result = config_manager.update_configuration_realtime(sample_config_updates)

        # Verify success (indicating events were processed without errors)
        assert result["success"] is True

        # In a more complete test, you would:
        # 1. Mock the audit logging system
        # 2. Verify specific events were logged
        # 3. Check event data structure and content
