# **Data Models (Minimal for MVP)**

## **No Local Database Required**

All patient and appointment data remains in EMR. Local system only maintains:

```python
# Session data (in-memory only)
active_calls = {
    "call_id": {
        "start_time": datetime,
        "phone_hash": "sha256_hash",
        "status": "processing"
    }
}

# Configuration (config.json)
{
    "practice_name": "...",
    "emr_credentials": "encrypted",
    "api_keys": "encrypted",
    "operational_hours": {...}
}

# Audit logs (audit.log)
{"timestamp": "...", "event": "patient_access", "patient_id": "emr_id_only", "action": "appointment_create"}
```
