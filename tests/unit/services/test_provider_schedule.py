"""
Unit tests for Provider Schedule Service.

This module tests the provider schedule service functionality including provider
listing, schedule retrieval, availability calculation, and data quality validation.
"""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from src.services.emr import EMROAuthClient, NetworkError, OAuthError, TokenExpiredError
from src.services.provider_schedule import (
    Provider,
    ProviderNotFoundError,
    ProviderScheduleError,
    ProviderScheduleService,
    Schedule,
    ScheduleNotFoundError,
    ScheduleStatus,
    ScheduleValidationError,
    Slot,
    SlotStatus,
)
from src.services.schedule_refresh import RefreshStatus, ScheduleRefreshService


class TestProvider:
    """Test the Provider class."""

    def test_provider_initialization(self):
        """Test provider initialization with valid data."""
        provider_data = {
            "id": "123",
            "resourceType": "Practitioner",
            "active": True,
            "name": [{"given": ["John", "Robert"], "family": "Smith"}],
            "qualification": [
                {"code": {"coding": [{"display": "MD - Doctor of Medicine"}]}}
            ],
        }

        provider = Provider(provider_data)

        assert provider.id == "123"
        assert provider.active is True
        assert provider.name == "John Robert Smith"
        assert provider.qualification == ["MD - Doctor of Medicine"]

    def test_provider_minimal_data(self):
        """Test provider with minimal data."""
        provider_data = {"id": "456", "resourceType": "Practitioner"}

        provider = Provider(provider_data)

        assert provider.id == "456"
        assert provider.active is True
        assert provider.name == "Unknown Provider"
        assert provider.qualification == []

    def test_provider_to_dict(self):
        """Test provider to_dict conversion."""
        provider_data = {
            "id": "789",
            "active": False,
            "name": [{"given": ["Jane"], "family": "Doe"}],
            "qualification": [],
        }

        provider = Provider(provider_data)
        provider_dict = provider.to_dict()

        assert provider_dict["id"] == "789"
        assert provider_dict["active"] is False
        assert provider_dict["name"] == "Jane Doe"
        assert provider_dict["qualification"] == []


class TestSchedule:
    """Test the Schedule class."""

    def test_schedule_initialization(self):
        """Test schedule initialization with valid data."""
        schedule_data = {
            "id": "schedule-123",
            "resourceType": "Schedule",
            "status": "active",
            "serviceCategory": [{"coding": [{"display": "General Medicine"}]}],
            "serviceType": [{"coding": [{"display": "Consultation"}]}],
            "specialty": [{"coding": [{"display": "Internal Medicine"}]}],
            "actor": [{"reference": "Practitioner/123"}],
            "planningHorizon": {
                "start": "2024-01-01T00:00:00Z",
                "end": "2024-12-31T23:59:59Z",
            },
            "comment": "Regular schedule",
        }

        schedule = Schedule(schedule_data)

        assert schedule.id == "schedule-123"
        assert schedule.status == "active"
        assert schedule.service_category == "General Medicine"
        assert schedule.service_type == "Consultation"
        assert schedule.specialty == "Internal Medicine"
        assert schedule.get_practitioner_reference() == "Practitioner/123"
        assert schedule.comment == "Regular schedule"

    def test_schedule_minimal_data(self):
        """Test schedule with minimal data."""
        schedule_data = {"id": "schedule-456", "resourceType": "Schedule"}

        schedule = Schedule(schedule_data)

        assert schedule.id == "schedule-456"
        assert schedule.status is None
        assert schedule.service_category is None
        assert schedule.get_practitioner_reference() is None


class TestSlot:
    """Test the Slot class."""

    def test_slot_initialization(self):
        """Test slot initialization with valid data."""
        slot_data = {
            "id": "slot-123",
            "resourceType": "Slot",
            "status": "free",
            "start": "2024-01-15T10:00:00Z",
            "end": "2024-01-15T10:30:00Z",
            "serviceCategory": [{"coding": [{"display": "General Medicine"}]}],
            "schedule": {"reference": "Schedule/schedule-123"},
            "comment": "Available slot",
        }

        slot = Slot(slot_data)

        assert slot.id == "slot-123"
        assert slot.status == "free"
        assert slot.start == "2024-01-15T10:00:00Z"
        assert slot.end == "2024-01-15T10:30:00Z"
        assert slot.service_category == "General Medicine"
        assert slot.schedule_reference == "Schedule/schedule-123"
        assert slot.comment == "Available slot"

    def test_slot_to_dict(self):
        """Test slot to_dict conversion."""
        slot_data = {
            "id": "slot-456",
            "status": "busy",
            "start": "2024-01-15T14:00:00Z",
            "end": "2024-01-15T14:30:00Z",
        }

        slot = Slot(slot_data)
        slot_dict = slot.to_dict()

        assert slot_dict["id"] == "slot-456"
        assert slot_dict["status"] == "busy"
        assert slot_dict["start"] == "2024-01-15T14:00:00Z"
        assert slot_dict["end"] == "2024-01-15T14:30:00Z"


class TestProviderScheduleService:
    """Test the ProviderScheduleService class."""

    @pytest.fixture
    def mock_oauth_client(self):
        """Create a mock OAuth client."""
        client = Mock(spec=EMROAuthClient)
        client._get_oauth_config.return_value = {
            "fhir_base_url": "https://test-emr.example.com/fhir"
        }
        client.get_valid_access_token.return_value = "mock-access-token"
        return client

    @pytest.fixture
    def service(self, mock_oauth_client):
        """Create a ProviderScheduleService instance."""
        return ProviderScheduleService(mock_oauth_client)

    @pytest.fixture
    def mock_providers_response(self):
        """Mock response for providers list."""
        return {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "id": "123",
                        "resourceType": "Practitioner",
                        "active": True,
                        "name": [{"given": ["John"], "family": "Smith"}],
                    }
                },
                {
                    "resource": {
                        "id": "456",
                        "resourceType": "Practitioner",
                        "active": True,
                        "name": [{"given": ["Jane"], "family": "Doe"}],
                    }
                },
            ],
        }

    @pytest.fixture
    def mock_schedules_response(self):
        """Mock response for schedules list."""
        return {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "id": "schedule-123",
                        "resourceType": "Schedule",
                        "status": "active",
                        "actor": [{"reference": "Practitioner/123"}],
                    }
                },
                {
                    "resource": {
                        "id": "schedule-456",
                        "resourceType": "Schedule",
                        "status": "active",
                        "actor": [{"reference": "Practitioner/456"}],
                    }
                },
            ],
        }

    @pytest.fixture
    def mock_slots_response(self):
        """Mock response for slots list."""
        return {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "id": "slot-123",
                        "resourceType": "Slot",
                        "status": "free",
                        "start": "2024-01-15T10:00:00Z",
                        "end": "2024-01-15T10:30:00Z",
                        "schedule": {"reference": "Schedule/schedule-123"},
                    }
                },
                {
                    "resource": {
                        "id": "slot-456",
                        "resourceType": "Slot",
                        "status": "free",
                        "start": "2024-01-15T14:00:00Z",
                        "end": "2024-01-15T14:30:00Z",
                        "schedule": {"reference": "Schedule/schedule-123"},
                    }
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_get_providers_success(self, service, mock_providers_response):
        """Test successful provider retrieval."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_providers_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            providers = await service.get_providers()

            assert len(providers) == 2
            assert providers[0].id == "123"
            assert providers[0].name == "John Smith"
            assert providers[1].id == "456"
            assert providers[1].name == "Jane Doe"

    @pytest.mark.asyncio
    async def test_get_providers_empty_response(self, service):
        """Test provider retrieval with empty response."""
        empty_response = {"resourceType": "Bundle", "entry": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = empty_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            providers = await service.get_providers()

            assert len(providers) == 0

    @pytest.mark.asyncio
    async def test_get_providers_authentication_error(self, service, mock_oauth_client):
        """Test provider retrieval with authentication error."""
        mock_oauth_client.get_valid_access_token.side_effect = OAuthError(
            "invalid_token", "Token expired"
        )

        with pytest.raises(ProviderScheduleError) as exc_info:
            await service.get_providers()

        assert "Authentication failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_provider_schedules_success(
        self, service, mock_schedules_response
    ):
        """Test successful schedule retrieval."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_schedules_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            schedules = await service.get_provider_schedules(
                practitioner_reference="Practitioner/123",
                start_date="2024-01-01T00:00:00Z",
                end_date="2024-01-31T23:59:59Z",
            )

            assert len(schedules) == 2
            assert schedules[0].id == "schedule-123"
            assert schedules[0].get_practitioner_reference() == "Practitioner/123"

    @pytest.mark.asyncio
    async def test_get_provider_schedules_cached(
        self, service, mock_schedules_response
    ):
        """Test schedule retrieval uses cache on subsequent calls."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_schedules_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            # First call
            schedules1 = await service.get_provider_schedules(
                practitioner_reference="Practitioner/123"
            )

            # Second call should use cache
            schedules2 = await service.get_provider_schedules(
                practitioner_reference="Practitioner/123"
            )

            # Should only make one HTTP request
            assert mock_client.return_value.__aenter__.return_value.get.call_count == 1
            assert len(schedules1) == len(schedules2) == 2

    @pytest.mark.asyncio
    async def test_get_available_slots_success(self, service, mock_slots_response):
        """Test successful slot retrieval."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_slots_response
            mock_response.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            slots = await service.get_available_slots(
                schedule_reference="Schedule/schedule-123",
                start_date="2024-01-15T00:00:00Z",
                end_date="2024-01-15T23:59:59Z",
            )

            assert len(slots) == 2
            assert slots[0].id == "slot-123"
            assert slots[0].status == "free"
            assert slots[0].schedule_reference == "Schedule/schedule-123"

    @pytest.mark.asyncio
    async def test_get_provider_availability_comprehensive(
        self, service, mock_schedules_response, mock_slots_response
    ):
        """Test comprehensive provider availability calculation."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock both schedule and slot requests
            mock_response_schedule = Mock()
            mock_response_schedule.status_code = 200
            mock_response_schedule.json.return_value = mock_schedules_response
            mock_response_schedule.raise_for_status.return_value = None

            mock_response_slots = Mock()
            mock_response_slots.status_code = 200
            mock_response_slots.json.return_value = mock_slots_response
            mock_response_slots.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get.side_effect = [
                mock_response_schedule,
                mock_response_slots,
                mock_response_slots,
            ]

            availability = await service.get_provider_availability(
                practitioner_reference="Practitioner/123",
                start_date="2024-01-15T00:00:00Z",
                end_date="2024-01-15T23:59:59Z",
            )

            assert availability["practitioner_reference"] == "Practitioner/123"
            assert availability["availability_summary"]["total_schedules"] == 2
            assert availability["availability_summary"]["total_available_slots"] == 4
            assert availability["availability_summary"]["has_availability"] is True
            assert "working_hours" in availability
            assert "breaks" in availability
            assert "data_quality" in availability

    def test_schedule_data_validation_duplicates(self, service):
        """Test schedule data validation removes duplicates."""
        schedules = [
            Schedule(
                {
                    "id": "1",
                    "status": "active",
                    "actor": [{"reference": "Practitioner/123"}],
                }
            ),
            Schedule(
                {
                    "id": "1",
                    "status": "active",
                    "actor": [{"reference": "Practitioner/123"}],
                }
            ),  # Duplicate
            Schedule(
                {
                    "id": "2",
                    "status": "active",
                    "actor": [{"reference": "Practitioner/456"}],
                }
            ),
        ]

        validated = service._validate_schedule_data(schedules)

        assert len(validated) == 2
        assert service._duplicate_count == 1

    def test_schedule_data_validation_invalid_data(self, service):
        """Test schedule data validation removes invalid schedules."""
        schedules = [
            Schedule(
                {
                    "id": "1",
                    "status": "active",
                    "actor": [{"reference": "Practitioner/123"}],
                }
            ),
            Schedule(
                {
                    "id": "",
                    "status": "active",
                    "actor": [{"reference": "Practitioner/456"}],
                }
            ),  # Invalid: no ID
            Schedule(
                {"id": "3", "status": "", "actor": [{"reference": "Practitioner/789"}]}
            ),  # Invalid: no status
        ]

        validated = service._validate_schedule_data(schedules)

        assert len(validated) == 1
        assert service._validation_errors == 2

    def test_slot_data_validation(self, service):
        """Test slot data validation."""
        slots = [
            Slot(
                {
                    "id": "1",
                    "status": "free",
                    "start": "2024-01-15T10:00:00Z",
                    "end": "2024-01-15T10:30:00Z",
                }
            ),
            Slot(
                {
                    "id": "",  # Invalid: no ID
                    "status": "free",
                    "start": "2024-01-15T11:00:00Z",
                    "end": "2024-01-15T11:30:00Z",
                }
            ),
            Slot(
                {
                    "id": "3",
                    "status": "free",
                    "start": "2024-01-15T12:30:00Z",
                    "end": "2024-01-15T12:00:00Z",  # Invalid: end before start
                }
            ),
        ]

        validated = service._validate_slot_data(slots)

        assert len(validated) == 1
        assert service._validation_errors == 2

    def test_identify_breaks(self, service):
        """Test break identification from slot gaps."""
        slots = [
            Slot(
                {
                    "id": "1",
                    "start": "2024-01-15T09:00:00Z",
                    "end": "2024-01-15T10:00:00Z",
                }
            ),
            Slot(
                {
                    "id": "2",
                    "start": "2024-01-15T10:30:00Z",  # 30-minute gap
                    "end": "2024-01-15T11:30:00Z",
                }
            ),
            Slot(
                {
                    "id": "3",
                    "start": "2024-01-15T13:00:00Z",  # 1.5-hour gap (lunch break)
                    "end": "2024-01-15T14:00:00Z",
                }
            ),
        ]

        breaks = service._identify_breaks(slots)

        assert len(breaks) == 2
        assert breaks[0]["duration_minutes"] == 30
        assert breaks[1]["duration_minutes"] == 90

    def test_consolidate_working_hours(self, service):
        """Test working hours consolidation by date."""
        working_hours = [
            {
                "start": "2024-01-15T09:00:00Z",
                "end": "2024-01-15T12:00:00Z",
                "date": "2024-01-15",
            },
            {
                "start": "2024-01-15T13:00:00Z",
                "end": "2024-01-15T17:00:00Z",
                "date": "2024-01-15",
            },
            {
                "start": "2024-01-16T08:00:00Z",
                "end": "2024-01-16T16:00:00Z",
                "date": "2024-01-16",
            },
        ]

        consolidated = service._consolidate_working_hours(working_hours)

        assert len(consolidated) == 2
        assert len(consolidated["2024-01-15"]) == 2
        assert len(consolidated["2024-01-16"]) == 1

    def test_data_quality_report(self, service):
        """Test data quality report generation."""
        # Add some test data quality issues
        service._data_quality_issues = [
            {"type": "duplicate_schedule", "schedule_id": "1"},
            {"type": "invalid_slot_data", "slot_id": "2"},
            {"type": "duplicate_schedule", "schedule_id": "3"},
        ]
        service._duplicate_count = 2
        service._validation_errors = 1

        report = service.get_data_quality_report()

        assert report["total_issues"] == 3
        assert report["duplicate_count"] == 2
        assert report["validation_errors"] == 1
        assert report["issue_types"]["duplicate_schedule"] == 2
        assert report["issue_types"]["invalid_slot_data"] == 1

    def test_cache_management(self, service):
        """Test cache management functionality."""
        # Add test data to cache
        service._schedule_cache["test_key"] = ["test_data"]
        service._schedule_cache_time["test_key"] = time.time()

        cache_info = service.get_cache_info()
        assert cache_info["cache_size"] == 1
        assert cache_info["valid_entries"] == 1

        # Clear cache
        service.clear_schedule_cache()
        cache_info_after = service.get_cache_info()
        assert cache_info_after["cache_size"] == 0

    @pytest.mark.asyncio
    async def test_network_error_retry(self, service):
        """Test network error retry logic."""
        with patch("httpx.AsyncClient") as mock_client:
            # First two attempts fail, third succeeds
            mock_response_fail = Mock()
            mock_response_fail.raise_for_status.side_effect = httpx.TimeoutException(
                "Timeout"
            )

            mock_response_success = Mock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {
                "resourceType": "Bundle",
                "entry": [],
            }
            mock_response_success.raise_for_status.return_value = None

            mock_client.return_value.__aenter__.return_value.get.side_effect = [
                mock_response_fail,
                mock_response_fail,
                mock_response_success,
            ]

            providers = await service.get_providers()

            # Should succeed after retries
            assert len(providers) == 0
            assert mock_client.return_value.__aenter__.return_value.get.call_count == 3

    @pytest.mark.asyncio
    async def test_404_error_handling(self, service):
        """Test 404 error handling."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found", request=Mock(), response=mock_response
            )

            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            with pytest.raises(ProviderNotFoundError):
                await service.get_providers()


class TestScheduleRefreshService:
    """Test the ScheduleRefreshService class."""

    @pytest.fixture
    def mock_schedule_service(self):
        """Create a mock schedule service."""
        service = Mock(spec=ProviderScheduleService)
        service.clear_schedule_cache.return_value = None
        service.get_providers.return_value = [
            Mock(id="123", name="Dr. Smith"),
            Mock(id="456", name="Dr. Jones"),
        ]
        service.get_provider_schedules.return_value = [
            Mock(id="schedule-1"),
            Mock(id="schedule-2"),
        ]
        return service

    @pytest.fixture
    def refresh_service(self, mock_schedule_service):
        """Create a ScheduleRefreshService instance."""
        return ScheduleRefreshService(mock_schedule_service, refresh_interval_minutes=1)

    def test_refresh_service_initialization(
        self, refresh_service, mock_schedule_service
    ):
        """Test refresh service initialization."""
        assert refresh_service.schedule_service == mock_schedule_service
        assert refresh_service.refresh_interval == 60  # 1 minute in seconds
        assert refresh_service.status == RefreshStatus.IDLE
        assert refresh_service.is_running is False

    @pytest.mark.asyncio
    async def test_manual_refresh_success(self, refresh_service, mock_schedule_service):
        """Test manual refresh operation."""
        success = await refresh_service.refresh_now()

        assert success is True
        assert refresh_service.status == RefreshStatus.SUCCESS
        assert refresh_service._refresh_count == 1
        assert refresh_service._last_error is None

        # Verify service calls
        mock_schedule_service.clear_schedule_cache.assert_called_once()
        mock_schedule_service.get_providers.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_refresh_error(self, refresh_service, mock_schedule_service):
        """Test manual refresh with error."""
        mock_schedule_service.get_providers.side_effect = ProviderScheduleError(
            "Test error"
        )

        success = await refresh_service.refresh_now()

        assert success is False
        assert refresh_service.status == RefreshStatus.ERROR
        assert refresh_service._error_count == 1
        assert "Test error" in refresh_service._last_error

    @pytest.mark.asyncio
    async def test_refresh_service_start_stop(self, refresh_service):
        """Test starting and stopping refresh service."""
        # Start service
        await refresh_service.start()
        assert refresh_service.status == RefreshStatus.RUNNING
        assert refresh_service.is_running is True

        # Stop service
        await refresh_service.stop()
        assert refresh_service.status == RefreshStatus.STOPPED
        assert refresh_service.is_running is False

    def test_refresh_stats(self, refresh_service):
        """Test refresh statistics."""
        stats = refresh_service.refresh_stats

        assert stats["status"] == RefreshStatus.IDLE.value
        assert stats["refresh_count"] == 0
        assert stats["error_count"] == 0
        assert stats["refresh_interval_minutes"] == 1
        assert stats["is_running"] is False

    @pytest.mark.asyncio
    async def test_refresh_health_healthy(self, refresh_service):
        """Test health status when service is healthy."""
        # Set up healthy state
        refresh_service._last_refresh_time = time.time() - 30  # 30 seconds ago
        refresh_service._refresh_count = 10
        refresh_service._error_count = 0

        health = await refresh_service.get_refresh_health()

        assert health["is_healthy"] is True
        assert len(health["issues"]) == 0

    @pytest.mark.asyncio
    async def test_refresh_health_overdue(self, refresh_service):
        """Test health status when refresh is overdue."""
        # Set up overdue state
        refresh_service._last_refresh_time = time.time() - 120  # 2 minutes ago
        refresh_service._refresh_count = 5
        refresh_service._error_count = 0

        health = await refresh_service.get_refresh_health()

        assert health["is_healthy"] is False
        assert any("overdue" in issue for issue in health["issues"])

    @pytest.mark.asyncio
    async def test_refresh_health_high_error_rate(self, refresh_service):
        """Test health status with high error rate."""
        # Set up high error rate
        refresh_service._refresh_count = 10
        refresh_service._error_count = 3  # 30% error rate

        health = await refresh_service.get_refresh_health()

        assert health["is_healthy"] is False
        assert any("error rate" in issue for issue in health["issues"])

    def test_status_callbacks(self, refresh_service):
        """Test status change callbacks."""
        callback_calls = []

        def test_callback(status, data):
            callback_calls.append((status, data))

        refresh_service.add_status_callback(test_callback)

        # Trigger status change
        refresh_service._notify_status_change(RefreshStatus.RUNNING)

        assert len(callback_calls) == 1
        assert callback_calls[0][0] == RefreshStatus.RUNNING

        # Remove callback
        refresh_service.remove_status_callback(test_callback)
        refresh_service._notify_status_change(RefreshStatus.SUCCESS)

        # Should not have new calls
        assert len(callback_calls) == 1
