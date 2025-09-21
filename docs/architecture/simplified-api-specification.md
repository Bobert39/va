# **Simplified API Specification**

## **Core Endpoints (5 Total for MVP)**

```yaml
# Voice Processing
POST /api/v1/voice/call
  Description: Process incoming voice call
  Auth: API Key
  Body: { audio_url, phone_number }
  Response: { status, appointment_id, confirmation_audio }

# Dashboard Data
GET /api/v1/appointments/today
  Description: Get today's AI appointments
  Auth: Session
  Response: { appointments: [...] }

# System Health
GET /api/v1/status
  Description: System health check
  Auth: None
  Response: { status, emr_connected, voice_ai_connected }

# Admin Interface
GET /dashboard
  Description: Serve admin dashboard
  Auth: Basic Auth
  Response: HTML page

# Configuration
POST /api/v1/config
  Description: Update configuration
  Auth: Session
  Body: { config updates }
  Response: { status: "updated" }
```
