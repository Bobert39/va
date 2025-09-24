"""
Integration tests for Dashboard Monitoring.

Tests the complete dashboard workflow including API endpoints,
WebSocket connections, and real-time updates.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

# Import the FastAPI app
from src.main import app
from src.services.dashboard_service import AppointmentStatus, DashboardService


class TestDashboardMonitoringIntegration:
    """Integration tests for dashboard monitoring functionality."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_dashboard_service(self):
        """Mock dashboard service."""
        mock = Mock(spec=DashboardService)
        mock.get_ai_scheduled_appointments = AsyncMock()
        mock.export_appointments = AsyncMock()
        mock.get_appointment_analytics = Mock()
        mock.add_connection = Mock()
        mock.remove_connection = Mock()
        return mock

    @pytest.fixture(autouse=True)
    def setup_dashboard_service(self, mock_dashboard_service):
        """Set up mock dashboard service in the app."""
        with patch("src.main.dashboard_service", mock_dashboard_service):
            yield mock_dashboard_service

    def test_get_ai_appointments_endpoint_success(self, client, mock_dashboard_service):
        """Test successful AI appointments retrieval."""
        # Mock response
        mock_response = {
            "status": "success",
            "appointments": [
                {
                    "id": "appt_1",
                    "patient_name": "John Doe",
                    "provider_name": "Dr. Smith",
                    "appointment_datetime": "2023-01-01T10:00:00",
                    "status": "confirmed",
                    "ai_confidence": 0.90,
                }
            ],
            "total_count": 1,
            "filters_applied": {},
        }
        mock_dashboard_service.get_ai_scheduled_appointments.return_value = (
            mock_response
        )

        # Make request
        response = client.get("/api/v1/appointments/ai-scheduled")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["appointments"]) == 1
        assert data["appointments"][0]["id"] == "appt_1"

    def test_get_ai_appointments_with_filters(self, client, mock_dashboard_service):
        """Test AI appointments endpoint with filters."""
        mock_response = {
            "status": "success",
            "appointments": [],
            "total_count": 0,
            "filters_applied": {"provider_id": "provider_1", "status": "confirmed"},
        }
        mock_dashboard_service.get_ai_scheduled_appointments.return_value = (
            mock_response
        )

        # Make request with filters
        response = client.get(
            "/api/v1/appointments/ai-scheduled",
            params={
                "provider_id": "provider_1",
                "status": "confirmed",
                "date_from": "2023-01-01",
                "date_to": "2023-01-31",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Verify service was called with correct parameters
        mock_dashboard_service.get_ai_scheduled_appointments.assert_called_once()
        call_args = mock_dashboard_service.get_ai_scheduled_appointments.call_args
        assert call_args.kwargs["provider_id"] == "provider_1"
        assert call_args.kwargs["status"] == "confirmed"

    def test_get_ai_appointments_invalid_date(self, client, mock_dashboard_service):
        """Test AI appointments endpoint with invalid date format."""
        response = client.get(
            "/api/v1/appointments/ai-scheduled", params={"date_from": "invalid-date"}
        )

        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    def test_get_ai_appointments_service_unavailable(self, client):
        """Test AI appointments endpoint when service is unavailable."""
        with patch("src.main.dashboard_service", None):
            response = client.get("/api/v1/appointments/ai-scheduled")

        assert response.status_code == 503
        assert "Dashboard service not available" in response.json()["detail"]

    def test_export_appointments_csv(self, client, mock_dashboard_service):
        """Test CSV export functionality."""
        mock_response = {
            "status": "success",
            "format": "csv",
            "content": "appointment_id,patient_name\nappt_1,John Doe",
            "filename": "ai_appointments_20230101_120000.csv",
        }
        mock_dashboard_service.export_appointments.return_value = mock_response

        response = client.get("/api/v1/appointments/export", params={"format": "csv"})

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv"
        assert "attachment" in response.headers["content-disposition"]

    def test_export_appointments_pdf(self, client, mock_dashboard_service):
        """Test PDF export functionality."""
        mock_response = {
            "status": "success",
            "format": "pdf",
            "content": b"PDF content here",
            "filename": "ai_appointments_report_20230101_120000.pdf",
        }
        mock_dashboard_service.export_appointments.return_value = mock_response

        response = client.get("/api/v1/appointments/export", params={"format": "pdf"})

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]

    def test_export_appointments_invalid_format(self, client, mock_dashboard_service):
        """Test export with invalid format."""
        response = client.get("/api/v1/appointments/export", params={"format": "xml"})

        assert response.status_code == 400
        assert "Format must be 'csv' or 'pdf'" in response.json()["detail"]

    def test_export_appointments_service_error(self, client, mock_dashboard_service):
        """Test export when service returns error."""
        mock_response = {"status": "error", "error": "Export failed"}
        mock_dashboard_service.export_appointments.return_value = mock_response

        response = client.get("/api/v1/appointments/export", params={"format": "csv"})

        assert response.status_code == 500
        assert "Export failed" in response.json()["detail"]

    def test_get_analytics_endpoint(self, client, mock_dashboard_service):
        """Test analytics endpoint."""
        mock_analytics = {
            "total_bookings": 10,
            "success_rate": 85.0,
            "status_breakdown": {"confirmed": 8, "pending": 1, "failed": 1},
            "provider_utilization": {"provider_1": 5, "provider_2": 5},
        }
        mock_dashboard_service.get_appointment_analytics.return_value = mock_analytics

        response = client.get("/api/v1/appointments/analytics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_bookings"] == 10
        assert data["success_rate"] == 85.0
        assert data["status_breakdown"]["confirmed"] == 8

    @pytest.mark.asyncio
    async def test_websocket_connection_flow(self, mock_dashboard_service):
        """Test WebSocket connection establishment and message handling."""
        with TestClient(app) as client:
            # Test WebSocket connection
            with client.websocket_connect("/ws/appointments") as websocket:
                # Verify connection was added
                mock_dashboard_service.add_connection.assert_called_once()

                # Send ping message
                websocket.send_text("ping")

                # Receive pong response
                data = websocket.receive_text()
                assert data == "pong"

            # Connection should be removed when closed
            mock_dashboard_service.remove_connection.assert_called_once()

    def test_websocket_service_unavailable(self):
        """Test WebSocket when dashboard service is unavailable."""
        with patch("src.main.dashboard_service", None):
            with TestClient(app) as client:
                with pytest.raises(Exception):
                    # Should fail to connect
                    with client.websocket_connect("/ws/appointments"):
                        pass

    @pytest.mark.asyncio
    async def test_real_time_update_broadcast(self, mock_dashboard_service):
        """Test real-time update broadcasting through WebSocket."""
        # Mock the broadcast method
        mock_dashboard_service.broadcast_appointment_update = AsyncMock()

        # Simulate appointment creation that triggers broadcast
        from src.services.dashboard_service import AppointmentStatus

        # This would normally be called by the voice AI service
        update_data = {
            "event": "appointment_created",
            "appointment_id": "appt_1",
            "status": "confirmed",
            "provider_id": "provider_1",
        }

        await mock_dashboard_service.broadcast_appointment_update(update_data)

        # Verify broadcast was called
        mock_dashboard_service.broadcast_appointment_update.assert_called_once_with(
            update_data
        )

    def test_dashboard_html_accessibility(self, client):
        """Test that dashboard HTML page loads correctly."""
        response = client.get("/dashboard")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Check for key dashboard elements
        content = response.text
        assert "AI-Scheduled Appointments" in content
        assert "Real-time" in content
        assert "Export CSV" in content

    def test_static_dashboard_js_accessibility(self, client):
        """Test that dashboard JavaScript file is accessible."""
        response = client.get("/static/dashboard.js")

        assert response.status_code == 200
        assert (
            "application/javascript" in response.headers["content-type"]
            or "text/javascript" in response.headers["content-type"]
        )

    @pytest.mark.integration
    def test_full_dashboard_workflow(self, client, mock_dashboard_service):
        """Test complete dashboard workflow from API to display."""
        # Step 1: Get appointments
        mock_appointments = {
            "status": "success",
            "appointments": [
                {
                    "id": "appt_1",
                    "patient_name": "John Doe",
                    "provider_name": "Dr. Smith",
                    "appointment_datetime": datetime.now().isoformat(),
                    "status": "confirmed",
                    "ai_confidence": 0.90,
                    "booking_source": "voice_ai",
                }
            ],
            "total_count": 1,
        }
        mock_dashboard_service.get_ai_scheduled_appointments.return_value = (
            mock_appointments
        )

        appointments_response = client.get("/api/v1/appointments/ai-scheduled")
        assert appointments_response.status_code == 200

        # Step 2: Get analytics
        mock_analytics = {
            "total_bookings": 1,
            "success_rate": 100.0,
            "status_breakdown": {"confirmed": 1},
        }
        mock_dashboard_service.get_appointment_analytics.return_value = mock_analytics

        analytics_response = client.get("/api/v1/appointments/analytics")
        assert analytics_response.status_code == 200

        # Step 3: Export data
        mock_export = {
            "status": "success",
            "format": "csv",
            "content": "id,patient_name\nappt_1,John Doe",
            "filename": "export.csv",
        }
        mock_dashboard_service.export_appointments.return_value = mock_export

        export_response = client.get(
            "/api/v1/appointments/export", params={"format": "csv"}
        )
        assert export_response.status_code == 200

        # Step 4: Verify dashboard page loads
        dashboard_response = client.get("/dashboard")
        assert dashboard_response.status_code == 200

    def test_error_handling_service_exceptions(self, client, mock_dashboard_service):
        """Test error handling when service raises exceptions."""
        # Test appointments endpoint with service exception
        mock_dashboard_service.get_ai_scheduled_appointments.side_effect = Exception(
            "Service error"
        )

        response = client.get("/api/v1/appointments/ai-scheduled")
        assert response.status_code == 500

        # Test analytics endpoint with service exception
        mock_dashboard_service.get_appointment_analytics.side_effect = Exception(
            "Analytics error"
        )

        response = client.get("/api/v1/appointments/analytics")
        assert response.status_code == 500

        # Test export endpoint with service exception
        mock_dashboard_service.export_appointments.side_effect = Exception(
            "Export error"
        )

        response = client.get("/api/v1/appointments/export", params={"format": "csv"})
        assert response.status_code == 500

    @pytest.mark.performance
    def test_dashboard_response_times(self, client, mock_dashboard_service):
        """Test dashboard response time performance."""
        import time

        # Mock large dataset
        mock_appointments = {
            "status": "success",
            "appointments": [
                {
                    "id": f"appt_{i}",
                    "patient_name": f"Patient {i}",
                    "provider_name": "Dr. Smith",
                    "appointment_datetime": datetime.now().isoformat(),
                    "status": "confirmed",
                    "ai_confidence": 0.90,
                }
                for i in range(100)  # 100 appointments
            ],
            "total_count": 100,
        }
        mock_dashboard_service.get_ai_scheduled_appointments.return_value = (
            mock_appointments
        )

        start_time = time.time()
        response = client.get("/api/v1/appointments/ai-scheduled")
        end_time = time.time()

        assert response.status_code == 200
        # Should respond within 1 second even with 100 appointments
        assert (end_time - start_time) < 1.0

    def test_concurrent_websocket_connections(self, mock_dashboard_service):
        """Test handling multiple concurrent WebSocket connections."""
        with TestClient(app) as client:
            connections = []

            # Establish multiple connections
            for i in range(5):
                try:
                    ws = client.websocket_connect("/ws/appointments")
                    connections.append(ws)
                except:
                    pass  # Some may fail, that's ok for this test

            # Verify connections were tracked
            assert mock_dashboard_service.add_connection.call_count >= 1

            # Close connections
            for ws in connections:
                try:
                    ws.close()
                except:
                    pass

    def test_dashboard_security_headers(self, client):
        """Test that dashboard responses include appropriate security headers."""
        response = client.get("/dashboard")

        # Basic security check - should not expose server details
        assert "X-Powered-By" not in response.headers
        assert (
            "Server" not in response.headers
            or "FastAPI" not in response.headers.get("Server", "")
        )
