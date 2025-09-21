"""
Integration tests for FHIR Patient Search with Mock OpenEMR Server
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.emr import EMROAuthClient
from src.services.fhir_patient import FHIRPatientService, FHIRSearchError, NetworkError


class MockFHIRServer:
    """Mock FHIR server for integration testing."""

    def __init__(self):
        self.patients = self._create_test_patients()
        self.request_count = 0
        self.should_fail = False
        self.failure_mode = "network"  # "network", "auth", "server"

    def _create_test_patients(self):
        """Create 20+ test patient records with varied demographics."""
        patients = []

        # Test data with various scenarios
        test_data = [
            {
                "id": "patient-001",
                "family": "Smith",
                "given": ["John", "Michael"],
                "birth_date": "1985-03-15",
                "phone": "+1-555-101-0001",
                "email": "john.smith@email.com",
                "address": {
                    "line": "123 Main St",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62701",
                },
            },
            {
                "id": "patient-002",
                "family": "Johnson",
                "given": ["Jane", "Elizabeth"],
                "birth_date": "1978-09-22",
                "phone": "+1-555-101-0002",
                "email": "jane.johnson@email.com",
                "address": {
                    "line": "456 Oak Ave",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62702",
                },
            },
            {
                "id": "patient-003",
                "family": "Smith",
                "given": ["Johnny"],  # Similar name to patient-001
                "birth_date": "1985-03-16",  # Close birth date
                "phone": "+1-555-101-0003",
                "email": "johnny.smith@email.com",
                "address": {
                    "line": "789 Pine St",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62703",
                },
            },
            {
                "id": "patient-004",
                "family": "Williams",
                "given": ["Robert", "James"],
                "birth_date": "1962-12-01",
                "phone": "+1-555-101-0004",
                "email": "robert.williams@email.com",
                "address": {
                    "line": "321 Elm St",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62704",
                },
            },
            {
                "id": "patient-005",
                "family": "Brown",
                "given": ["Mary", "Catherine"],
                "birth_date": "1990-07-30",
                "phone": "+1-555-101-0005",
                "email": "mary.brown@email.com",
                "address": {
                    "line": "654 Maple Dr",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62705",
                },
            },
            # Patients with minimal data
            {
                "id": "patient-006",
                "family": "Davis",
                "given": ["Michael"],
                "birth_date": "1975-11-08"
                # No phone, email, or address
            },
            {
                "id": "patient-007",
                "family": "Miller",
                "given": ["Susan", "Ann"],
                "birth_date": "1983-04-12",
                "phone": "+1-555-101-0007"
                # No email or address
            },
            # Patients with special characters and edge cases
            {
                "id": "patient-008",
                "family": "O'Connor",
                "given": ["Patrick", "Sean"],
                "birth_date": "1970-02-14",
                "phone": "+1-555-101-0008",
                "email": "patrick.oconnor@email.com",
                "address": {
                    "line": "111 O'Brien Ave",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62706",
                },
            },
            {
                "id": "patient-009",
                "family": "Van Der Berg",
                "given": ["Anna", "Marie"],
                "birth_date": "1995-01-01",
                "phone": "+1-555-101-0009",
                "email": "anna.vanderberg@email.com",
                "address": {
                    "line": "222 Van Buren St",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62707",
                },
            },
            {
                "id": "patient-010",
                "family": "Smith-Jones",
                "given": ["Jennifer", "Lynn"],
                "birth_date": "1988-08-25",
                "phone": "+1-555-101-0010",
                "email": "jennifer.smith-jones@email.com",
                "address": {
                    "line": "333 Smith-Jones Blvd",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62708",
                },
            },
            # More diverse names and demographics
            {
                "id": "patient-011",
                "family": "García",
                "given": ["Carlos", "Miguel"],
                "birth_date": "1980-05-03",
                "phone": "+1-555-101-0011",
                "email": "carlos.garcia@email.com",
                "address": {
                    "line": "444 García Lane",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62709",
                },
            },
            {
                "id": "patient-012",
                "family": "Chen",
                "given": ["Wei", "Ming"],
                "birth_date": "1992-10-17",
                "phone": "+1-555-101-0012",
                "email": "wei.chen@email.com",
                "address": {
                    "line": "555 Chen Way",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62710",
                },
            },
            {
                "id": "patient-013",
                "family": "Patel",
                "given": ["Priya", "Kumari"],
                "birth_date": "1987-06-23",
                "phone": "+1-555-101-0013",
                "email": "priya.patel@email.com",
                "address": {
                    "line": "666 Patel Circle",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62711",
                },
            },
            # Patients with common names for disambiguation testing
            {
                "id": "patient-014",
                "family": "Johnson",
                "given": ["Michael"],
                "birth_date": "1975-03-15",
                "phone": "+1-555-101-0014",
                "email": "michael.johnson@email.com",
                "address": {
                    "line": "777 Johnson St",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62712",
                },
            },
            {
                "id": "patient-015",
                "family": "Johnson",
                "given": ["Michael", "Robert"],
                "birth_date": "1975-03-15",  # Same DOB as patient-014
                "phone": "+1-555-101-0015",
                "email": "michael.r.johnson@email.com",
                "address": {
                    "line": "888 Johnson Ave",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62713",
                },
            },
            # Edge cases
            {
                "id": "patient-016",
                "family": "Test",
                "given": ["Empty"],
                "birth_date": "2000-01-01"
                # Minimal data for testing
            },
            {
                "id": "patient-017",
                "family": "Very-Long-Last-Name-For-Testing",
                "given": ["Very", "Long", "First", "Name"],
                "birth_date": "1965-12-31",
                "phone": "+1-555-101-0017",
                "email": "very.long.name@email.com",
                "address": {
                    "line": "999 Very Long Street Name That Tests Address Handling",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62714",
                },
            },
            # Recent patients
            {
                "id": "patient-018",
                "family": "Young",
                "given": ["Taylor", "Jordan"],
                "birth_date": "2005-06-15",
                "phone": "+1-555-101-0018",
                "email": "taylor.young@email.com",
                "address": {
                    "line": "101 Young Blvd",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62715",
                },
            },
            {
                "id": "patient-019",
                "family": "Senior",
                "given": ["Margaret", "Rose"],
                "birth_date": "1940-08-08",
                "phone": "+1-555-101-0019",
                "email": "margaret.senior@email.com",
                "address": {
                    "line": "202 Senior Circle",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62716",
                },
            },
            {
                "id": "patient-020",
                "family": "Last",
                "given": ["Final", "Test"],
                "birth_date": "1999-12-31",
                "phone": "+1-555-101-0020",
                "email": "final.test@email.com",
                "address": {
                    "line": "303 Last Lane",
                    "city": "Springfield",
                    "state": "IL",
                    "postal_code": "62717",
                },
            },
            # Additional patients for comprehensive testing
            {
                "id": "patient-021",
                "family": "Duplicate",
                "given": ["First"],
                "birth_date": "1985-01-01",
                "phone": "+1-555-101-0021",
                "email": "first.duplicate@email.com",
            },
            {
                "id": "patient-022",
                "family": "Duplicate",
                "given": ["Second"],
                "birth_date": "1985-01-01",  # Same DOB, different first name
                "phone": "+1-555-101-0022",
                "email": "second.duplicate@email.com",
            },
        ]

        # Convert to FHIR Patient resources
        for data in test_data:
            patient = self._create_fhir_patient(data)
            patients.append(patient)

        return patients

    def _create_fhir_patient(self, data):
        """Create FHIR Patient resource from test data."""
        patient = {
            "id": data["id"],
            "resourceType": "Patient",
            "name": [
                {"use": "official", "family": data["family"], "given": data["given"]}
            ],
            "birthDate": data["birth_date"],
        }

        # Add optional fields if present
        telecom = []
        if "phone" in data:
            telecom.append({"system": "phone", "value": data["phone"], "use": "home"})
        if "email" in data:
            telecom.append({"system": "email", "value": data["email"], "use": "home"})
        if telecom:
            patient["telecom"] = telecom

        if "address" in data:
            patient["address"] = [
                {
                    "use": "home",
                    "line": [data["address"]["line"]],
                    "city": data["address"]["city"],
                    "state": data["address"]["state"],
                    "postalCode": data["address"]["postal_code"],
                }
            ]

        return patient

    async def search_patients(self, params):
        """Mock FHIR patient search endpoint."""
        self.request_count += 1

        # Simulate failures
        if self.should_fail:
            if self.failure_mode == "network":
                raise httpx.TimeoutError("Mock network timeout")
            elif self.failure_mode == "auth":
                response = MagicMock()
                response.status_code = 401
                raise httpx.HTTPStatusError(
                    "Unauthorized", request=MagicMock(), response=response
                )
            elif self.failure_mode == "server":
                response = MagicMock()
                response.status_code = 500
                raise httpx.HTTPStatusError(
                    "Internal Server Error", request=MagicMock(), response=response
                )

        # Filter patients based on search parameters
        results = []
        for patient in self.patients:
            if self._matches_criteria(patient, params):
                results.append(patient)

        # Create FHIR Bundle response
        bundle = {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(results),
            "entry": [
                {
                    "fullUrl": f"https://emr.example.com/fhir/Patient/{patient['id']}",
                    "resource": patient,
                }
                for patient in results
            ],
        }

        return bundle

    def _matches_criteria(self, patient, params):
        """Check if patient matches search criteria."""
        names = patient.get("name", [])
        if not names:
            return False

        name = names[0]  # Use first name record
        patient_family = name.get("family", "").lower()
        patient_given = " ".join(name.get("given", [])).lower()
        patient_dob = patient.get("birthDate", "")

        # Check family name
        if "family" in params:
            search_family = params["family"].replace(":contains", "").lower()
            if ":contains" in params["family"]:
                if search_family not in patient_family:
                    return False
            else:
                if search_family != patient_family:
                    return False

        # Check given name
        if "given" in params:
            search_given = params["given"].replace(":contains", "").lower()
            if ":contains" in params["given"]:
                if search_given not in patient_given:
                    return False
            else:
                if search_given not in patient_given.split():
                    return False

        # Check birth date (exact match)
        if "birthdate" in params:
            if params["birthdate"] != patient_dob:
                return False

        return True

    def get_patient(self, patient_id):
        """Mock FHIR get patient by ID endpoint."""
        self.request_count += 1

        # Simulate failures
        if self.should_fail:
            if self.failure_mode == "network":
                raise httpx.TimeoutError("Mock network timeout")
            elif self.failure_mode == "auth":
                response = MagicMock()
                response.status_code = 401
                raise httpx.HTTPStatusError(
                    "Unauthorized", request=MagicMock(), response=response
                )

        # Find patient
        for patient in self.patients:
            if patient["id"] == patient_id:
                return patient

        # Patient not found
        response = MagicMock()
        response.status_code = 404
        raise httpx.HTTPStatusError("Not Found", request=MagicMock(), response=response)

    def reset(self):
        """Reset mock server state."""
        self.request_count = 0
        self.should_fail = False
        self.failure_mode = "network"


class TestFHIRPatientSearchIntegration:
    """Integration tests with mock FHIR server."""

    @pytest.fixture
    def mock_server(self):
        """Create and configure mock FHIR server."""
        return MockFHIRServer()

    @pytest.fixture
    def mock_oauth_client(self):
        """Create mock OAuth client."""
        mock_client = MagicMock(spec=EMROAuthClient)
        mock_client.config = {"fhir_base_url": "https://emr.example.com/apis/fhir"}
        mock_client.get_auth_headers = AsyncMock(
            return_value={"Authorization": "Bearer test-token"}
        )
        mock_client.refresh_access_token = AsyncMock()
        return mock_client

    @pytest.fixture
    def service(self, mock_oauth_client):
        """Create FHIRPatientService with mock OAuth client."""
        return FHIRPatientService(mock_oauth_client)

    @pytest.mark.asyncio
    async def test_search_by_exact_name(self, service, mock_server):
        """Test exact name search functionality."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Search for exact match
            results = await service.search_patients(
                given_name="John", family_name="Smith", fuzzy=False
            )

            assert len(results) == 1
            assert results[0].id == "patient-001"
            assert results[0].given_name == "John Michael"
            assert results[0].family_name == "Smith"
            assert results[0].confidence > 0.8

    @pytest.mark.asyncio
    async def test_search_by_fuzzy_name(self, service, mock_server):
        """Test fuzzy name search functionality."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Search with fuzzy matching
            results = await service.search_patients(
                given_name="Jo", family_name="Smi", fuzzy=True
            )

            # Should find patients with names containing "Jo" and "Smi"
            assert len(results) >= 2  # Should find John Smith and Johnny Smith

            # Verify some expected matches
            patient_ids = [r.id for r in results]
            assert "patient-001" in patient_ids  # John Smith
            assert "patient-003" in patient_ids  # Johnny Smith

    @pytest.mark.asyncio
    async def test_search_by_birth_date(self, service, mock_server):
        """Test birth date search functionality."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Search by birth date only
            results = await service.search_patients(birth_date="1985-03-15")

            # Should find patient-001 (John Smith) and potentially others with same DOB
            assert len(results) >= 1
            birth_dates = [r.birth_date for r in results]
            assert all(bd == "1985-03-15" for bd in birth_dates)

    @pytest.mark.asyncio
    async def test_search_combined_criteria(self, service, mock_server):
        """Test search with combined name and birth date."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Search with combined criteria for precise matching
            results = await service.search_patients(
                given_name="John", family_name="Smith", birth_date="1985-03-15"
            )

            assert len(results) == 1
            assert results[0].id == "patient-001"
            assert results[0].confidence == 1.0  # Perfect match

    @pytest.mark.asyncio
    async def test_search_multiple_matches_disambiguation(self, service, mock_server):
        """Test handling of multiple patient matches with disambiguation."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Search for common name that returns multiple matches
            results = await service.search_patients(family_name="Johnson")

            assert len(results) >= 2  # Should find multiple Johnson patients

            # Verify results are sorted by confidence
            confidences = [r.confidence for r in results]
            assert confidences == sorted(confidences, reverse=True)

            # Check that disambiguation info is available
            for result in results:
                assert result.family_name == "Johnson"
                assert result.address is not None or result.phone is not None

    @pytest.mark.asyncio
    async def test_search_no_results(self, service, mock_server):
        """Test search that returns no results."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Search for non-existent patient
            results = await service.search_patients(
                given_name="NonExistent", family_name="NotFound"
            )

            assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_special_characters(self, service, mock_server):
        """Test search with special characters in names."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Search for name with apostrophe
            results = await service.search_patients(family_name="O'Connor")

            assert len(results) >= 1
            assert any(r.family_name == "O'Connor" for r in results)

            # Search for hyphenated name
            results = await service.search_patients(family_name="Van Der Berg")

            assert len(results) >= 1
            assert any(r.family_name == "Van Der Berg" for r in results)

    @pytest.mark.asyncio
    async def test_get_patient_by_id_success(self, service, mock_server):
        """Test getting patient by ID successfully."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params=None: mock_server.get_patient(
                    endpoint.split("/")[-1]
                )
            )

            result = await service.get_patient_by_id("patient-001")

            assert result.id == "patient-001"
            assert result.given_name == "John Michael"
            assert result.family_name == "Smith"
            assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_get_patient_by_id_not_found(self, service, mock_server):
        """Test getting non-existent patient by ID."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params=None: mock_server.get_patient(
                    endpoint.split("/")[-1]
                )
            )

            with pytest.raises(FHIRSearchError, match="Patient not found"):
                await service.get_patient_by_id("patient-999")

    @pytest.mark.asyncio
    async def test_caching_functionality(self, service, mock_server):
        """Test that search results are properly cached."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # First search
            results1 = await service.search_patients(
                given_name="John", family_name="Smith"
            )
            assert mock_server.request_count == 1

            # Second identical search - should hit cache
            results2 = await service.search_patients(
                given_name="John", family_name="Smith"
            )
            assert mock_server.request_count == 1  # No additional request
            assert len(results1) == len(results2)

            # Different search - should make new request
            results3 = await service.search_patients(
                given_name="Jane", family_name="Johnson"
            )
            assert mock_server.request_count == 2

            # Verify cache statistics
            stats = service.cache.get_stats()
            assert stats["hits"] == 1
            assert stats["misses"] == 2

    @pytest.mark.asyncio
    async def test_network_error_handling(self, service, mock_server):
        """Test handling of network errors with retry logic."""
        mock_server.should_fail = True
        mock_server.failure_mode = "network"

        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            with pytest.raises(httpx.TimeoutError):
                await service.search_patients(given_name="John")

    @pytest.mark.asyncio
    async def test_authentication_error_handling(self, service, mock_server):
        """Test handling of authentication errors."""
        mock_server.should_fail = True
        mock_server.failure_mode = "auth"

        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            with pytest.raises(httpx.HTTPStatusError):
                await service.search_patients(given_name="John")

    @pytest.mark.asyncio
    async def test_server_error_handling(self, service, mock_server):
        """Test handling of server errors."""
        mock_server.should_fail = True
        mock_server.failure_mode = "server"

        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            with pytest.raises(httpx.HTTPStatusError):
                await service.search_patients(given_name="John")

    @pytest.mark.asyncio
    async def test_phi_protection_in_logs(self, service, mock_server):
        """Test that PHI is properly redacted in logs."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            with patch.object(service.logger, "info") as mock_log:
                await service.search_patients(given_name="John", family_name="Smith")

                # Check that logs don't contain PHI
                log_calls = [call[0][0] for call in mock_log.call_args_list]
                log_text = " ".join(log_calls)

                assert "John" not in log_text
                assert "Smith" not in log_text
                assert "[REDACTED-" in log_text

    @pytest.mark.asyncio
    async def test_confidence_scoring_accuracy(self, service, mock_server):
        """Test accuracy of confidence scoring algorithm."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Test exact match
            results = await service.search_patients(
                given_name="John", family_name="Smith", birth_date="1985-03-15"
            )
            exact_match = next(r for r in results if r.id == "patient-001")
            assert exact_match.confidence == 1.0

            # Test partial match
            results = await service.search_patients(
                given_name="Jo", family_name="Smith"
            )
            partial_matches = [r for r in results if r.family_name == "Smith"]

            # John Smith should have higher confidence than Johnny Smith for "Jo" search
            john_match = next(r for r in partial_matches if "John" in r.given_name)
            johnny_match = next(r for r in partial_matches if "Johnny" in r.given_name)
            assert john_match.confidence >= johnny_match.confidence

    @pytest.mark.asyncio
    async def test_edge_cases_data_handling(self, service, mock_server):
        """Test handling of edge cases in patient data."""
        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Search for patient with minimal data
            results = await service.search_patients(family_name="Davis")

            minimal_patient = next(r for r in results if r.id == "patient-006")
            assert minimal_patient.given_name == "Michael"
            assert minimal_patient.family_name == "Davis"
            assert minimal_patient.phone is None
            assert minimal_patient.email is None
            assert minimal_patient.address is None

            # Search for patient with very long name
            results = await service.search_patients(
                family_name="Very-Long-Last-Name-For-Testing"
            )

            long_name_patient = next(r for r in results if r.id == "patient-017")
            assert long_name_patient.family_name == "Very-Long-Last-Name-For-Testing"
            assert "Very Long First Name" in long_name_patient.given_name


class TestPerformanceAndScalability:
    """Test performance characteristics and scalability."""

    @pytest.mark.asyncio
    async def test_cache_performance(self, mock_oauth_client):
        """Test cache performance with multiple searches."""
        service = FHIRPatientService(mock_oauth_client)
        mock_server = MockFHIRServer()

        with patch.object(service, "_make_fhir_request") as mock_request:
            mock_request.side_effect = (
                lambda endpoint, params: mock_server.search_patients(params)
            )

            # Perform multiple searches
            search_params = [
                {"given_name": "John", "family_name": "Smith"},
                {"given_name": "Jane", "family_name": "Johnson"},
                {"family_name": "Brown"},
                {"birth_date": "1985-03-15"},
                {"given_name": "John", "family_name": "Smith"},  # Repeat for cache hit
            ]

            for params in search_params:
                await service.search_patients(**params)

            # Verify cache efficiency
            stats = service.cache.get_stats()
            assert stats["hits"] == 1  # One cache hit from repeated search
            assert stats["misses"] == 4  # Four unique searches


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
