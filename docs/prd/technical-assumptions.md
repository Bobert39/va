# Technical Assumptions

## Repository Structure: Monorepo
Single repository containing all components (voice AI, web interface, EMR integration, configuration) to simplify solo developer workflow and deployment for practices.

## Service Architecture
**Monolith with Modular Components**: Single application deployment with clear separation between voice processing, EMR integration, web interface, and appointment management. This enables simple on-premise installation while maintaining code organization for future microservices expansion.

## Testing Requirements
**Unit + Integration**: Focus on critical path testing (EMR API integration, appointment creation, voice processing accuracy) with automated testing for core business logic and integration points. Manual testing for voice interaction flows due to complexity and MVP timeline constraints.

## Additional Technical Assumptions and Requests

**Programming Language & Framework:**
- **Backend**: Python 3.9+ with FastAPI for REST API and web interface serving
- **Frontend**: Vanilla JavaScript with Bootstrap for rapid MVP development
- **Rationale**: Python ecosystem rich in voice AI libraries, FastAPI provides automatic API documentation, minimal complexity for solo developer

**Voice Processing Technology:**
- **Speech-to-Text**: OpenAI Whisper (local processing) or Azure Speech Services (cloud backup)
- **Natural Language Processing**: OpenAI GPT-3.5/4 API for conversation management
- **Text-to-Speech**: Azure Speech Services or similar cloud provider
- **Rationale**: Balance between accuracy, cost, and HIPAA compliance requirements

**Database & Storage:**
- **Primary Database**: SQLite for MVP (simple deployment, no additional infrastructure)
- **Configuration Storage**: JSON files for practice-specific settings
- **Audit Logging**: Structured logging to files with rotation
- **Rationale**: Minimal infrastructure overhead, easy backup/restore, sufficient for single-practice deployment

**EMR Integration:**
- **Primary Target**: OpenEMR REST API and FHIR R4 endpoints
- **Authentication**: OAuth 2.0 with stored refresh tokens
- **Data Synchronization**: Real-time API calls with local caching for performance
- **Rationale**: Aligns with Project Brief focus, widely adopted standards

**Deployment & Infrastructure:**
- **Deployment Method**: Standalone executable with embedded web server
- **Operating System**: Windows 10+ (primary practice environment)
- **Installation**: Single installer package with setup wizard
- **Updates**: Manual update process for MVP, automated updates for production
- **Rationale**: Minimal technical requirements for practice staff, reliable deployment

**Security & Compliance:**
- **Encryption**: TLS 1.3 for all API communications, AES-256 for local data storage
- **Authentication**: Local admin accounts with session management
- **Audit Logging**: All appointment actions, API calls, and system events logged
- **PHI Handling**: Minimal PHI storage, immediate EMR synchronization
- **Rationale**: HIPAA compliance foundation with minimal complexity

**Development & Build Tools:**
- **Package Management**: Poetry for Python dependencies
- **Build System**: GitHub Actions for automated testing and releases
- **Code Quality**: Black formatter, flake8 linting, pytest for testing
- **Documentation**: Markdown documentation with architecture decision records
- **Rationale**: Standard Python ecosystem tools, automated quality gates

**Performance & Scalability:**
- **Concurrent Voice Calls**: Maximum 2 simultaneous calls for MVP
- **Response Time Target**: <2 seconds for voice processing, <500ms for web interface
- **Resource Usage**: <4GB RAM under normal operation, <50GB storage
- **Scalability Path**: Microservices architecture documented for future expansion
- **Rationale**: Conservative targets appropriate for practice hardware and MVP scope
