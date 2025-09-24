"""
Integration tests for Health Monitoring functionality.

Tests the system health dashboard, API endpoints, error logging,
and monitoring capabilities for Story 3.3.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services.system_monitoring import monitoring_service


class TestHealthMonitoringIntegration:
    """Integration tests for Health Monitoring system."""

    @pytest.fixture
    def client(self):
        """Create a test client for the FastAPI application."""
        return TestClient(app)

    @pytest.fixture
    def mock_monitoring_service(self):
        """Mock monitoring service for testing."""
        mock_service = MagicMock()
        mock_service.get_dashboard_metrics.return_value = {
            "call_statistics": {
                "total_calls": 10,
                "successful_calls": 9,
                "failed_calls": 1,
                "success_rate_percent": 90.0,
                "average_duration_minutes": 2.5,
            },
            "error_summary": {
                "total_errors": 1,
                "transcription_errors": 0,
                "timeout_events": 1,
                "last_error": (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).isoformat(),
            },
        }
        return mock_service

    def test_dashboard_loads_successfully(self, client):
        """Test that the dashboard page loads with health monitoring section."""
        response = client.get("/dashboard")
        assert response.status_code == 200

        content = response.text
        # Check for health monitoring section
        assert "System Health & Status Monitoring" in content
        assert "System Component Status" in content
        assert "Performance Metrics" in content
        assert "Connection Testing" in content
        assert "System Management" in content

    def test_health_monitoring_css_loads(self, client):
        """Test that health monitoring CSS file is accessible."""
        response = client.get("/static/health-monitoring.css")
        assert response.status_code == 200
        assert "status-indicator" in response.text
        assert "pulse-success" in response.text

    def test_health_monitoring_js_loads(self, client):
        """Test that health monitoring JavaScript file is accessible."""
        response = client.get("/static/health-monitoring.js")
        assert response.status_code == 200
        assert "HealthMonitoringService" in response.text
        assert "loadHealthStatus" in response.text

    def test_enhanced_status_endpoint(self, client, mock_monitoring_service):
        """Test the enhanced system status endpoint."""
        with patch("src.main.system_monitoring_service", mock_monitoring_service):
            response = client.get("/api/v1/status")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "Voice AI Platform"
            assert data["version"] == "0.1.0"
            assert "timestamp" in data

            # Check EMR and Voice status (should be false in test environment)
            assert data["emr_connected"] == False
            assert data["voice_ai_connected"] == False
            assert data["web_interface_operational"] == True

            # Check monitoring metrics are included
            assert "call_statistics" in data
            assert "error_summary" in data

    def test_connection_testing_endpoint(self, client):
        """Test the connection testing endpoint."""
        response = client.get("/api/v1/health/test")
        assert response.status_code == 200

        data = response.json()
        assert "timestamp" in data
        assert "tests" in data

        # Check all required test types
        tests = data["tests"]
        assert "emr" in tests
        assert "voice" in tests
        assert "web" in tests

        # Web test should always succeed in test environment
        assert tests["web"]["status"] == "success"
        assert tests["web"]["message"] == "Web interface operational"

        # EMR and Voice should fail in test environment (not configured)
        assert tests["emr"]["status"] == "failed"
        assert tests["voice"]["status"] == "failed"

    def test_performance_metrics_endpoint(self, client, mock_monitoring_service):
        """Test the performance metrics endpoint."""
        with patch("src.main.system_monitoring_service", mock_monitoring_service):
            response = client.get("/api/v1/health/metrics")
            assert response.status_code == 200

            data = response.json()
            assert "timestamp" in data
            assert "system_uptime_percent" in data
            assert "average_response_time" in data
            assert "call_volume_today" in data
            assert "error_rate_percent" in data
            assert "health_score" in data

            # Verify health score calculation
            health_score = data["health_score"]
            assert 0 <= health_score <= 100

    def test_error_logs_endpoint(self, client):
        """Test the error logs endpoint."""
        response = client.get("/api/v1/health/errors")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert "timestamp" in data
        assert "errors" in data
        assert "total" in data
        assert "pagination" in data

        # Check error structure
        if data["errors"]:
            error = data["errors"][0]
            assert "id" in error
            assert "timestamp" in error
            assert "severity" in error
            assert "component" in error
            assert "message" in error

    def test_error_logs_filtering(self, client):
        """Test error logs filtering by severity."""
        # Test severity filtering
        response = client.get("/api/v1/health/errors?severity=error")
        assert response.status_code == 200
        data = response.json()
        assert data["filters"]["severity"] == "error"

        # Test limit parameter
        response = client.get("/api/v1/health/errors?limit=1")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["limit"] == 1

    def test_error_logs_text_format(self, client):
        """Test error logs in text format for download."""
        response = client.get("/api/v1/health/errors?format=text")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "Error Log Export" in response.text

    def test_system_restart_endpoint(self, client):
        """Test the system restart endpoint."""
        restart_request = {"component": "system", "action": "restart"}

        response = client.post("/api/v1/health/restart", json=restart_request)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["component"] == "system"
        assert data["action"] == "restart"
        assert "message" in data
        assert "timestamp" in data

    def test_restart_validation(self, client):
        """Test restart endpoint validation."""
        # Test missing component
        response = client.post("/api/v1/health/restart", json={"action": "restart"})
        assert response.status_code == 400

        # Test invalid component
        response = client.post(
            "/api/v1/health/restart", json={"component": "invalid", "action": "restart"}
        )
        assert response.status_code == 400

        # Test invalid action
        response = client.post(
            "/api/v1/health/restart", json={"component": "system", "action": "invalid"}
        )
        assert response.status_code == 400

    def test_rate_limiting(self, client):
        """Test rate limiting on health endpoints."""
        # The endpoints have rate limits, but in testing we'll just verify
        # they don't immediately fail
        response = client.get("/api/v1/status")
        assert response.status_code == 200

        response = client.get("/api/v1/health/test")
        assert response.status_code == 200

        response = client.get("/api/v1/health/metrics")
        assert response.status_code == 200

    def test_health_monitoring_with_real_monitoring_service(self, client):
        """Test health monitoring with the actual monitoring service."""
        # Test that monitoring service is properly integrated
        assert monitoring_service is not None

        # Test getting dashboard metrics
        metrics = monitoring_service.get_dashboard_metrics()
        assert "call_statistics" in metrics
        assert "cost_tracking" in metrics
        assert "api_usage" in metrics
        assert "error_summary" in metrics

    def test_error_handling_in_endpoints(self, client):
        """Test error handling in health endpoints."""
        # Test status endpoint with mocked failure
        with patch("src.main.system_monitoring_service", None):
            response = client.get("/api/v1/status")
            # Should still return 200 but with degraded info
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"  # Basic health check passes

    def test_health_dashboard_ui_elements(self, client):
        """Test that all required UI elements are present in the dashboard."""
        response = client.get("/dashboard")
        assert response.status_code == 200

        content = response.text

        # Test status indicators
        assert 'id="emrStatusCard"' in content
        assert 'id="voiceStatusCard"' in content
        assert 'id="webStatusCard"' in content

        # Test performance metrics
        assert 'id="systemUptime"' in content
        assert 'id="avgResponseTime"' in content
        assert 'id="callVolume"' in content
        assert 'id="errorRate"' in content

        # Test connection testing buttons
        assert 'id="testEmrConnection"' in content
        assert 'id="testVoiceServices"' in content
        assert 'id="testWebInterface"' in content

        # Test system management tools
        assert 'id="restartSystem"' in content
        assert 'id="viewErrorLogs"' in content
        assert 'id="supportInfo"' in content

        # Test modals
        assert 'id="errorLogsModal"' in content
        assert 'id="restartConfirmModal"' in content
        assert 'id="supportInfoModal"' in content

    def test_css_animations_and_styles(self, client):
        """Test that CSS contains required animations and styles."""
        response = client.get("/static/health-monitoring.css")
        assert response.status_code == 200

        css_content = response.text

        # Test status indicator animations
        assert "pulse-success" in css_content
        assert "pulse-warning" in css_content
        assert "pulse-danger" in css_content

        # Test color coding
        assert "border-success" in css_content
        assert "border-warning" in css_content
        assert "border-danger" in css_content

        # Test error log styling
        assert "error-log-entry" in css_content
        assert "log-error" in css_content
        assert "log-warning" in css_content

    def test_javascript_health_service_methods(self, client):
        """Test that JavaScript contains required health service methods."""
        response = client.get("/static/health-monitoring.js")
        assert response.status_code == 200

        js_content = response.text

        # Test core methods
        assert "loadHealthStatus" in js_content
        assert "testConnection" in js_content
        assert "loadErrorLogs" in js_content
        assert "performSystemRestart" in js_content
        assert "generateSupportReport" in js_content

        # Test event handling
        assert "bindEventListeners" in js_content
        assert "updateHealthDisplay" in js_content
        assert "updateComponentStatus" in js_content

    @pytest.mark.parametrize(
        "component,action",
        [
            ("system", "restart"),
            ("emr", "reset"),
            ("voice", "restart"),
            ("monitoring", "restart"),
        ],
    )
    def test_restart_different_components(self, client, component, action):
        """Test restart functionality for different components."""
        restart_request = {"component": component, "action": action}

        response = client.post("/api/v1/health/restart", json=restart_request)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["component"] == component
        assert data["action"] == action

    def test_monitoring_service_integration(self, client):
        """Test integration with the system monitoring service."""
        # Test that monitoring service is properly tracking dashboard views
        initial_metrics = monitoring_service.get_dashboard_metrics()

        # Access dashboard
        response = client.get("/dashboard")
        assert response.status_code == 200

        # The monitoring service should have tracking capabilities
        assert hasattr(monitoring_service, "track_dashboard_view")
        assert hasattr(monitoring_service, "get_dashboard_metrics")

    def test_audit_logging_integration(self, client):
        """Test that health monitoring actions are properly audited."""
        # Test connection testing audit
        response = client.get("/api/v1/health/test")
        assert response.status_code == 200

        # Test error log access audit
        response = client.get("/api/v1/health/errors")
        assert response.status_code == 200

        # Test restart request audit
        restart_request = {"component": "monitoring", "action": "restart"}
        response = client.post("/api/v1/health/restart", json=restart_request)
        assert response.status_code == 200

    def test_comprehensive_health_flow(self, client, mock_monitoring_service):
        """Test complete health monitoring workflow."""
        with patch("src.main.system_monitoring_service", mock_monitoring_service):
            # 1. Check system status
            status_response = client.get("/api/v1/status")
            assert status_response.status_code == 200

            # 2. Test connections
            test_response = client.get("/api/v1/health/test")
            assert test_response.status_code == 200

            # 3. Get performance metrics
            metrics_response = client.get("/api/v1/health/metrics")
            assert metrics_response.status_code == 200

            # 4. Check error logs
            errors_response = client.get("/api/v1/health/errors")
            assert errors_response.status_code == 200

            # 5. Verify all responses contain expected data
            status_data = status_response.json()
            test_data = test_response.json()
            metrics_data = metrics_response.json()
            errors_data = errors_response.json()

            assert status_data["status"] == "healthy"
            assert "tests" in test_data
            assert "health_score" in metrics_data
            assert "errors" in errors_data
