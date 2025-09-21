"""
Unit tests for FHIR Patient Search Service
"""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.emr import EMROAuthClient
from src.services.fhir_patient import (
    FHIRPatientService,
    FHIRResponseError,
    FHIRSearchError,
    NetworkError,
    PatientMatch,
    SearchCache,
)


class TestPatientMatch:
    """Test PatientMatch class functionality."""

    def test_patient_match_creation(self):
        """Test PatientMatch object creation and data extraction."""
        patient_data = {
            "id": "patient-123",
            "resourceType": "Patient",
            "name": [
                {"use": "official", "family": "Doe", "given": ["John", "William"]}
            ],
            "birthDate": "1985-06-15",
            "telecom": [
                {"system": "phone", "value": "+1-555-123-4567"},
                {"system": "email", "value": "john.doe@email.com"},
            ],
            "address": [
                {
                    "use": "home",
                    "line": ["123 Main St", "Apt 4B"],
                    "city": "Springfield",
                    "state": "IL",
                    "postalCode": "62701",
                }
            ],
        }

        match = PatientMatch(patient_data, confidence=0.85)

        assert match.id == "patient-123"
        assert match.given_name == "John William"
        assert match.family_name == "Doe"
        assert match.birth_date == "1985-06-15"
        assert match.phone == "+1-555-123-4567"
        assert match.email == "john.doe@email.com"
        assert match.confidence == 0.85

        address = match.address
        assert address["line"] == "123 Main St Apt 4B"
        assert address["city"] == "Springfield"
        assert address["state"] == "IL"
        assert address["postal_code"] == "62701"

    def test_patient_match_missing_data(self):
        """Test PatientMatch with missing optional data."""
        patient_data = {
            "id": "patient-456",
            "resourceType": "Patient",
            "name": [{"family": "Smith"}],
        }

        match = PatientMatch(patient_data, confidence=0.5)

        assert match.id == "patient-456"
        assert match.given_name is None
        assert match.family_name == "Smith"
        assert match.birth_date is None
        assert match.phone is None
        assert match.email is None
        assert match.address is None

    def test_patient_match_to_dict(self):
        """Test PatientMatch to_dict conversion."""
        patient_data = {
            "id": "patient-789",
            "name": [{"family": "Jones", "given": ["Jane"]}],
            "birthDate": "1990-03-20",
        }

        match = PatientMatch(patient_data, confidence=0.95)
        result = match.to_dict()

        expected = {
            "id": "patient-789",
            "given_name": "Jane",
            "family_name": "Jones",
            "birth_date": "1990-03-20",
            "confidence": 0.95,
            "phone": None,
            "email": None,
            "address": None,
        }

        assert result == expected


class TestSearchCache:
    """Test SearchCache functionality."""

    def test_cache_miss(self):
        """Test cache miss scenario."""
        cache = SearchCache(ttl_seconds=300)
        result = cache.get(given_name="John", family_name="Doe")
        assert result is None
        assert cache.get_stats()["misses"] == 1
        assert cache.get_stats()["hits"] == 0

    def test_cache_hit(self):
        """Test cache hit scenario."""
        cache = SearchCache(ttl_seconds=300)
        matches = [PatientMatch({"id": "123"}, 0.9)]

        # Set and get
        cache.set(matches, given_name="John", family_name="Doe")
        result = cache.get(given_name="John", family_name="Doe")

        assert result == matches
        assert cache.get_stats()["hits"] == 1
        assert cache.get_stats()["misses"] == 0

    def test_cache_expiration(self):
        """Test cache TTL expiration."""
        cache = SearchCache(ttl_seconds=0.1)  # 100ms TTL
        matches = [PatientMatch({"id": "123"}, 0.9)]

        cache.set(matches, given_name="John")

        # Should hit immediately
        result = cache.get(given_name="John")
        assert result == matches

        # Wait for expiration
        import time

        time.sleep(0.2)

        # Should miss after expiration
        result = cache.get(given_name="John")
        assert result is None
        assert cache.get_stats()["evictions"] == 1

    def test_cache_key_consistency(self):
        """Test that cache keys are consistent for same parameters."""
        cache = SearchCache()
        matches = [PatientMatch({"id": "123"}, 0.9)]

        # Set with different parameter order
        cache.set(matches, family_name="Doe", given_name="John")
        result = cache.get(given_name="John", family_name="Doe")

        assert result == matches  # Should hit despite different parameter order

    def test_cache_invalidation(self):
        """Test cache invalidation functionality."""
        cache = SearchCache()
        matches = [PatientMatch({"id": "123"}, 0.9)]

        cache.set(matches, given_name="John")
        cache.invalidate(patient_id="123")

        result = cache.get(given_name="John")
        assert result is None
        assert cache.get_stats()["evictions"] == 1


class TestFHIRPatientService:
    """Test FHIRPatientService functionality."""

    @pytest.fixture
    def mock_oauth_client(self):
        """Create mock OAuth client."""
        mock_client = MagicMock(spec=EMROAuthClient)
        mock_client.config = {"fhir_base_url": "https://emr.example.com/apis/fhir"}
        mock_client.get_auth_headers = AsyncMock(
            return_value={"Authorization": "Bearer test-token"}
        )
        return mock_client

    @pytest.fixture
    def service(self, mock_oauth_client):
        """Create FHIRPatientService instance."""
        return FHIRPatientService(mock_oauth_client)

    def test_anonymize_for_logging(self, service):
        """Test PHI anonymization for logging."""
        result = service._anonymize_for_logging("John Doe")
        assert result.startswith("[REDACTED-")
        assert len(result) == 19  # [REDACTED- + 8 chars + ]

        # Empty string
        assert service._anonymize_for_logging("") == "[empty]"
        assert service._anonymize_for_logging(None) == "[empty]"

    def test_log_phi_safe(self, service):
        """Test PHI-safe logging."""
        with patch("src.services.fhir_patient.logger.info") as mock_log:
            service._log_phi_safe(
                "info",
                "Test message",
                given_name="John",
                family_name="Doe",
                safe_param="value",
            )

            # Check that the log was called
            mock_log.assert_called_once()
            args = mock_log.call_args[0]
            log_message = args[0]

            # PHI should be redacted
            assert "John" not in log_message
            assert "Doe" not in log_message
            assert "[REDACTED-" in log_message
            # Safe param should remain
            assert "value" in log_message

    @pytest.mark.asyncio
    async def test_search_patients_success(self, service):
        """Test successful patient search."""
        mock_response = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "id": "patient-123",
                        "resourceType": "Patient",
                        "name": [
                            {"use": "official", "family": "Doe", "given": ["John"]}
                        ],
                        "birthDate": "1985-06-15",
                    }
                }
            ],
        }

        with patch.object(
            service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            results = await service.search_patients(
                given_name="John", family_name="Doe"
            )

            assert len(results) == 1
            assert results[0].id == "patient-123"
            assert results[0].given_name == "John"
            assert results[0].family_name == "Doe"
            assert results[0].confidence > 0

    @pytest.mark.asyncio
    async def test_search_patients_no_params(self, service):
        """Test search with no parameters raises error."""
        with pytest.raises(
            FHIRSearchError, match="At least one search parameter is required"
        ):
            await service.search_patients()

    @pytest.mark.asyncio
    async def test_search_patients_cached_result(self, service):
        """Test that cached results are returned without FHIR call."""
        # Pre-populate cache
        cached_matches = [PatientMatch({"id": "cached-123"}, 0.9)]
        service.cache.set(cached_matches, given_name="John", family_name="Doe")

        with patch.object(
            service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            results = await service.search_patients(
                given_name="John", family_name="Doe"
            )

            # Should not make FHIR request
            mock_request.assert_not_called()

            # Should return cached results
            assert results == cached_matches

    @pytest.mark.asyncio
    async def test_search_patients_invalid_bundle(self, service):
        """Test handling of invalid FHIR bundle response."""
        mock_response = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "invalid"}],
        }

        with patch.object(
            service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(FHIRResponseError, match="Expected Bundle"):
                await service.search_patients(given_name="John")

    @pytest.mark.asyncio
    async def test_make_fhir_request_success(self, service):
        """Test successful FHIR request."""
        mock_response_data = {"resourceType": "Bundle", "total": 1}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await service._make_fhir_request("Patient", {"name": "test"})

            assert result == mock_response_data
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_fhir_request_401_retry(self, service):
        """Test 401 error triggers token refresh and retry."""
        mock_response_data = {"resourceType": "Bundle", "total": 1}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value

            # First response: 401 error
            mock_401_response = MagicMock()
            mock_401_response.status_code = 401

            # Second response: success
            mock_success_response = MagicMock()
            mock_success_response.status_code = 200
            mock_success_response.json.return_value = mock_response_data
            mock_success_response.raise_for_status.return_value = None

            mock_client.get = AsyncMock(
                side_effect=[mock_401_response, mock_success_response]
            )

            result = await service._make_fhir_request("Patient")

            assert result == mock_response_data
            # Should have called refresh_access_token
            service.oauth_client.refresh_access_token.assert_called_once()
            # Should have made 2 requests
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_make_fhir_request_timeout_retry(self, service):
        """Test timeout error triggers retry with backoff."""
        mock_response_data = {"resourceType": "Bundle", "total": 1}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value

            # First two calls: timeout
            timeout_error = httpx.TimeoutException("Request timeout")

            # Third call: success
            mock_success_response = MagicMock()
            mock_success_response.status_code = 200
            mock_success_response.json.return_value = mock_response_data
            mock_success_response.raise_for_status.return_value = None

            mock_client.get = AsyncMock(
                side_effect=[timeout_error, timeout_error, mock_success_response]
            )

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await service._make_fhir_request("Patient")

                assert result == mock_response_data
                # Should have made 3 requests
                assert mock_client.get.call_count == 3
                # Should have slept twice (after first two failures)
                assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_make_fhir_request_exhausted_retries(self, service):
        """Test request failure after all retries exhausted."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = mock_client_class.return_value.__aenter__.return_value

            # All calls timeout
            timeout_error = httpx.TimeoutException("Request timeout")
            mock_client.get = AsyncMock(side_effect=timeout_error)

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(NetworkError, match="FHIR request failed after"):
                    await service._make_fhir_request("Patient")

    def test_calculate_match_confidence(self, service):
        """Test patient match confidence calculation."""
        patient = {
            "name": [
                {"use": "official", "family": "Doe", "given": ["John", "William"]}
            ],
            "birthDate": "1985-06-15",
        }

        # Exact matches
        search_params = {
            "given_name": "John",
            "family_name": "Doe",
            "birth_date": "1985-06-15",
        }
        confidence = service._calculate_match_confidence(patient, search_params)
        assert confidence == 1.0  # 0.4 + 0.4 + 0.2

        # Partial name match
        search_params = {"given_name": "Jo", "family_name": "Doe"}  # Partial match
        confidence = service._calculate_match_confidence(patient, search_params)
        assert confidence == 0.65  # 0.25 + 0.4

        # No matches
        search_params = {"given_name": "Jane", "family_name": "Smith"}
        confidence = service._calculate_match_confidence(patient, search_params)
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_get_patient_by_id(self, service):
        """Test getting patient by ID."""
        mock_patient = {
            "id": "patient-123",
            "resourceType": "Patient",
            "name": [{"family": "Doe", "given": ["John"]}],
        }

        with patch.object(
            service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_patient

            result = await service.get_patient_by_id("patient-123")

            assert result.id == "patient-123"
            assert result.confidence == 1.0
            mock_request.assert_called_once_with("Patient/patient-123")

    @pytest.mark.asyncio
    async def test_get_patient_by_id_invalid_resource(self, service):
        """Test getting patient by ID with invalid resource type."""
        mock_response = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error"}],
        }

        with patch.object(
            service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(FHIRResponseError, match="Expected Patient"):
                await service.get_patient_by_id("patient-123")


class TestIntegration:
    """Integration tests for FHIR service components."""

    @pytest.mark.asyncio
    async def test_full_search_workflow(self):
        """Test complete patient search workflow."""
        # Create mock OAuth client
        mock_oauth_client = MagicMock(spec=EMROAuthClient)
        mock_oauth_client.config = {
            "fhir_base_url": "https://emr.example.com/apis/fhir"
        }
        mock_oauth_client.get_auth_headers = AsyncMock(
            return_value={"Authorization": "Bearer test-token"}
        )

        service = FHIRPatientService(mock_oauth_client)

        # Mock FHIR response with multiple patients
        mock_response = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "id": "patient-1",
                        "resourceType": "Patient",
                        "name": [{"family": "Doe", "given": ["John"]}],
                        "birthDate": "1985-06-15",
                    }
                },
                {
                    "resource": {
                        "id": "patient-2",
                        "resourceType": "Patient",
                        "name": [{"family": "Doe", "given": ["Johnny"]}],
                        "birthDate": "1986-06-15",
                    }
                },
            ],
        }

        with patch.object(
            service, "_make_fhir_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            # First search - should hit FHIR API
            results1 = await service.search_patients(
                given_name="John", family_name="Doe"
            )

            assert len(results1) == 2
            assert mock_request.call_count == 1

            # Verify results are sorted by confidence
            assert results1[0].confidence >= results1[1].confidence

            # Second identical search - should hit cache
            results2 = await service.search_patients(
                given_name="John", family_name="Doe"
            )

            assert results2 == results1
            assert mock_request.call_count == 1  # No additional FHIR call

            # Verify cache statistics
            stats = service.cache.get_stats()
            assert stats["hits"] == 1
            assert stats["misses"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
