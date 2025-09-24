"""
Documentation validation tests for Voice AI Platform setup guides.

Tests that all documentation files exist, contain required sections,
and have working links and code examples.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List

import pytest
import requests


class TestDocumentationStructure:
    """Test that all required documentation files exist with proper structure."""

    @pytest.fixture
    def docs_dir(self) -> Path:
        """Return path to documentation directory."""
        return Path(__file__).parent.parent.parent / "docs"

    @pytest.fixture
    def setup_docs_dir(self, docs_dir: Path) -> Path:
        """Return path to setup documentation directory."""
        return docs_dir / "setup"

    def test_setup_directory_exists(self, setup_docs_dir: Path):
        """Test that setup documentation directory exists."""
        assert setup_docs_dir.exists(), "Setup documentation directory should exist"
        assert setup_docs_dir.is_dir(), "Setup path should be a directory"

    def test_required_setup_files_exist(self, setup_docs_dir: Path):
        """Test that all required setup documentation files exist."""
        required_files = [
            "README.md",
            "installation-guide.md",
            "environment-setup.md",
            "configuration-reference.md",
            "validation-guide.md",
            "troubleshooting.md",
            "quick-start.md",
        ]

        for filename in required_files:
            file_path = setup_docs_dir / filename
            assert file_path.exists(), f"{filename} should exist in setup directory"
            assert file_path.is_file(), f"{filename} should be a file"

    def test_main_readme_references_setup_docs(self):
        """Test that main README.md properly references setup documentation."""
        readme_path = Path(__file__).parent.parent.parent / "README.md"
        content = readme_path.read_text(encoding="utf-8")

        # Check for references to setup documentation
        expected_links = [
            "docs/setup/README.md",
            "docs/setup/quick-start.md",
            "docs/setup/installation-guide.md",
            "docs/setup/environment-setup.md",
            "docs/setup/configuration-reference.md",
            "docs/setup/validation-guide.md",
            "docs/setup/troubleshooting.md",
        ]

        for link in expected_links:
            assert link in content, f"Main README should reference {link}"

    def test_setup_readme_structure(self, setup_docs_dir: Path):
        """Test that setup README.md has proper structure."""
        readme_path = setup_docs_dir / "README.md"
        content = readme_path.read_text(encoding="utf-8")

        # Check for required sections
        required_sections = [
            "# Voice AI Platform Setup Documentation",
            "## 🚀 Quick Navigation",
            "## 🎯 Setup Path by User Type",
            "## 📋 Prerequisites Checklist",
            "## 🗂️ Documentation Structure",
            "## 🔍 Common Setup Scenarios",
        ]

        for section in required_sections:
            assert section in content, f"Setup README should contain section: {section}"


class TestDocumentationContent:
    """Test that documentation content meets quality standards."""

    @pytest.fixture
    def setup_docs_dir(self) -> Path:
        """Return path to setup documentation directory."""
        return Path(__file__).parent.parent.parent / "docs" / "setup"

    def test_installation_guide_completeness(self, setup_docs_dir: Path):
        """Test that installation guide contains all required sections."""
        guide_path = setup_docs_dir / "installation-guide.md"
        content = guide_path.read_text(encoding="utf-8")

        required_sections = [
            "# Voice AI Platform - Installation Guide",
            "## System Requirements",
            "## Python 3.9+ Installation",
            "## Poetry Installation and Setup",
            "## Project Setup",
            "## Dependency Installation Troubleshooting",
            "## Virtual Environment Best Practices",
            "## Version Compatibility Matrix",
        ]

        for section in required_sections:
            assert section in content, f"Installation guide should contain: {section}"

        # Check for PowerShell code blocks
        powershell_blocks = re.findall(r"```powershell\n(.*?)\n```", content, re.DOTALL)
        assert (
            len(powershell_blocks) >= 5
        ), "Installation guide should have multiple PowerShell examples"

    def test_configuration_reference_completeness(self, setup_docs_dir: Path):
        """Test that configuration reference contains all required sections."""
        guide_path = setup_docs_dir / "configuration-reference.md"
        content = guide_path.read_text(encoding="utf-8")

        required_sections = [
            "# Configuration Reference Guide",
            "## Configuration File Structure",
            "## Practice Information",
            "## EMR Credentials",
            "## API Keys",
            "## Operational Hours",
            "## System Settings",
            "## Encryption and Key Management",
            "## Environment Variable Overrides",
        ]

        for section in required_sections:
            assert (
                section in content
            ), f"Configuration reference should contain: {section}"

        # Check for JSON examples
        json_blocks = re.findall(r"```json\n(.*?)\n```", content, re.DOTALL)
        assert (
            len(json_blocks) >= 10
        ), "Configuration reference should have multiple JSON examples"

    def test_quick_start_guide_structure(self, setup_docs_dir: Path):
        """Test that quick start guide has proper structure for experienced developers."""
        guide_path = setup_docs_dir / "quick-start.md"
        content = guide_path.read_text(encoding="utf-8")

        # Check for time promises
        assert (
            "< 10 minutes" in content
        ), "Quick start should promise sub-10 minute setup"

        required_sections = [
            "# Quick Start Guide - Experienced Developers",
            "## ⚡ Express Setup (5 minutes)",
            "## 🚀 One-Line Commands",
            "## 🔧 Developer Shortcuts",
            "## 📁 Project Structure Quick Reference",
            "## 🧪 Testing & Quality",
            "## 🎯 Success Criteria",
        ]

        for section in required_sections:
            assert section in content, f"Quick start guide should contain: {section}"


class TestDocumentationLinks:
    """Test that all internal documentation links work."""

    @pytest.fixture
    def docs_dir(self) -> Path:
        """Return path to documentation directory."""
        return Path(__file__).parent.parent.parent / "docs"

    def test_internal_links_valid(self, docs_dir: Path):
        """Test that all internal markdown links are valid."""
        setup_dir = docs_dir / "setup"

        for md_file in setup_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")

            # Find all markdown links
            links = re.findall(r"\[.*?\]\((.*?)\)", content)

            for link in links:
                # Skip external links (http/https)
                if link.startswith(("http://", "https://")):
                    continue

                # Skip anchor links
                if link.startswith("#"):
                    continue

                # Resolve relative links
                if link.startswith("../"):
                    target_path = (md_file.parent / link).resolve()
                else:
                    target_path = (setup_dir / link).resolve()

                # Remove anchor references for file check
                file_path = str(target_path).split("#")[0]
                target_file = Path(file_path)

                assert (
                    target_file.exists()
                ), f"Link target should exist: {link} in {md_file.name} -> {target_file}"


class TestCodeExamples:
    """Test that code examples in documentation are valid."""

    @pytest.fixture
    def setup_docs_dir(self) -> Path:
        """Return path to setup documentation directory."""
        return Path(__file__).parent.parent.parent / "docs" / "setup"

    def test_json_examples_valid(self, setup_docs_dir: Path):
        """Test that all JSON examples in documentation are valid JSON."""
        config_guide = setup_docs_dir / "configuration-reference.md"
        content = config_guide.read_text(encoding="utf-8")

        # Extract JSON code blocks
        json_blocks = re.findall(r"```json\n(.*?)\n```", content, re.DOTALL)

        assert len(json_blocks) > 0, "Configuration reference should have JSON examples"

        for i, json_str in enumerate(json_blocks):
            try:
                json.loads(json_str)
            except json.JSONDecodeError as e:
                pytest.fail(
                    f"Invalid JSON in configuration reference, block {i + 1}: {e}"
                )

    def test_powershell_commands_syntax(self, setup_docs_dir: Path):
        """Test that PowerShell commands have basic syntax validity."""
        installation_guide = setup_docs_dir / "installation-guide.md"
        content = installation_guide.read_text(encoding="utf-8")

        # Extract PowerShell code blocks
        ps_blocks = re.findall(r"```powershell\n(.*?)\n```", content, re.DOTALL)

        assert len(ps_blocks) > 0, "Installation guide should have PowerShell examples"

        # Basic syntax checks
        for i, ps_code in enumerate(ps_blocks):
            # Check for basic PowerShell constructs
            lines = ps_code.strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Check for unmatched quotes (basic check)
                single_quotes = line.count("'")
                double_quotes = line.count('"')

                # Skip if quotes appear in comments
                if "#" in line:
                    comment_pos = line.index("#")
                    line_before_comment = line[:comment_pos]
                    single_quotes = line_before_comment.count("'")
                    double_quotes = line_before_comment.count('"')

                # Both single and double quotes should be even numbers (paired)
                if single_quotes % 2 != 0:
                    pytest.fail(
                        f"Unmatched single quotes in PowerShell block {i + 1}: {line}"
                    )
                if double_quotes % 2 != 0:
                    pytest.fail(
                        f"Unmatched double quotes in PowerShell block {i + 1}: {line}"
                    )


class TestDocumentationAccessibility:
    """Test that documentation is accessible and user-friendly."""

    @pytest.fixture
    def setup_docs_dir(self) -> Path:
        """Return path to setup documentation directory."""
        return Path(__file__).parent.parent.parent / "docs" / "setup"

    def test_headings_hierarchy(self, setup_docs_dir: Path):
        """Test that headings follow proper hierarchy (no skipped levels)."""
        for md_file in setup_docs_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")

            # Find all headings
            headings = re.findall(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)

            if not headings:
                continue

            heading_levels = [len(h[0]) for h in headings]

            # First heading should be level 1
            assert (
                heading_levels[0] == 1
            ), f"First heading in {md_file.name} should be level 1"

            # Check for skipped levels
            for i in range(1, len(heading_levels)):
                level_diff = heading_levels[i] - heading_levels[i - 1]
                assert (
                    level_diff <= 1
                ), f"Heading level skipped in {md_file.name}: {headings[i-1][1]} -> {headings[i][1]}"

    def test_code_blocks_have_language(self, setup_docs_dir: Path):
        """Test that code blocks specify language for syntax highlighting."""
        for md_file in setup_docs_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")

            # Find code blocks
            code_blocks = re.findall(r"```(\w*)\n", content)

            for i, lang in enumerate(code_blocks):
                # Allow some exceptions for generic blocks
                if lang in ["", "yaml", "txt"]:
                    continue

                assert lang in [
                    "powershell",
                    "bash",
                    "json",
                    "python",
                    "dockerfile",
                ], f"Code block {i + 1} in {md_file.name} should have valid language: '{lang}'"

    def test_time_estimates_present(self, setup_docs_dir: Path):
        """Test that setup guides include time estimates."""
        time_sensitive_files = [
            "README.md",
            "installation-guide.md",
            "quick-start.md",
            "validation-guide.md",
        ]

        time_patterns = [
            r"\d+\s*-?\s*\d*\s*minutes?",
            r"< \d+ min",
            r"\d+ min",
            r"\d+\s*hours?",
        ]

        for filename in time_sensitive_files:
            file_path = setup_docs_dir / filename
            if not file_path.exists():
                continue

            content = file_path.read_text(encoding="utf-8")

            has_time_estimate = any(
                re.search(pattern, content, re.IGNORECASE) for pattern in time_patterns
            )

            assert has_time_estimate, f"{filename} should include time estimates"


class TestDocumentationConsistency:
    """Test that documentation maintains consistency across files."""

    @pytest.fixture
    def setup_docs_dir(self) -> Path:
        """Return path to setup documentation directory."""
        return Path(__file__).parent.parent.parent / "docs" / "setup"

    def test_consistent_terminology(self, setup_docs_dir: Path):
        """Test that key terms are used consistently across documentation."""
        terminology_map = {
            "Voice AI Platform": ["voice-ai-platform", "Voice AI", "VoiceAI"],
            "config.json": ["configuration file", "config file"],
            "PowerShell": ["powershell", "PS"],
            "Windows 10+": ["Windows 10", "Win10"],
        }

        # Count term usage across all files
        term_usage = {}

        for md_file in setup_docs_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")

            for canonical_term, alternatives in terminology_map.items():
                if canonical_term not in term_usage:
                    term_usage[canonical_term] = {"canonical": 0, "alternatives": 0}

                # Count canonical term
                term_usage[canonical_term]["canonical"] += len(
                    re.findall(re.escape(canonical_term), content, re.IGNORECASE)
                )

                # Count alternatives
                for alt_term in alternatives:
                    term_usage[canonical_term]["alternatives"] += len(
                        re.findall(re.escape(alt_term), content, re.IGNORECASE)
                    )

        # Canonical terms should be used more than alternatives
        for canonical_term, counts in term_usage.items():
            if counts["canonical"] > 0 or counts["alternatives"] > 0:
                canonical_ratio = counts["canonical"] / (
                    counts["canonical"] + counts["alternatives"]
                )
                assert canonical_ratio >= 0.7, (
                    f"Canonical term '{canonical_term}' should be used more consistently. "
                    f"Ratio: {canonical_ratio:.2f}"
                )

    def test_consistent_file_references(self, setup_docs_dir: Path):
        """Test that file references are consistent across documentation."""
        common_files = {
            "config.json": r"config\.json",
            "pyproject.toml": r"pyproject\.toml",
            "README.md": r"README\.md",
        }

        for md_file in setup_docs_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")

            for file_name, pattern in common_files.items():
                matches = re.findall(pattern, content, re.IGNORECASE)

                # If file is referenced, it should use consistent naming
                if matches:
                    for match in matches:
                        assert (
                            match == file_name
                        ), f"File reference should be consistent: '{match}' should be '{file_name}' in {md_file.name}"


@pytest.mark.integration
class TestDocumentationUsability:
    """Integration tests for documentation usability."""

    def test_quick_start_time_feasibility(self):
        """Test that quick start guide time estimates are realistic."""
        # This would typically involve timing actual setup procedures
        # For now, we'll do basic feasibility checks

        setup_dir = Path(__file__).parent.parent.parent / "docs" / "setup"
        quick_start = setup_dir / "quick-start.md"
        content = quick_start.read_text(encoding="utf-8")

        # Count number of steps in express setup
        express_section = re.search(
            r"## ⚡ Express Setup.*?(?=##|$)", content, re.DOTALL
        )

        if express_section:
            steps = len(re.findall(r"###\s+\d+\.", express_section.group(0)))
            # Should have reasonable number of steps for 10-minute setup
            assert (
                3 <= steps <= 6
            ), f"Express setup should have 3-6 major steps, found {steps}"

    def test_validation_levels_progressive(self):
        """Test that validation levels are progressively comprehensive."""
        setup_dir = Path(__file__).parent.parent.parent / "docs" / "setup"
        validation_guide = setup_dir / "validation-guide.md"
        content = validation_guide.read_text(encoding="utf-8")

        # Find all validation levels
        levels = re.findall(r"## Level (\d+):", content)
        level_numbers = [int(level) for level in levels]

        # Should have sequential levels starting from 1
        assert level_numbers == list(
            range(1, len(level_numbers) + 1)
        ), f"Validation levels should be sequential: {level_numbers}"

        # Should have 3-5 validation levels
        assert (
            3 <= len(level_numbers) <= 5
        ), f"Should have 3-5 validation levels, found {len(level_numbers)}"


if __name__ == "__main__":
    # Run specific test categories
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "-x",  # Stop on first failure for faster feedback
        ]
    )
