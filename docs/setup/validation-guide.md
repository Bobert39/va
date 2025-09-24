# First-Run Validation Guide

## Overview
This guide provides step-by-step procedures to validate your Voice AI Platform installation and ensure all components are working correctly before going live.

## Pre-Validation Checklist

Before starting validation, ensure you have completed:
- ✅ [Installation Guide](installation-guide.md) - Python, Poetry, and dependencies installed
- ✅ [Environment Setup](environment-setup.md) - Environment configured for your use case
- ✅ [Configuration](configuration-reference.md) - config.json file properly configured

## Validation Levels

### Level 1: System Health Check (5 minutes)
Basic system functionality and configuration validation

### Level 2: API Connectivity (10 minutes)
External service integration testing

### Level 3: Core Functionality (15 minutes)
End-to-end workflow testing

### Level 4: Production Readiness (30 minutes)
Comprehensive deployment validation

---

## Level 1: System Health Check

### 1.1 Environment Validation

**Check Python and Poetry**:
```powershell
# Verify Python version
python --version
# Expected: Python 3.9.x, 3.10.x, or 3.11.x

# Verify Poetry installation
poetry --version
# Expected: Poetry version 1.6.0 or later

# Check virtual environment
poetry env info
# Expected: Shows virtual environment path and Python version
```

**Expected Output Examples**:
```
Python 3.11.5
Poetry version 1.7.0
```

### 1.2 Dependencies Check

**Verify all dependencies installed**:
```powershell
# Check installed packages
poetry show

# Verify critical packages
poetry show fastapi uvicorn openai twilio cryptography

# Check development dependencies (if needed)
poetry show --only dev
```

**Expected Result**: All packages listed without errors, versions match pyproject.toml

### 1.3 Configuration Loading

**Test configuration file loading**:
```powershell
# Test basic configuration loading
poetry run python -c "from src.config import get_config; config = get_config(); print(f'Practice: {config.practice_name}')"

# Test encryption (if using encrypted values)
poetry run python -c "from src.config import get_config; config = get_config(); print('Config loaded with encryption support')"
```

**Expected Output**:
```
Practice: Your Practice Name
Config loaded with encryption support
```

**Troubleshooting Level 1 Issues**:

❌ **Python version incorrect**:
```powershell
# Solution: Install correct Python version
# Download from python.org or use Microsoft Store
```

❌ **Poetry not found**:
```powershell
# Solution: Add Poetry to PATH
$env:PATH += ";$env:USERPROFILE\AppData\Roaming\Python\Scripts"
```

❌ **Config loading fails**:
```powershell
# Solution: Check config file exists and syntax
ls config.json
poetry run python -m json.tool config.json
```

### 1.4 Port Availability Check

**Check if required ports are available**:
```powershell
# Check if port 8000 is available
netstat -an | findstr :8000

# If port is in use, find the process
netstat -ano | findstr :8000
```

**Expected Result**: No output (port is free) or controlled by your application

---

## Level 2: API Connectivity Testing

### 2.1 Application Startup Test

**Start the application**:
```powershell
# Start development server
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000

# Alternative: Start with specific config
$env:VOICE_AI_CONFIG = "config.json"
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**Expected Output**:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 2.2 Health Endpoint Validation

**Test basic application health** (in new PowerShell window):
```powershell
# Test health endpoint
curl http://localhost:8000/health

# Alternative using PowerShell
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
```

**Expected Response**:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2023-12-01T10:30:00Z"
}
```

### 2.3 API Documentation Access

**Verify API documentation is accessible**:
```powershell
# Open API documentation in browser
start http://localhost:8000/docs

# Alternative: Test API docs endpoint
curl http://localhost:8000/openapi.json
```

**Expected Result**: Browser opens FastAPI Swagger documentation interface

### 2.4 Dashboard Access

**Test web dashboard accessibility**:
```powershell
# Open dashboard in browser
start http://localhost:8000/dashboard

# Alternative: Test dashboard endpoint
curl http://localhost:8000/dashboard
```

**Expected Result**: Dashboard loads with basic interface elements

### 2.5 External API Connectivity

**Test OpenAI API connection**:
```powershell
# Test OpenAI API connectivity
poetry run python -c "
import openai
from src.config import get_config
config = get_config()
client = openai.OpenAI(api_key=config.api_keys.openai_api_key)
try:
    response = client.chat.completions.create(
        model='gpt-3.5-turbo',
        messages=[{'role': 'user', 'content': 'Test connection'}],
        max_tokens=5
    )
    print('OpenAI API: ✅ Connected')
except Exception as e:
    print(f'OpenAI API: ❌ Error - {e}')
"
```

**Test Twilio API connection**:
```powershell
# Test Twilio API connectivity
poetry run python -c "
from twilio.rest import Client
from src.config import get_config
config = get_config()
try:
    client = Client(config.api_keys.twilio_account_sid, config.api_keys.twilio_auth_token)
    account = client.api.accounts(config.api_keys.twilio_account_sid).fetch()
    print('Twilio API: ✅ Connected')
except Exception as e:
    print(f'Twilio API: ❌ Error - {e}')
"
```

**Test Azure Speech Service**:
```powershell
# Test Azure Speech Service connectivity
poetry run python -c "
import requests
from src.config import get_config
config = get_config()
try:
    url = f'https://{config.api_keys.azure_speech_region}.api.cognitive.microsoft.com/sts/v1.0/issueToken'
    headers = {'Ocp-Apim-Subscription-Key': config.api_keys.azure_speech_key}
    response = requests.post(url, headers=headers, timeout=10)
    if response.status_code == 200:
        print('Azure Speech API: ✅ Connected')
    else:
        print(f'Azure Speech API: ❌ Error - Status {response.status_code}')
except Exception as e:
    print(f'Azure Speech API: ❌ Error - {e}')
"
```

**Expected Results**:
```
OpenAI API: ✅ Connected
Twilio API: ✅ Connected
Azure Speech API: ✅ Connected
```

---

## Level 3: Core Functionality Testing

### 3.1 Configuration Endpoint Test

**Test configuration API**:
```powershell
# Test configuration endpoint (should not expose sensitive data)
curl http://localhost:8000/api/config

# Alternative
Invoke-RestMethod -Uri "http://localhost:8000/api/config" -Method Get
```

**Expected Response** (sensitive data masked):
```json
{
  "practice_name": "Your Practice Name",
  "operational_hours": {
    "monday": {"start": "09:00", "end": "17:00"}
  },
  "system_settings": {
    "log_level": "INFO",
    "max_call_duration_minutes": 10
  }
}
```

### 3.2 EMR Integration Test

**Test EMR OAuth flow initiation**:
```powershell
# Test EMR OAuth initialization
curl http://localhost:8000/api/emr/auth/init

# Alternative
Invoke-RestMethod -Uri "http://localhost:8000/api/emr/auth/init" -Method Post
```

**Expected Response**:
```json
{
  "auth_url": "https://your-emr.com/oauth/authorize?client_id=...",
  "state": "random-state-string"
}
```

### 3.3 Voice Processing Test

**Test speech-to-text capability**:
```powershell
# Test voice processing endpoint with sample audio
curl -X POST http://localhost:8000/api/voice/process \
  -H "Content-Type: multipart/form-data" \
  -F "audio=@test-audio.wav"

# Note: You'll need a test audio file for this test
```

### 3.4 Appointment Scheduling Simulation

**Test appointment scheduling logic**:
```powershell
# Test appointment scheduling with mock data
curl -X POST http://localhost:8000/api/appointments/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "patient_name": "Test Patient",
    "appointment_type": "consultation",
    "preferred_date": "2023-12-15",
    "preferred_time": "10:00"
  }'
```

**Expected Response**:
```json
{
  "status": "scheduled",
  "appointment_id": "apt_123456",
  "scheduled_time": "2023-12-15T10:00:00Z",
  "confirmation_code": "CONF123"
}
```

### 3.5 Audit Logging Verification

**Verify audit logging is working**:
```powershell
# Check if audit logs are being created
ls logs/

# View recent audit log entries
Get-Content logs/audit.log | Select-Object -Last 10
```

**Expected Result**: Log files exist and contain recent entries

---

## Level 4: Production Readiness Validation

### 4.1 Performance Testing

**Basic performance test**:
```powershell
# Test response time for health endpoint
Measure-Command {
  Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
}

# Expected: TotalMilliseconds under 200ms
```

**Load testing** (if ab.exe available):
```powershell
# Simple load test (install Apache Bench if needed)
ab -n 100 -c 10 http://localhost:8000/health
```

### 4.2 Security Validation

**Test HTTPS configuration** (production only):
```powershell
# Test HTTPS endpoint
curl https://your-domain.com/health

# Verify SSL certificate
curl -I https://your-domain.com/health
```

**Verify sensitive data protection**:
```powershell
# Ensure config endpoint doesn't expose secrets
curl http://localhost:8000/api/config | Select-String "secret|key|token"
# Expected: No sensitive values in output
```

### 4.3 Backup and Recovery Test

**Test configuration backup**:
```powershell
# Create configuration backup
poetry run python scripts/backup_config.py

# Verify backup was created
ls backups/
```

### 4.4 Monitoring and Alerting

**Test monitoring endpoints** (if enabled):
```powershell
# Test metrics endpoint
curl http://localhost:8000/metrics

# Test health check endpoint
curl http://localhost:8000/health/detailed
```

### 4.5 Integration Testing

**End-to-end workflow test**:
```powershell
# Test complete appointment scheduling workflow
# This requires manual testing through the web interface:
# 1. Open http://localhost:8000/dashboard
# 2. Initiate voice call simulation
# 3. Process appointment request
# 4. Verify EMR integration
# 5. Confirm audit logging
```

---

## Automated Validation Script

Create a comprehensive validation script:

```powershell
# Create validation script
@"
# Voice AI Platform Validation Script
Write-Host "Starting Voice AI Platform Validation..." -ForegroundColor Green

# Level 1: System Health
Write-Host "`nLevel 1: System Health Check" -ForegroundColor Yellow
python --version
poetry --version
poetry run python -c "from src.config import get_config; print('✅ Config loaded successfully')"

# Level 2: API Connectivity
Write-Host "`nLevel 2: API Connectivity" -ForegroundColor Yellow
# Start server in background
Start-Process -FilePath "poetry" -ArgumentList "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000" -WindowStyle Hidden
Start-Sleep -Seconds 5

# Test endpoints
try {
    `$health = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 10
    Write-Host "✅ Health endpoint: OK" -ForegroundColor Green
} catch {
    Write-Host "❌ Health endpoint: FAILED" -ForegroundColor Red
}

Write-Host "`nValidation complete!" -ForegroundColor Green
"@ | Out-File -FilePath "validate.ps1"

# Run validation script
.\validate.ps1
```

---

## Validation Checklist

### Pre-Production Checklist

- [ ] **Level 1 Complete**: System health checks pass
- [ ] **Level 2 Complete**: API connectivity confirmed
- [ ] **Level 3 Complete**: Core functionality tested
- [ ] **Level 4 Complete**: Production readiness validated

### Specific Validations

#### Configuration
- [ ] Config file loads without errors
- [ ] All required fields present
- [ ] Encrypted fields decrypt correctly
- [ ] Operational hours configured properly

#### External Services
- [ ] OpenAI API connection successful
- [ ] Twilio API connection successful
- [ ] Azure Speech API connection successful
- [ ] EMR system OAuth flow works

#### Application
- [ ] Server starts without errors
- [ ] Health endpoint responds correctly
- [ ] API documentation accessible
- [ ] Dashboard loads properly
- [ ] Audit logging functional

#### Security
- [ ] Sensitive data not exposed in API responses
- [ ] HTTPS configured (production)
- [ ] File permissions set correctly
- [ ] Encryption keys secured

#### Performance
- [ ] Response times under 200ms for health checks
- [ ] Memory usage reasonable (< 500MB baseline)
- [ ] Log files rotating properly
- [ ] No memory leaks detected

---

## Troubleshooting Common Validation Issues

### Application Won't Start

❌ **Error**: `ModuleNotFoundError: No module named 'src'`
```powershell
# Solution: Set PYTHONPATH
$env:PYTHONPATH = "src"
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

❌ **Error**: `Port 8000 already in use`
```powershell
# Solution: Kill existing process or use different port
netstat -ano | findstr :8000
# Kill process with PID shown, then retry
```

### Configuration Issues

❌ **Error**: `Configuration file not found`
```powershell
# Solution: Check file path and name
ls config.json
$env:VOICE_AI_CONFIG = "config.json"
```

❌ **Error**: `Cannot decrypt encrypted values`
```powershell
# Solution: Set encryption key
$env:VOICE_AI_ENCRYPTION_KEY = "your-32-character-key"
```

### API Connection Issues

❌ **Error**: `OpenAI API authentication failed`
- Check API key is valid and active
- Verify sufficient credits in OpenAI account
- Test key directly: https://platform.openai.com/account/api-keys

❌ **Error**: `Twilio authentication failed`
- Verify Account SID format (starts with "AC")
- Check Auth Token is current
- Test credentials in Twilio Console

❌ **Error**: `Azure Speech Service failed`
- Verify subscription key is active
- Check region matches your Azure resource
- Confirm service is enabled in Azure portal

### Performance Issues

❌ **Issue**: Slow response times (>1 second)
- Check system resources (CPU, memory)
- Review log level (DEBUG can be slow)
- Verify network connectivity to external APIs

❌ **Issue**: High memory usage
- Check for memory leaks in application logs
- Monitor long-running processes
- Consider restarting application periodically

### Networking Issues

❌ **Issue**: Dashboard not accessible
```powershell
# Solution: Check firewall and network settings
netsh advfirewall firewall add rule name="Voice AI Platform" dir=in action=allow protocol=TCP localport=8000
```

---

## Post-Validation Steps

After successful validation:

1. **Document Results**: Record validation date and results
2. **Create Monitoring**: Set up ongoing health monitoring
3. **Schedule Maintenance**: Plan regular validation runs
4. **Train Users**: Provide user training on validated system
5. **Go Live**: Begin production operation

### Ongoing Validation

**Daily Health Check**:
```powershell
# Create daily health check script
curl http://localhost:8000/health | Out-File -FilePath "logs/health-$(Get-Date -Format 'yyyy-MM-dd').log" -Append
```

**Weekly Full Validation**:
- Run full validation script
- Review audit logs
- Check performance metrics
- Verify backup integrity

## Related Documentation

- [Installation Guide](installation-guide.md) - Initial setup
- [Configuration Reference](configuration-reference.md) - Configuration details
- [Troubleshooting Guide](troubleshooting.md) - Issue resolution
- [User Guide](../user-guide.md) - End-user documentation
