"""
Integration tests for configuration system.

Tests the full configuration loading in application context
and integration with other components.
"""

import pytest
import tempfile
import os
from src.config import ConfigurationManager
from src.audit import AuditLogger


class TestConfigurationIntegration:
    """Test configuration integration with other components."""

    @pytest.fixture
    def temp_files(self):
        """Create temporary files for testing."""
        config_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        log_file = tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False)

        yield config_file.name, log_file.name

        # Cleanup
        for file_path in [config_file.name, log_file.name]:
            if os.path.exists(file_path):
                os.unlink(file_path)

    def test_full_configuration_loading_in_application_context(self, temp_files):
        """Test full configuration loading in application context."""
        config_path, log_path = temp_files

        # Create configuration manager
        config_manager = ConfigurationManager(config_path=config_path)

        # Load configuration (should create default)
        config = config_manager.load_config()

        # Verify configuration structure
        assert "practice_name" in config
        assert "emr_credentials" in config
        assert "system_settings" in config

        # Test configuration updates
        config_manager.set("practice_name", "Integration Test Practice")
        updated_config = config_manager.load_config()
        assert updated_config["practice_name"] == "Integration Test Practice"

    def test_configuration_changes_require_restart_behavior(self, temp_files):
        """Test configuration changes require restart behavior."""
        config_path, log_path = temp_files

        # Create configuration manager
        config_manager = ConfigurationManager(config_path=config_path)

        # Load initial configuration
        initial_config = config_manager.load_config()
        initial_practice_name = initial_config["practice_name"]

        # Modify configuration directly
        config_manager.set("practice_name", "Modified Practice")

        # Create new manager instance (simulating restart)
        new_manager = ConfigurationManager(config_path=config_path)
        reloaded_config = new_manager.load_config()

        # Verify changes persisted
        assert reloaded_config["practice_name"] == "Modified Practice"
        assert reloaded_config["practice_name"] != initial_practice_name

    def test_invalid_configuration_graceful_failure(self, temp_files):
        """Test invalid configuration graceful failure."""
        config_path, log_path = temp_files

        # Write invalid configuration to file
        with open(config_path, "w") as f:
            f.write('{"invalid": "config", "missing": "required_fields"}')

        # Create configuration manager
        config_manager = ConfigurationManager(config_path=config_path)

        # Should gracefully handle invalid config and create default
        config = config_manager.load_config()

        # Should have default configuration
        assert config["practice_name"] == "Voice AI Practice"
        assert "emr_credentials" in config
