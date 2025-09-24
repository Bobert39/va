"""
Modern configuration management using Pydantic Settings.

This module replaces the old config.json approach with environment-based
configuration using Pydantic for validation and type safety.
"""

import os
from datetime import time
from functools import lru_cache
from typing import Dict, List, Optional

from pydantic import Field, SecretStr, validator
from pydantic.networks import HttpUrl
from pydantic_settings import BaseSettings


class OperationalHours(BaseSettings):
    """Operational hours for each day of the week."""

    start: Optional[str] = None
    end: Optional[str] = None
    closed: bool = False

    @validator("start", "end")
    def validate_time_format(cls, v):
        """Validate time is in HH:MM format."""
        if v is None:
            return v
        try:
            time.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Time must be in HH:MM format, got {v}")


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden via environment variables.
    Use .env file for local development.
    """

    # ==============================================================================
    # APPLICATION SETTINGS
    # ==============================================================================
    app_name: str = Field(default="Voice AI Platform", env="APP_NAME")
    environment: str = Field(default="development", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")

    # ==============================================================================
    # SERVER CONFIGURATION
    # ==============================================================================
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=9847, env="PORT")
    reload_on_change: bool = Field(default=False, env="RELOAD_ON_CHANGE")
    reload_dirs: str = Field(default="src,static", env="RELOAD_DIRS")
    workers: int = Field(default=4, env="WORKERS")
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000", env="CORS_ORIGINS"
    )

    # ==============================================================================
    # PRACTICE INFORMATION
    # ==============================================================================
    practice_name: str = Field(default="Your Practice Name", env="PRACTICE_NAME")
    practice_timezone: str = Field(default="America/New_York", env="PRACTICE_TIMEZONE")

    # ==============================================================================
    # EMR INTEGRATION
    # ==============================================================================
    emr_base_url: HttpUrl = Field(
        default="https://your-emr-instance.com", env="EMR_BASE_URL"
    )
    emr_client_id: str = Field(default="", env="EMR_CLIENT_ID")
    emr_client_secret: SecretStr = Field(default="", env="EMR_CLIENT_SECRET")
    emr_redirect_uri: str = Field(
        default="http://localhost:8000/auth/callback", env="EMR_REDIRECT_URI"
    )

    # ==============================================================================
    # OPENAI CONFIGURATION
    # ==============================================================================
    openai_api_key: SecretStr = Field(default="", env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4", env="OPENAI_MODEL")

    # ==============================================================================
    # TWILIO CONFIGURATION
    # ==============================================================================
    twilio_account_sid: str = Field(default="", env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: SecretStr = Field(default="", env="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field(default="", env="TWILIO_PHONE_NUMBER")
    max_call_duration_minutes: int = Field(default=10, env="MAX_CALL_DURATION_MINUTES")

    # ==============================================================================
    # AZURE SPEECH SERVICES
    # ==============================================================================
    azure_speech_key: SecretStr = Field(default="", env="AZURE_SPEECH_KEY")
    azure_speech_region: str = Field(default="westus2", env="AZURE_SPEECH_REGION")

    # ==============================================================================
    # OPERATIONAL HOURS
    # ==============================================================================
    hours_monday: str = Field(default="08:00-17:00", env="HOURS_MONDAY")
    hours_tuesday: str = Field(default="08:00-17:00", env="HOURS_TUESDAY")
    hours_wednesday: str = Field(default="08:00-17:00", env="HOURS_WEDNESDAY")
    hours_thursday: str = Field(default="08:00-17:00", env="HOURS_THURSDAY")
    hours_friday: str = Field(default="08:00-17:00", env="HOURS_FRIDAY")
    hours_saturday: str = Field(default="08:00-13:00", env="HOURS_SATURDAY")
    hours_sunday: str = Field(default="closed", env="HOURS_SUNDAY")

    # ==============================================================================
    # SECURITY & AUTHENTICATION
    # ==============================================================================
    dashboard_username: str = Field(default="admin", env="DASHBOARD_USERNAME")
    dashboard_password: SecretStr = Field(default="changeme", env="DASHBOARD_PASSWORD")

    # ==============================================================================
    # AUDIT & COMPLIANCE
    # ==============================================================================
    enable_audit_logging: bool = Field(default=True, env="ENABLE_AUDIT_LOGGING")
    audit_log_file: str = Field(default="audit.log", env="AUDIT_LOG_FILE")
    audit_log_rotation_mb: int = Field(default=10, env="AUDIT_LOG_ROTATION_MB")

    # ==============================================================================
    # DEVELOPMENT SETTINGS
    # ==============================================================================
    allow_dev_defaults: bool = Field(default=False, env="ALLOW_DEV_DEFAULTS")

    # ==============================================================================
    # TESTING CONFIGURATION
    # ==============================================================================
    pytest_cache_dir: str = Field(default=".pytest_cache", env="PYTEST_CACHE_DIR")
    coverage_min_threshold: int = Field(default=80, env="COVERAGE_MIN_THRESHOLD")

    # ==============================================================================
    # BUILD SETTINGS
    # ==============================================================================
    build_target: str = Field(default="windows", env="BUILD_TARGET")
    build_name: str = Field(default="voice-ai-platform", env="BUILD_NAME")

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_nested_delimiter = "__"

    def get_cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list."""
        if isinstance(self.cors_origins, str):
            return [
                origin.strip()
                for origin in self.cors_origins.split(",")
                if origin.strip()
            ]
        return self.cors_origins

    def get_reload_dirs_list(self) -> List[str]:
        """Get reload directories as a list."""
        if isinstance(self.reload_dirs, str):
            return [dir.strip() for dir in self.reload_dirs.split(",") if dir.strip()]
        return self.reload_dirs

    def get_operational_hours(self, day: str) -> Dict[str, Optional[str]]:
        """
        Get operational hours for a specific day.

        Args:
            day: Day of the week (monday, tuesday, etc.)

        Returns:
            Dictionary with 'start', 'end', and 'closed' keys
        """
        hours_str = getattr(self, f"hours_{day.lower()}", "closed")

        if hours_str == "closed":
            return {"start": None, "end": None, "closed": True}

        if "-" in hours_str:
            start, end = hours_str.split("-")
            return {"start": start.strip(), "end": end.strip(), "closed": False}

        return {"start": None, "end": None, "closed": True}

    def is_configured_for_production(self) -> bool:
        """Check if all required production settings are configured."""
        required_fields = [
            self.openai_api_key.get_secret_value() if self.openai_api_key else "",
            self.twilio_account_sid,
            self.twilio_auth_token.get_secret_value() if self.twilio_auth_token else "",
            self.azure_speech_key.get_secret_value() if self.azure_speech_key else "",
        ]

        return all(field for field in required_fields) and not self.allow_dev_defaults

    def get_sanitized_dict(self) -> dict:
        """
        Get settings as dictionary with sensitive values masked.
        Useful for logging and debugging.
        """
        data = self.dict()

        # Mask sensitive fields
        sensitive_fields = [
            "emr_client_secret",
            "openai_api_key",
            "twilio_auth_token",
            "azure_speech_key",
            "dashboard_password",
        ]

        for field in sensitive_fields:
            if field in data and data[field]:
                # Show first 4 and last 4 characters
                value = str(data[field])
                if len(value) > 8:
                    data[field] = f"{value[:4]}...{value[-4:]}"
                else:
                    data[field] = "***"

        return data

    def validate_for_startup(self) -> List[str]:
        """
        Validate settings for application startup.

        Returns:
            List of warning messages (empty if everything is OK)
        """
        warnings = []

        if self.allow_dev_defaults:
            warnings.append("Running in development mode with mock services enabled")

        if not self.openai_api_key or self.openai_api_key.get_secret_value() == "":
            warnings.append(
                "OpenAI API key not configured - NLP features will be limited"
            )

        if not self.twilio_account_sid:
            warnings.append("Twilio not configured - Voice calls will be unavailable")

        if not self.azure_speech_key or self.azure_speech_key.get_secret_value() == "":
            warnings.append(
                "Azure Speech not configured - Speech services will be unavailable"
            )

        # Enhanced security validations
        password_value = self.dashboard_password.get_secret_value()
        if password_value in ["changeme", "admin", "password", "123456", ""]:
            warnings.append(
                "🚨 SECURITY: Dashboard password is insecure - Use a strong password"
            )

        if self.dashboard_username in ["admin", "root", "user", "test"]:
            warnings.append(
                "⚠️ SECURITY: Dashboard username is predictable - Consider changing"
            )

        if self.debug and self.environment == "production":
            warnings.append(
                "🚨 SECURITY: Debug mode enabled in production - This is a security risk"
            )

        if self.environment == "production" and len(password_value) < 16:
            warnings.append(
                "⚠️ SECURITY: Dashboard password should be at least 16 characters in production"
            )

        # Check for localhost URLs in production
        if self.environment == "production":
            if "localhost" in str(self.emr_base_url):
                warnings.append(
                    "⚠️ PRODUCTION: EMR URL contains localhost - Update for production"
                )

        # Port security validation
        if self.port in [80, 443, 8000, 8080, 3000, 5000]:
            warnings.append(
                "⚠️ SECURITY: Using common port - Consider using non-standard port for security"
            )

        if self.port < 1024 and self.environment != "production":
            warnings.append(
                "ℹ️ INFO: Using privileged port - May require sudo/administrator access"
            )

        return warnings

    def get_security_score(self) -> dict:
        """
        Calculate security score based on configuration.

        Returns:
            Dict with security score (0-100) and recommendations
        """
        score = 100
        issues = []

        password_value = self.dashboard_password.get_secret_value()

        # Password strength
        if password_value in ["changeme", "admin", "password"]:
            score -= 30
            issues.append("Weak dashboard password")
        elif len(password_value) < 12:
            score -= 15
            issues.append("Dashboard password should be longer")

        # Username security
        if self.dashboard_username in ["admin", "root"]:
            score -= 10
            issues.append("Predictable dashboard username")

        # Production settings
        if self.environment == "production":
            if self.debug:
                score -= 25
                issues.append("Debug enabled in production")
            if self.allow_dev_defaults:
                score -= 20
                issues.append("Dev defaults enabled in production")

        # API key presence
        if not self.openai_api_key or self.openai_api_key.get_secret_value() == "":
            score -= 5
            issues.append("Missing OpenAI API key")

        # Port security
        if self.port in [80, 443, 8000, 8080, 3000, 5000]:
            score -= 10
            issues.append("Using common/predictable port")

        return {
            "score": max(0, score),
            "grade": "A"
            if score >= 90
            else "B"
            if score >= 80
            else "C"
            if score >= 70
            else "D"
            if score >= 60
            else "F",
            "issues": issues,
            "recommendations": self._get_security_recommendations(issues),
        }

    def _get_security_recommendations(self, issues: List[str]) -> List[str]:
        """Generate security recommendations based on issues."""
        recommendations = []

        if "Weak dashboard password" in issues:
            recommendations.append("Generate strong password: openssl rand -base64 32")
        if "Predictable dashboard username" in issues:
            recommendations.append(
                "Use organization-specific username (e.g., 'clearview_admin')"
            )
        if "Debug enabled in production" in issues:
            recommendations.append("Set DEBUG=false for production deployment")
        if "Dev defaults enabled in production" in issues:
            recommendations.append("Set ALLOW_DEV_DEFAULTS=false for production")
        if "Using common/predictable port" in issues:
            recommendations.append(
                "Use uncommon port range: 9000-9999, 10000-65535 (avoid 8000, 8080, 3000)"
            )

        return recommendations


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    This function creates a singleton Settings instance that is cached
    for the lifetime of the application.
    """
    return Settings()


# Convenience function for backward compatibility
def load_config() -> dict:
    """
    Load configuration in dictionary format for backward compatibility.

    This function helps with gradual migration from the old config.json system.
    """
    settings = get_settings()

    # Build config dict in old format
    config = {
        "practice_name": settings.practice_name,
        "emr_credentials": {
            "base_url": str(settings.emr_base_url),
            "client_id": settings.emr_client_id,
            "client_secret": settings.emr_client_secret.get_secret_value()
            if settings.emr_client_secret
            else "",
            "redirect_uri": settings.emr_redirect_uri,
        },
        "api_keys": {
            "openai_api_key": settings.openai_api_key.get_secret_value()
            if settings.openai_api_key
            else "",
            "twilio_account_sid": settings.twilio_account_sid,
            "twilio_auth_token": settings.twilio_auth_token.get_secret_value()
            if settings.twilio_auth_token
            else "",
            "azure_speech_key": settings.azure_speech_key.get_secret_value()
            if settings.azure_speech_key
            else "",
            "azure_speech_region": settings.azure_speech_region,
        },
        "operational_hours": {
            "monday": settings.get_operational_hours("monday"),
            "tuesday": settings.get_operational_hours("tuesday"),
            "wednesday": settings.get_operational_hours("wednesday"),
            "thursday": settings.get_operational_hours("thursday"),
            "friday": settings.get_operational_hours("friday"),
            "saturday": settings.get_operational_hours("saturday"),
            "sunday": settings.get_operational_hours("sunday"),
        },
        "system_settings": {
            "log_level": settings.log_level,
            "max_call_duration_minutes": settings.max_call_duration_minutes,
            "enable_audit_logging": settings.enable_audit_logging,
            "audit_log_rotation_mb": settings.audit_log_rotation_mb,
        },
    }

    return config


# Export for easy import
__all__ = ["Settings", "get_settings", "load_config"]
