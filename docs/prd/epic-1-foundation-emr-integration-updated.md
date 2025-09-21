# Epic 1: Foundation & EMR Integration (Updated)

**Expanded Goal:** Establish project infrastructure and prove both OpenEMR viewing AND appointment creation viability while delivering immediate value through appointment viewing capability. **CRITICAL: Must validate appointment creation APIs before Epic 2 commitment.**

## Story 1.1: Project Infrastructure Setup
As a **developer**,
I want **complete project environment with dependencies and build tools**,
so that **I can develop efficiently with proper testing and deployment capabilities**.

### Acceptance Criteria
1. Python 3.9+ environment with Poetry dependency management configured
2. FastAPI application structure with automatic API documentation
3. SQLite database with initial schema for appointments and configuration
4. pytest testing framework with coverage reporting setup
5. GitHub repository with automated CI/CD pipeline using GitHub Actions
6. Development environment runs locally with hot reload capability
7. Code quality tools (Black, flake8) integrated with pre-commit hooks

## Story 1.2: OpenEMR OAuth Authentication
As a **system administrator**,
I want **secure authentication with OpenEMR instance**,
so that **the voice AI can access patient data safely and legally**.

### Acceptance Criteria
1. OAuth 2.0 client registration process documented and tested
2. Authorization code flow implementation with PKCE security
3. Access token and refresh token storage with encryption
4. Token refresh automation to maintain persistent access
5. Authentication failure handling with clear error messages
6. Test suite validates authentication against local OpenEMR instance
7. Configuration interface for practice staff to enter OAuth credentials

## Story 1.3: Patient Lookup via FHIR API
As a **practice staff member**,
I want **the system to find patient records by name and date of birth**,
so that **voice appointments can be linked to existing patient accounts**.

### Acceptance Criteria
1. FHIR R4 Patient resource search by name and birthdate
2. Patient demographic data retrieval (name, DOB, contact info, insurance)
3. Multiple patient matching handled with disambiguation logic
4. API error handling for network failures and invalid responses
5. Patient search results cached for session performance
6. Search accuracy tested with minimum 20 test patient records
7. No PHI logged in application logs or error messages

## Story 1.4: OpenEMR Appointment Creation API Validation (NEW - BLOCKING STORY)
As a **developer**,
I want **to prove OpenEMR appointment creation works reliably**,
so that **Epic 2 voice scheduling is technically feasible**.

### Acceptance Criteria
1. Successfully create test appointments via OpenEMR appointment API
2. Verify appointments appear correctly in OpenEMR interface
3. Test appointment modification and cancellation capabilities
4. Document API limitations, quirks, and workarounds required
5. Validate conflict detection when attempting double-booking
6. Test with multiple appointment types and providers
7. **BLOCKING GATE**: Epic 2 cannot proceed until this story is 100% complete

## Story 1.5: Provider Schedule Retrieval (Updated)
As a **practice staff member**,
I want **the system to display provider schedules and availability**,
so that **I can verify appointment slots before voice booking begins**.

### Acceptance Criteria (Updated)
1. Retrieve provider schedules via OpenEMR appointment API
2. Display available time slots for next 30 days by provider
3. Show existing appointments to identify conflicts
4. Handle multiple provider schedules in single practice
5. Schedule data refreshed automatically every 15 minutes
6. Provider working hours and break times properly represented
7. **VALIDATION ADDED**: Test with real EMR data quality issues (duplicates, missing data, inconsistent formats)

## Story 1.6: Basic Web Interface for Appointment Viewing
As a **practice staff member**,
I want **a simple web interface to view retrieved appointment data**,
so that **I can verify the system is working correctly with real data**.

### Acceptance Criteria
1. Clean HTML interface displaying today's appointments
2. Provider filter to view schedules by individual provider
3. Date range selector for viewing future appointments
4. Appointment details include patient name, time, type, provider
5. Real-time updates when appointment data changes
6. Mobile-friendly responsive design for basic viewing
7. Session timeout and logout functionality for security
