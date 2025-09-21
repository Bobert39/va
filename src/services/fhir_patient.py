"""
FHIR R4 Patient Search Service

This module provides FHIR R4 compliant patient search functionality
for OpenEMR integration with PHI protection and caching.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..audit import log_audit_event
from .emr import EMROAuthClient, NetworkError

logger = logging.getLogger(__name__)


class FHIRError(Exception):
    """Base exception for FHIR operations."""

    pass


class FHIRSearchError(FHIRError):
    """Error during FHIR patient search."""

    pass


class FHIRResponseError(FHIRError):
    """Invalid or unexpected FHIR response."""

    pass


class PatientMatch:
    """Represents a patient match result with confidence scoring."""

    def __init__(self, patient_data: Dict[str, Any], confidence: float):
        self.id = patient_data.get("id")
        self.resource = patient_data
        self.confidence = confidence
        self.given_name = self._extract_given_name(patient_data)
        self.family_name = self._extract_family_name(patient_data)
        self.birth_date = patient_data.get("birthDate")
        self.phone = self._extract_phone(patient_data)
        self.email = self._extract_email(patient_data)
        self.address = self._extract_address(patient_data)

    def _extract_given_name(self, patient: Dict) -> Optional[str]:
        """Extract patient's given name."""
        names = patient.get("name", [])
        for name in names:
            if name.get("use") in ["official", "usual"] or not name.get("use"):
                given = name.get("given", [])
                if given:
                    return " ".join(given)
        return None

    def _extract_family_name(self, patient: Dict) -> Optional[str]:
        """Extract patient's family name."""
        names = patient.get("name", [])
        for name in names:
            if name.get("use") in ["official", "usual"] or not name.get("use"):
                family = name.get("family")
                if family:
                    return family
        return None

    def _extract_phone(self, patient: Dict) -> Optional[str]:
        """Extract patient's phone number."""
        telecoms = patient.get("telecom", [])
        for telecom in telecoms:
            if telecom.get("system") == "phone":
                return telecom.get("value")
        return None

    def _extract_email(self, patient: Dict) -> Optional[str]:
        """Extract patient's email."""
        telecoms = patient.get("telecom", [])
        for telecom in telecoms:
            if telecom.get("system") == "email":
                return telecom.get("value")
        return None

    def _extract_address(self, patient: Dict) -> Optional[Dict]:
        """Extract patient's address."""
        addresses = patient.get("address", [])
        for address in addresses:
            if address.get("use") in ["home", "work"] or not address.get("use"):
                return {
                    "line": " ".join(address.get("line", [])),
                    "city": address.get("city"),
                    "state": address.get("state"),
                    "postal_code": address.get("postalCode"),
                    "country": address.get("country"),
                }
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "given_name": self.given_name,
            "family_name": self.family_name,
            "birth_date": self.birth_date,
            "confidence": self.confidence,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
        }


class SearchCache:
    """Simple in-memory cache for patient search results."""

    def __init__(self, ttl_seconds: int = 300):  # 5 minutes default
        self._cache: Dict[str, Tuple[List[PatientMatch], float]] = {}
        self._ttl = ttl_seconds
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def _make_key(self, **search_params) -> str:
        """Create cache key from search parameters."""
        # Sort params for consistent hashing
        sorted_params = sorted(search_params.items())
        key_str = json.dumps(sorted_params, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, **search_params) -> Optional[List[PatientMatch]]:
        """Get cached results if available and not expired."""
        key = self._make_key(**search_params)

        if key in self._cache:
            results, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                self._stats["hits"] += 1
                logger.debug(
                    f"Cache hit for search params (anonymized key: {key[:8]}...)"
                )
                return results
            else:
                # Expired entry
                del self._cache[key]
                self._stats["evictions"] += 1

        self._stats["misses"] += 1
        return None

    def set(self, results: List[PatientMatch], **search_params):
        """Cache search results."""
        key = self._make_key(**search_params)
        self._cache[key] = (results, time.time())
        logger.debug(f"Cached {len(results)} results (anonymized key: {key[:8]}...)")

    def invalidate(self, patient_id: Optional[str] = None):
        """Invalidate cache entries."""
        if patient_id:
            # Invalidate entries containing specific patient
            keys_to_remove = []
            for key, (results, _) in self._cache.items():
                if any(r.id == patient_id for r in results):
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del self._cache[key]
                self._stats["evictions"] += 1
        else:
            # Clear all cache
            self._cache.clear()
            self._stats["evictions"] += len(self._cache)

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return self._stats.copy()


class FHIRPatientService:
    """Service for FHIR R4 Patient resource operations."""

    def __init__(self, oauth_client: EMROAuthClient):
        self.oauth_client = oauth_client
        oauth_config = oauth_client._get_oauth_config()
        self.base_url = oauth_config.get(
            "fhir_base_url",
            oauth_config.get("emr_base_url", "").rstrip("/") + "/apis/fhir",
        )
        self.cache = SearchCache(ttl_seconds=300)
        self._retry_delays = [0.5, 1.0, 2.0]  # Exponential backoff

    def _anonymize_for_logging(self, text: str) -> str:
        """Create anonymized version of text for logging."""
        if not text:
            return "[empty]"
        return f"[REDACTED-{hashlib.sha256(text.encode()).hexdigest()[:8]}]"

    def _log_phi_safe(self, level: str, message: str, **kwargs):
        """Log message with PHI redacted."""
        # Redact any patient-specific data in kwargs
        safe_kwargs = {}
        phi_fields = [
            "name",
            "given_name",
            "family_name",
            "birth_date",
            "dob",
            "phone",
            "email",
            "address",
            "id",
            "patient_id",
        ]

        for key, value in kwargs.items():
            if any(field in key.lower() for field in phi_fields):
                safe_kwargs[key] = self._anonymize_for_logging(str(value))
            else:
                safe_kwargs[key] = value

        log_message = f"{message} | {safe_kwargs}" if safe_kwargs else message
        getattr(logger, level)(log_message)

    async def _make_fhir_request(
        self, endpoint: str, params: Optional[Dict] = None
    ) -> Dict:
        """Make authenticated FHIR API request with retry logic."""
        url = f"{self.base_url}/{endpoint}"
        headers = await self.oauth_client.get_auth_headers()

        last_error = None
        for attempt, delay in enumerate(self._retry_delays + [None], 1):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, params=params, headers=headers)

                    if response.status_code == 401:
                        # Try refreshing token once
                        if attempt == 1:
                            await self.oauth_client.refresh_access_token()
                            headers = await self.oauth_client.get_auth_headers()
                            continue
                        raise FHIRError("Authentication failed after token refresh")

                    if response.status_code == 404:
                        raise FHIRSearchError("Patient not found")
                    elif response.status_code == 400:
                        raise FHIRSearchError(
                            f"Invalid search parameters: {response.text}"
                        )

                    response.raise_for_status()
                    return response.json()

            except httpx.TimeoutException as e:
                last_error = e
                self._log_phi_safe(
                    "warning", f"FHIR request timeout (attempt {attempt}/4)"
                )

            except httpx.HTTPStatusError as e:
                last_error = e
                self._log_phi_safe(
                    "warning",
                    f"FHIR HTTP error (attempt {attempt}/4): {e.response.status_code}",
                )

            except Exception as e:
                last_error = e
                self._log_phi_safe(
                    "error", f"Unexpected FHIR error (attempt {attempt}/4): {str(e)}"
                )

            # Retry with backoff if not the last attempt
            if delay is not None:
                await asyncio.sleep(delay)

        # All retries exhausted
        raise NetworkError(
            f"FHIR request failed after {len(self._retry_delays) + 1} attempts: {str(last_error)}"
        )

    def _calculate_match_confidence(self, patient: Dict, search_params: Dict) -> float:
        """Calculate confidence score for patient match."""
        confidence = 0.0

        # Extract patient data
        patient_given = self._extract_name_parts(patient, "given")
        patient_family = self._extract_name_parts(patient, "family")
        patient_dob = patient.get("birthDate")

        # Check name matches
        if "given_name" in search_params and patient_given:
            search_given = search_params["given_name"].lower()
            if any(search_given == g.lower() for g in patient_given):
                confidence += 0.4  # Exact given name match
            elif any(
                search_given in g.lower() or g.lower() in search_given
                for g in patient_given
            ):
                confidence += 0.25  # Partial given name match

        if "family_name" in search_params and patient_family:
            search_family = search_params["family_name"].lower()
            if search_family == patient_family.lower():
                confidence += 0.4  # Exact family name match
            elif (
                search_family in patient_family.lower()
                or patient_family.lower() in search_family
            ):
                confidence += 0.25  # Partial family name match

        # Check DOB match
        if "birth_date" in search_params and patient_dob:
            if search_params["birth_date"] == patient_dob:
                confidence += 0.2  # Exact DOB match

        # Normalize to 0-1 scale
        return min(confidence, 1.0)

    def _extract_name_parts(self, patient: Dict, part: str) -> Any:
        """Extract name parts from patient resource."""
        names = patient.get("name", [])
        for name in names:
            if name.get("use") in ["official", "usual"] or not name.get("use"):
                if part == "given":
                    return name.get("given", [])
                elif part == "family":
                    return name.get("family")
        return [] if part == "given" else None

    async def search_patients(
        self,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
        birth_date: Optional[str] = None,
        fuzzy: bool = True,
    ) -> List[PatientMatch]:
        """
        Search for patients by name and/or birth date.

        Args:
            given_name: Patient's given (first) name
            family_name: Patient's family (last) name
            birth_date: Patient's date of birth (YYYY-MM-DD format)
            fuzzy: Enable fuzzy matching for names

        Returns:
            List of PatientMatch objects sorted by confidence
        """
        # Build search parameters
        search_params = {}
        if given_name:
            search_params["given_name"] = given_name
        if family_name:
            search_params["family_name"] = family_name
        if birth_date:
            search_params["birth_date"] = birth_date

        if not search_params:
            raise FHIRSearchError("At least one search parameter is required")

        # Check cache first
        cached_results = self.cache.get(**search_params)
        if cached_results is not None:
            return cached_results

        # Build FHIR search query
        fhir_params = {}
        if given_name:
            fhir_params["given"] = given_name + (":contains" if fuzzy else "")
        if family_name:
            fhir_params["family"] = family_name + (":contains" if fuzzy else "")
        if birth_date:
            fhir_params["birthdate"] = birth_date

        # Log search with anonymized data
        log_audit_event(
            "patient_search",
            "FHIR patient search initiated",
            additional_data={
                "search_params": {
                    k: self._anonymize_for_logging(v) for k, v in search_params.items()
                },
                "fuzzy": fuzzy,
            },
        )

        try:
            # Make FHIR request
            response = await self._make_fhir_request("Patient", fhir_params)

            # Parse response bundle
            if response.get("resourceType") != "Bundle":
                raise FHIRResponseError(
                    f"Expected Bundle, got {response.get('resourceType')}"
                )

            entries = response.get("entry", [])
            results = []

            for entry in entries:
                patient = entry.get("resource", {})
                if patient.get("resourceType") != "Patient":
                    continue

                # Calculate match confidence
                confidence = self._calculate_match_confidence(patient, search_params)

                # Create PatientMatch object
                match = PatientMatch(patient, confidence)
                results.append(match)

            # Sort by confidence (highest first)
            results.sort(key=lambda m: m.confidence, reverse=True)

            # Cache results
            self.cache.set(results, **search_params)

            # Log results summary (PHI-safe)
            self._log_phi_safe(
                "info",
                f"Found {len(results)} patient matches",
                confidence_range=f"{results[0].confidence:.2f}-{results[-1].confidence:.2f}"
                if results
                else "N/A",
            )

            return results

        except (FHIRError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe("error", f"Unexpected error in patient search: {str(e)}")
            raise FHIRSearchError(f"Patient search failed: {str(e)}")

    async def get_patient_by_id(self, patient_id: str) -> PatientMatch:
        """
        Get a specific patient by ID.

        Args:
            patient_id: FHIR Patient resource ID

        Returns:
            PatientMatch object with confidence 1.0
        """
        # Log access with anonymized ID
        log_audit_event(
            "patient_access",
            "FHIR patient access by ID",
            additional_data={"patient_id": self._anonymize_for_logging(patient_id)},
        )

        try:
            response = await self._make_fhir_request(f"Patient/{patient_id}")

            if response.get("resourceType") != "Patient":
                raise FHIRResponseError(
                    f"Expected Patient, got {response.get('resourceType')}"
                )

            return PatientMatch(response, confidence=1.0)

        except (FHIRError, NetworkError):
            raise
        except Exception as e:
            self._log_phi_safe("error", f"Error getting patient by ID: {str(e)}")
            raise FHIRError(f"Failed to get patient: {str(e)}")
