"""
Voice AI Platform - FastAPI Application Entry Point

This module serves as the main entry point for the Voice AI Platform application.
It sets up the FastAPI application with automatic OpenAPI documentation,
CORS middleware, and basic health check endpoints.
"""

import os
from pathlib import Path
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from .audit import audit_logger, log_audit_event
from .services.appointment import FHIRAppointmentError, FHIRAppointmentService
from .services.emr import OAuthError, TokenExpiredError, oauth_client
from .services.fhir_patient import FHIRPatientService, FHIRSearchError, PatientMatch
from .services.provider_schedule import ProviderScheduleError, ProviderScheduleService
from .services.session_storage import InMemorySessionStorage, session_storage

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI application
app = FastAPI(
    title="Voice AI Platform",
    description="Voice AI Platform for EMR Integration - "
    "Enables voice-controlled appointment scheduling",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add rate limiting middleware and error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Session storage for OAuth state
# Use Redis in production, fallback to in-memory for development
oauth_session_store = session_storage

# Initialize FHIR services
fhir_patient_service = FHIRPatientService(oauth_client)
provider_schedule_service = ProviderScheduleService(oauth_client)
appointment_service = FHIRAppointmentService(oauth_client)


@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    global oauth_session_store

    # Test Redis connection, fallback to in-memory if needed
    try:
        redis_healthy = await session_storage.health_check()
        if not redis_healthy:
            print("Warning: Redis not available, using in-memory session storage")
            oauth_session_store = InMemorySessionStorage()
    except Exception as e:
        print(
            f"Warning: Redis connection failed ({e}), using in-memory session storage"
        )
        oauth_session_store = InMemorySessionStorage()


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks."""
    await oauth_session_store.disconnect()


# Pydantic models for API requests/responses
class OAuthConfigUpdate(BaseModel):
    """OAuth configuration update model."""

    client_id: str
    client_secret: str
    authorization_endpoint: str
    token_endpoint: str
    fhir_base_url: str


class OAuthStatusResponse(BaseModel):
    """OAuth status response model."""

    authenticated: bool
    expires_at: str = ""
    error: str = ""


class OAuthTestResponse(BaseModel):
    """OAuth test connection response model."""

    status: str
    fhir_version: str = ""
    software: str = ""
    message: str
    error: str = ""


# Patient Search Models
class PatientSearchRequest(BaseModel):
    """Patient search request model."""

    given_name: str = ""
    family_name: str = ""
    birth_date: str = ""  # YYYY-MM-DD format
    fuzzy: bool = True


class PatientMatchResponse(BaseModel):
    """Patient match response model."""

    id: str
    given_name: str = ""
    family_name: str = ""
    birth_date: str = ""
    confidence: float
    phone: str = ""
    email: str = ""
    address: dict = {}


class PatientSearchResponse(BaseModel):
    """Patient search response model."""

    status: str
    patients: list[PatientMatchResponse]
    total: int
    message: str = ""
    error: str = ""


# Appointment Models
class AppointmentResponse(BaseModel):
    """Appointment response model."""

    id: str
    status: str
    start: str = ""
    end: str = ""
    description: str = ""
    comment: str = ""
    appointment_type: str = ""
    service_type: str = ""
    patient_reference: str = ""
    practitioner_reference: str = ""
    patient_name: str = ""
    provider_name: str = ""
    time_display: str = ""
    date_display: str = ""
    participants: int


class AppointmentListResponse(BaseModel):
    """Appointment list response model."""

    status: str
    appointments: list[AppointmentResponse]
    total: int
    message: str = ""
    error: str = ""


class ProviderResponse(BaseModel):
    """Provider response model for filtering."""

    id: str
    name: str
    reference: str


class ProviderListResponse(BaseModel):
    """Provider list response model."""

    status: str
    providers: list[ProviderResponse]
    total: int
    message: str = ""
    error: str = ""


# OAuth 2.0 Endpoints


@app.get("/oauth/authorize")
@limiter.limit("10/minute")
async def oauth_authorize(request: Request):
    """
    Initiate OAuth 2.0 authorization flow.

    Redirects user to OpenEMR authorization server with PKCE parameters.
    """
    try:
        authorization_url, state, code_verifier = oauth_client.build_authorization_url()

        # Store OAuth session data
        session_data = {
            "code_verifier": code_verifier,
            "timestamp": request.headers.get("timestamp", ""),
        }
        await oauth_session_store.set_session(state, session_data)

        # Log OAuth initiation
        log_audit_event(
            event_type="oauth_authorize_initiated",
            action="Initiated OAuth authorization request",
            user_id="system",
            additional_data={
                "client_id": oauth_client._get_oauth_config().get("client_id", "")
            },
        )

        return RedirectResponse(url=authorization_url, status_code=302)

    except OAuthError as e:
        log_audit_event(
            event_type="oauth_authorize_failed",
            action="Failed OAuth authorization due to unexpected error",
            user_id="system",
            additional_data={"error": e.error, "description": e.description},
        )
        raise HTTPException(
            status_code=400, detail=f"OAuth configuration error: {e.description}"
        )
    except Exception as e:
        log_audit_event(
            event_type="oauth_authorize_failed",
            action="Failed OAuth authorization due to unexpected error",
            user_id="system",
            additional_data={"error": "unexpected_error", "description": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to initiate OAuth flow")


@app.get("/oauth/callback")
@limiter.limit("20/minute")
async def oauth_callback(request: Request, code: str, state: str):
    """
    Handle OAuth 2.0 authorization code callback.

    Exchanges authorization code for access and refresh tokens.
    """
    try:
        # Retrieve session data
        session_data = await oauth_session_store.get_session(state)
        if not session_data:
            log_audit_event(
                event_type="oauth_callback_failed",
                action="OAuth callback received invalid state",
                user_id="system",
                additional_data={"error": "invalid_state", "state": state},
            )
            raise HTTPException(status_code=400, detail="Invalid OAuth state parameter")
        code_verifier = session_data["code_verifier"]

        # Exchange code for tokens
        token_response = await oauth_client.exchange_code_for_tokens(
            authorization_code=code,
            code_verifier=code_verifier,
            state=state,
            expected_state=state,
        )

        # Store tokens
        oauth_client.store_tokens(token_response)

        # Clean up session
        await oauth_session_store.delete_session(state)

        # Log successful authentication
        log_audit_event(
            event_type="oauth_callback_success",
            action="Executed oauth_callback_success",
            user_id="system",
            additional_data={"expires_at": token_response.get("expires_at", "")},
        )

        return {
            "status": "success",
            "message": "OAuth authentication completed successfully",
            "expires_at": token_response.get("expires_at", ""),
        }

    except OAuthError as e:
        log_audit_event(
            event_type="oauth_callback_failed",
            action="Executed oauth_callback_failed",
            user_id="system",
            additional_data={"error": e.error, "description": e.description},
        )
        # Clean up session on error
        await oauth_session_store.delete_session(state)
        raise HTTPException(status_code=400, detail=f"OAuth error: {e.description}")
    except Exception as e:
        log_audit_event(
            event_type="oauth_callback_failed",
            action="Executed oauth_callback_failed",
            user_id="system",
            additional_data={"error": "unexpected_error", "description": str(e)},
        )
        # Clean up session on error
        await oauth_session_store.delete_session(state)
        raise HTTPException(status_code=500, detail="OAuth callback processing failed")


@app.get("/api/v1/oauth/status", response_model=OAuthStatusResponse)
@limiter.limit("30/minute")
async def oauth_status(request: Request):
    """
    Get OAuth authentication status.

    Returns current authentication status and token expiration.
    """
    try:
        token_data = oauth_client.get_stored_tokens()

        if not token_data:
            return OAuthStatusResponse(
                authenticated=False, error="No OAuth tokens found"
            )

        is_valid = oauth_client.is_token_valid(token_data)

        return OAuthStatusResponse(
            authenticated=is_valid,
            expires_at=token_data.get("expires_at", ""),
            error="" if is_valid else "Token expired",
        )

    except Exception as e:
        return OAuthStatusResponse(authenticated=False, error=str(e))


@app.post("/api/v1/oauth/test", response_model=OAuthTestResponse)
@limiter.limit("5/minute")
async def oauth_test(request: Request):
    """
    Test OAuth connection to OpenEMR FHIR API.

    Verifies authentication and connectivity to EMR system.
    """
    try:
        result = await oauth_client.test_connection()

        # Log test attempt
        log_audit_event(
            event_type="oauth_test_connection",
            action="Executed oauth_test_connection",
            user_id="system",
            additional_data={
                "status": result["status"],
                "message": result.get("message", ""),
            },
        )

        if result["status"] == "success":
            return OAuthTestResponse(
                status="success",
                fhir_version=result.get("fhir_version", ""),
                software=result.get("software", ""),
                message=result.get("message", "Connection successful"),
            )
        else:
            return OAuthTestResponse(
                status="error",
                message=result.get("message", "Connection failed"),
                error=result.get("error", "unknown_error"),
            )

    except Exception as e:
        log_audit_event(
            event_type="oauth_test_connection",
            action="Executed oauth_test_connection",
            user_id="system",
            additional_data={"status": "error", "error": str(e)},
        )
        return OAuthTestResponse(
            status="error",
            message="Unexpected error during connection test",
            error=str(e),
        )


@app.post("/api/v1/oauth/config")
@limiter.limit("3/minute")
async def update_oauth_config(request: Request, config: OAuthConfigUpdate):
    """
    Update OAuth configuration settings.

    Saves OAuth configuration with encrypted storage.
    """
    try:
        from .config import set_config

        # Update OAuth configuration
        oauth_config = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": "http://localhost:8000/oauth/callback",
            "authorization_endpoint": config.authorization_endpoint,
            "token_endpoint": config.token_endpoint,
            "fhir_base_url": config.fhir_base_url,
            "scopes": [
                "openid",
                "fhirUser",
                "patient/*.read",
                "patient/*.write",
                "Patient.read",
                "Encounter.read",
                "DiagnosticReport.read",
                "Medication.read",
                "Appointment.read",
                "Appointment.write",
            ],
        }

        set_config("oauth_config", oauth_config)

        # Clear OAuth client config cache
        oauth_client._clear_config_cache()

        # Log configuration update
        log_audit_event(
            event_type="oauth_config_updated",
            action="Updated OAuth configuration",
            user_id="system",
            additional_data={
                "client_id": config.client_id,
                "fhir_base_url": config.fhir_base_url,
            },
        )

        return {
            "status": "success",
            "message": "OAuth configuration updated successfully",
        }

    except Exception as e:
        log_audit_event(
            event_type="oauth_config_update_failed",
            action="Failed to update OAuth configuration",
            user_id="system",
            additional_data={"error": str(e)},
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to update configuration: {str(e)}"
        )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint that provides basic information about the API."""
    return """
    <html>
        <head>
            <title>Voice AI Platform</title>
        </head>
        <body>
            <h1>Voice AI Platform</h1>
            <p>Voice AI Platform for EMR Integration</p>
            <ul>
                <li><a href="/docs">API Documentation (OpenAPI)</a></li>
                <li><a href="/redoc">API Documentation (ReDoc)</a></li>
                <li><a href="/health">Health Check</a></li>
                <li><a href="/dashboard">Dashboard</a> (Coming Soon)</li>
            </ul>
        </body>
    </html>
    """


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring application status."""
    return {"status": "healthy", "service": "Voice AI Platform", "version": "0.1.0"}


@app.get("/dev/status")
async def dev_status():
    """Development status endpoint for testing hot reload functionality."""
    return {
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "debug": os.getenv("DEBUG", "false"),
        "hot_reload": "enabled",
        "message": "Development environment is working correctly!",
        "timestamp": "2025-01-20T12:00:00Z",
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Basic dashboard endpoint (placeholder for future development)."""
    dashboard_path = Path("static/dashboard.html")

    if dashboard_path.exists():
        with open(dashboard_path, "r") as f:
            return f.read()
    else:
        return """
        <html>
            <head>
                <title>Voice AI Platform - Dashboard</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/"
                      "bootstrap.min.css" rel="stylesheet">
            </head>
            <body>
                <div class="container mt-5">
                    <h1>Voice AI Platform Dashboard</h1>
                    <p class="lead">Dashboard coming soon...</p>
                    <div class="alert alert-info">
                        <strong>Note:</strong> This is the infrastructure setup phase.
                        Dashboard functionality will be implemented in future stories.
                    </div>
                    <a href="/docs" class="btn btn-primary">View API Documentation</a>
                </div>
            </body>
        </html>
        """


# FHIR Patient Search API Endpoints


@app.get("/api/v1/patients/search")
@limiter.limit("30/minute")
async def search_patients(
    request: Request,
    given_name: str = "",
    family_name: str = "",
    birth_date: str = "",  # YYYY-MM-DD format
    fuzzy: bool = True,
):
    """
    Search for patients by name and/or birth date.

    Query Parameters:
    - given_name: Patient's given (first) name
    - family_name: Patient's family (last) name
    - birth_date: Patient's date of birth (YYYY-MM-DD format)
    - fuzzy: Enable fuzzy matching for names (default: true)

    At least one search parameter is required.
    """
    try:
        # Validate that at least one search parameter is provided
        if not any([given_name, family_name, birth_date]):
            raise HTTPException(
                status_code=400,
                detail="At least one search parameter (given_name, family_name, or birth_date) is required",
            )

        # Validate birth_date format if provided
        if birth_date:
            try:
                from datetime import datetime

                datetime.strptime(birth_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="birth_date must be in YYYY-MM-DD format"
                )

        # Log search request with anonymized data
        log_audit_event(
            event_type="patient_search_requested",
            action="Executed patient_search_requested",
            user_id="system",
            additional_data={
                "has_given_name": bool(given_name),
                "has_family_name": bool(family_name),
                "has_birth_date": bool(birth_date),
                "fuzzy": fuzzy,
            },
        )

        # Perform patient search
        results = await fhir_patient_service.search_patients(
            given_name=given_name if given_name else None,
            family_name=family_name if family_name else None,
            birth_date=birth_date if birth_date else None,
            fuzzy=fuzzy,
        )

        # Convert results to response format
        patient_matches = [
            PatientMatchResponse(
                id=match.id,
                given_name=match.given_name or "",
                family_name=match.family_name or "",
                birth_date=match.birth_date or "",
                confidence=match.confidence,
                phone=match.phone or "",
                email=match.email or "",
                address=match.address or {},
            )
            for match in results
        ]

        # Log successful search with anonymized result count
        log_audit_event(
            event_type="patient_search_completed",
            action="Completed patient search",
            user_id="system",
            additional_data={
                "result_count": len(results),
                "has_exact_matches": any(r.confidence >= 0.95 for r in results),
                "cache_stats": fhir_patient_service.cache.get_stats(),
            },
        )

        return PatientSearchResponse(
            status="success",
            patients=patient_matches,
            total=len(patient_matches),
            message=f"Found {len(patient_matches)} patient matches",
        )

    except FHIRSearchError as e:
        log_audit_event(
            event_type="patient_search_failed",
            action="Failed patient search",
            user_id="system",
            additional_data={"error": "fhir_search_error", "message": str(e)},
        )
        return PatientSearchResponse(
            status="error", patients=[], total=0, error="search_error", message=str(e)
        )

    except OAuthError as e:
        log_audit_event(
            event_type="patient_search_failed",
            action="Failed patient search",
            user_id="system",
            additional_data={"error": "authentication_error", "message": e.description},
        )
        raise HTTPException(
            status_code=401, detail=f"Authentication failed: {e.description}"
        )

    except Exception as e:
        log_audit_event(
            event_type="patient_search_failed",
            action="Failed patient search",
            user_id="system",
            additional_data={"error": "unexpected_error", "message": str(e)},
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during patient search"
        )


@app.get("/api/v1/patients/{patient_id}")
@limiter.limit("30/minute")
async def get_patient_by_id(request: Request, patient_id: str):
    """
    Get a specific patient by their FHIR Patient resource ID.

    Path Parameters:
    - patient_id: FHIR Patient resource ID
    """
    try:
        # Validate patient_id
        if not patient_id or not patient_id.strip():
            raise HTTPException(
                status_code=400, detail="patient_id is required and cannot be empty"
            )

        # Log patient access request with anonymized ID
        log_audit_event(
            event_type="patient_access_requested",
            action="Executed patient_access_requested",
            user_id="system",
            additional_data={"has_patient_id": bool(patient_id)},
        )

        # Get patient by ID
        patient_match = await fhir_patient_service.get_patient_by_id(patient_id)

        # Convert to response format
        patient_response = PatientMatchResponse(
            id=patient_match.id,
            given_name=patient_match.given_name or "",
            family_name=patient_match.family_name or "",
            birth_date=patient_match.birth_date or "",
            confidence=patient_match.confidence,
            phone=patient_match.phone or "",
            email=patient_match.email or "",
            address=patient_match.address or {},
        )

        # Log successful access
        log_audit_event(
            event_type="patient_access_completed",
            action="Executed patient_access_completed",
            user_id="system",
            additional_data={"status": "success"},
        )

        return PatientSearchResponse(
            status="success",
            patients=[patient_response],
            total=1,
            message="Patient found",
        )

    except FHIRSearchError as e:
        log_audit_event(
            event_type="patient_access_failed",
            action="Executed patient_access_failed",
            user_id="system",
            additional_data={"error": "patient_not_found", "message": str(e)},
        )
        raise HTTPException(status_code=404, detail=str(e))

    except OAuthError as e:
        log_audit_event(
            event_type="patient_access_failed",
            action="Executed patient_access_failed",
            user_id="system",
            additional_data={"error": "authentication_error", "message": e.description},
        )
        raise HTTPException(
            status_code=401, detail=f"Authentication failed: {e.description}"
        )

    except Exception as e:
        log_audit_event(
            event_type="patient_access_failed",
            action="Executed patient_access_failed",
            user_id="system",
            additional_data={"error": "unexpected_error", "message": str(e)},
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during patient access"
        )


@app.post("/api/v1/patients/search")
@limiter.limit("30/minute")
async def search_patients_post(request: Request, search_request: PatientSearchRequest):
    """
    Search for patients by name and/or birth date (POST version).

    Request Body:
    - given_name: Patient's given (first) name
    - family_name: Patient's family (last) name
    - birth_date: Patient's date of birth (YYYY-MM-DD format)
    - fuzzy: Enable fuzzy matching for names (default: true)

    At least one search parameter is required.
    """
    try:
        # Validate that at least one search parameter is provided
        if not any(
            [
                search_request.given_name,
                search_request.family_name,
                search_request.birth_date,
            ]
        ):
            raise HTTPException(
                status_code=400,
                detail="At least one search parameter (given_name, family_name, or birth_date) is required",
            )

        # Validate birth_date format if provided
        if search_request.birth_date:
            try:
                from datetime import datetime

                datetime.strptime(search_request.birth_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="birth_date must be in YYYY-MM-DD format"
                )

        # Log search request with anonymized data
        log_audit_event(
            event_type="patient_search_requested",
            action="Executed patient_search_requested",
            user_id="system",
            additional_data={
                "method": "POST",
                "has_given_name": bool(search_request.given_name),
                "has_family_name": bool(search_request.family_name),
                "has_birth_date": bool(search_request.birth_date),
                "fuzzy": search_request.fuzzy,
            },
        )

        # Perform patient search
        results = await fhir_patient_service.search_patients(
            given_name=search_request.given_name if search_request.given_name else None,
            family_name=search_request.family_name
            if search_request.family_name
            else None,
            birth_date=search_request.birth_date if search_request.birth_date else None,
            fuzzy=search_request.fuzzy,
        )

        # Convert results to response format
        patient_matches = [
            PatientMatchResponse(
                id=match.id,
                given_name=match.given_name or "",
                family_name=match.family_name or "",
                birth_date=match.birth_date or "",
                confidence=match.confidence,
                phone=match.phone or "",
                email=match.email or "",
                address=match.address or {},
            )
            for match in results
        ]

        # Log successful search with anonymized result count
        log_audit_event(
            event_type="patient_search_completed",
            action="Completed patient search",
            user_id="system",
            additional_data={
                "method": "POST",
                "result_count": len(results),
                "has_exact_matches": any(r.confidence >= 0.95 for r in results),
                "cache_stats": fhir_patient_service.cache.get_stats(),
            },
        )

        return PatientSearchResponse(
            status="success",
            patients=patient_matches,
            total=len(patient_matches),
            message=f"Found {len(patient_matches)} patient matches",
        )

    except FHIRSearchError as e:
        log_audit_event(
            event_type="patient_search_failed",
            action="Failed patient search",
            user_id="system",
            additional_data={
                "method": "POST",
                "error": "fhir_search_error",
                "message": str(e),
            },
        )
        return PatientSearchResponse(
            status="error", patients=[], total=0, error="search_error", message=str(e)
        )

    except OAuthError as e:
        log_audit_event(
            event_type="patient_search_failed",
            action="Failed patient search",
            user_id="system",
            additional_data={
                "method": "POST",
                "error": "authentication_error",
                "message": e.description,
            },
        )
        raise HTTPException(
            status_code=401, detail=f"Authentication failed: {e.description}"
        )

    except Exception as e:
        log_audit_event(
            event_type="patient_search_failed",
            action="Failed patient search",
            user_id="system",
            additional_data={
                "method": "POST",
                "error": "unexpected_error",
                "message": str(e),
            },
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during patient search"
        )


# Appointment API Endpoints


@app.get("/api/v1/appointments/today", response_model=AppointmentListResponse)
@limiter.limit("30/minute")
async def get_appointments_today(request: Request):
    """
    Get today's appointments.

    Returns:
        AppointmentListResponse: Today's appointments
    """
    try:
        # Log appointment access request
        log_audit_event(
            event_type="appointments_today_requested",
            action="Requested today's appointments",
            user_id="system",
            additional_data={},
        )

        # Get today's appointments
        appointments = await appointment_service.get_appointments_today()

        # Convert to response format
        appointment_responses = [
            AppointmentResponse(**appointment.to_dict()) for appointment in appointments
        ]

        # Log successful access
        log_audit_event(
            event_type="appointments_today_completed",
            action="Successfully retrieved today's appointments",
            user_id="system",
            additional_data={"appointment_count": len(appointments)},
        )

        return AppointmentListResponse(
            status="success",
            appointments=appointment_responses,
            total=len(appointment_responses),
            message=f"Found {len(appointment_responses)} appointments for today",
        )

    except FHIRAppointmentError as e:
        log_audit_event(
            event_type="appointments_today_failed",
            action="Failed to retrieve today's appointments due to service error",
            user_id="system",
            additional_data={"error": "appointment_error", "message": str(e)},
        )
        return AppointmentListResponse(
            status="error",
            appointments=[],
            total=0,
            error="appointment_error",
            message=str(e),
        )

    except OAuthError as e:
        log_audit_event(
            event_type="appointments_today_failed",
            action="Executed appointments_today_failed",
            user_id="system",
            additional_data={"error": "authentication_error", "message": e.description},
        )
        raise HTTPException(
            status_code=401, detail=f"Authentication failed: {e.description}"
        )

    except Exception as e:
        log_audit_event(
            event_type="appointments_today_failed",
            action="Failed to retrieve today's appointments due to unexpected error",
            user_id="system",
            additional_data={"error": "unexpected_error", "message": str(e)},
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during appointment retrieval"
        )


@app.get("/api/v1/appointments", response_model=AppointmentListResponse)
@limiter.limit("30/minute")
async def get_appointments(
    request: Request,
    start_date: str = "",
    end_date: str = "",
    provider: str = "",
    status: str = "",
):
    """
    Get appointments with optional filtering.

    Query Parameters:
    - start_date: Start date for appointment range (YYYY-MM-DD format)
    - end_date: End date for appointment range (YYYY-MM-DD format)
    - provider: Provider reference to filter by (e.g., "Practitioner/123")
    - status: Appointment status to filter by

    Returns:
        AppointmentListResponse: Filtered appointments
    """
    try:
        # Validate date format if provided
        if start_date:
            try:
                from datetime import datetime

                datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="start_date must be in YYYY-MM-DD format"
                )

        if end_date:
            try:
                from datetime import datetime

                datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="end_date must be in YYYY-MM-DD format"
                )

        # Log appointment access request
        log_audit_event(
            event_type="appointments_filtered_requested",
            action="Executed appointments_filtered_requested",
            user_id="system",
            additional_data={
                "has_start_date": bool(start_date),
                "has_end_date": bool(end_date),
                "has_provider": bool(provider),
                "has_status": bool(status),
            },
        )

        # Get appointments based on filters
        if start_date and end_date:
            appointments = await appointment_service.get_appointments_by_date_range(
                start_date=start_date,
                end_date=end_date,
                practitioner_reference=provider if provider else None,
                status=status if status else None,
            )
        else:
            # Search appointments with individual filters
            appointments = await appointment_service.search_appointments(
                practitioner_reference=provider if provider else None,
                status=status if status else None,
            )

        # Convert to response format
        appointment_responses = [
            AppointmentResponse(**appointment.to_dict()) for appointment in appointments
        ]

        # Log successful access
        log_audit_event(
            event_type="appointments_filtered_completed",
            action="Executed appointments_filtered_completed",
            user_id="system",
            additional_data={"appointment_count": len(appointments)},
        )

        return AppointmentListResponse(
            status="success",
            appointments=appointment_responses,
            total=len(appointment_responses),
            message=f"Found {len(appointment_responses)} appointments",
        )

    except FHIRAppointmentError as e:
        log_audit_event(
            event_type="appointments_filtered_failed",
            action="Executed appointments_filtered_failed",
            user_id="system",
            additional_data={"error": "appointment_error", "message": str(e)},
        )
        return AppointmentListResponse(
            status="error",
            appointments=[],
            total=0,
            error="appointment_error",
            message=str(e),
        )

    except OAuthError as e:
        log_audit_event(
            event_type="appointments_filtered_failed",
            action="Executed appointments_filtered_failed",
            user_id="system",
            additional_data={"error": "authentication_error", "message": e.description},
        )
        raise HTTPException(
            status_code=401, detail=f"Authentication failed: {e.description}"
        )

    except Exception as e:
        log_audit_event(
            event_type="appointments_filtered_failed",
            action="Executed appointments_filtered_failed",
            user_id="system",
            additional_data={"error": "unexpected_error", "message": str(e)},
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during appointment retrieval"
        )


@app.get("/api/v1/providers", response_model=ProviderListResponse)
@limiter.limit("30/minute")
async def get_providers_for_filter(request: Request):
    """
    Get list of providers for filter dropdown.

    Returns:
        ProviderListResponse: Active providers for filtering
    """
    try:
        # Log provider access request
        log_audit_event(
            event_type="providers_filter_requested",
            action="Requested provider filter",
            user_id="system",
            additional_data={},
        )

        # Get providers
        providers = await provider_schedule_service.get_providers()

        # Convert to response format
        provider_responses = []
        for provider in providers:
            if provider.active:
                provider_responses.append(
                    ProviderResponse(
                        id=provider.id,
                        name=provider.name,
                        reference=f"Practitioner/{provider.id}",
                    )
                )

        # Log successful access
        log_audit_event(
            event_type="providers_filter_completed",
            action="Completed provider filter request",
            user_id="system",
            additional_data={"provider_count": len(provider_responses)},
        )

        return ProviderListResponse(
            status="success",
            providers=provider_responses,
            total=len(provider_responses),
            message=f"Found {len(provider_responses)} active providers",
        )

    except ProviderScheduleError as e:
        log_audit_event(
            event_type="providers_filter_failed",
            action="Failed provider filter request",
            user_id="system",
            additional_data={"error": "provider_error", "message": str(e)},
        )
        return ProviderListResponse(
            status="error",
            providers=[],
            total=0,
            error="provider_error",
            message=str(e),
        )

    except OAuthError as e:
        log_audit_event(
            event_type="providers_filter_failed",
            action="Failed provider filter request",
            user_id="system",
            additional_data={"error": "authentication_error", "message": e.description},
        )
        raise HTTPException(
            status_code=401, detail=f"Authentication failed: {e.description}"
        )

    except Exception as e:
        log_audit_event(
            event_type="providers_filter_failed",
            action="Failed provider filter request",
            user_id="system",
            additional_data={"error": "unexpected_error", "message": str(e)},
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during provider retrieval"
        )


if __name__ == "__main__":
    # Development server entry point
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["src"],
    )
