"""
Infrastructure tests for development environment.

Tests Poetry dependency resolution, development server startup,
and other infrastructure components.
"""

import pytest
import subprocess
import sys
import os


class TestDevelopmentEnvironment:
    """Test development environment infrastructure."""

    def test_poetry_dependency_resolution(self):
        """Test Poetry dependency resolution."""
        # Test that we can import packages managed by Poetry
        try:
            import fastapi
            import pytest
            import uvicorn
            import cryptography
            import httpx

            # Verify key package versions are available
            assert hasattr(fastapi, "__version__")
            assert hasattr(pytest, "__version__")

        except ImportError as e:
            pytest.fail(f"Poetry dependency resolution failed - cannot import: {e}")

    def test_python_environment_setup(self):
        """Test Python environment setup."""
        # Test Python version
        assert sys.version_info >= (3, 9)

        # Test that we can import key packages
        try:
            import fastapi
            import pytest
            import uvicorn
            import cryptography

            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import required package: {e}")

    def test_project_structure_exists(self):
        """Test that project structure exists."""
        expected_dirs = [
            "src",
            "tests",
            "tests/unit",
            "tests/integration",
            "tests/infrastructure",
            "static",
        ]

        for dir_path in expected_dirs:
            assert os.path.exists(dir_path), f"Directory {dir_path} should exist"

        expected_files = [
            "pyproject.toml",
            "README.md",
            "config.example.json",
            "src/__init__.py",
            "src/main.py",
            "src/config.py",
            "src/audit.py",
        ]

        for file_path in expected_files:
            assert os.path.exists(file_path), f"File {file_path} should exist"
