# Environment-Specific Setup Guide

## Overview
This guide covers environment-specific configurations for Development, Testing, and Production deployments of the Voice AI Platform.

## Development Environment

### Purpose
- Local development with hot reload
- Debug logging enabled
- Mock external services for offline work
- Fast iteration and testing

### Setup Steps

#### 1. Development Configuration
Create `config.dev.json`:
```json
{
  "practice_name": "Development Practice",
  "emr_credentials": {
    "base_url": "http://localhost:8080",
    "client_id": "dev_client_id",
    "client_secret": "dev_client_secret",
    "redirect_uri": "http://localhost:8000/auth/callback"
  },
  "api_keys": {
    "openai_api_key": "sk-dev-your-development-key",
    "twilio_account_sid": "dev_account_sid",
    "twilio_auth_token": "dev_auth_token",
    "azure_speech_key": "dev_speech_key",
    "azure_speech_region": "eastus"
  },
  "operational_hours": {
    "monday": {"start": "08:00", "end": "18:00"},
    "tuesday": {"start": "08:00", "end": "18:00"},
    "wednesday": {"start": "08:00", "end": "18:00"},
    "thursday": {"start": "08:00", "end": "18:00"},
    "friday": {"start": "08:00", "end": "18:00"},
    "saturday": {"start": "09:00", "end": "17:00"},
    "sunday": {"start": "10:00", "end": "16:00"}
  },
  "system_settings": {
    "log_level": "DEBUG",
    "max_call_duration_minutes": 15,
    "enable_audit_logging": true,
    "audit_log_rotation_mb": 5,
    "hot_reload": true,
    "mock_external_apis": true
  }
}
```

#### 2. Development Server Setup
```powershell
# Start development server with hot reload
poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Alternative: Debug mode with additional logging
$env:PYTHONPATH = "src"; poetry run uvicorn src.main:app --reload --log-level debug
```

#### 3. Development Environment Variables
```powershell
# Set environment variables for development
$env:VOICE_AI_ENV = "development"
$env:VOICE_AI_CONFIG = "config.dev.json"
$env:PYTHONPATH = "src"
```

#### 4. Development Dependencies
```powershell
# Install development dependencies
poetry install --with dev

# Enable pre-commit hooks
poetry run pre-commit install
```

### Development Best Practices

#### Hot Reload Configuration
- Uses `--reload` flag for automatic code reloading
- Watch additional directories if needed:
  ```powershell
  poetry run uvicorn src.main:app --reload --reload-dir src --reload-dir config
  ```

#### Debug Logging
- Set `log_level: "DEBUG"` in development config
- View logs in real-time:
  ```powershell
  poetry run python -c "import logging; logging.basicConfig(level=logging.DEBUG)"
  ```

#### Mock Services
Enable mock external APIs for offline development:
- EMR API mocking
- Twilio webhook simulation
- OpenAI API responses
- Azure Speech Service emulation

## Testing Environment

### Purpose
- Automated testing and CI/CD
- Integration testing with external services
- Performance benchmarking
- Quality assurance validation

### Setup Steps

#### 1. Testing Configuration
Create `config.test.json`:
```json
{
  "practice_name": "Test Practice",
  "emr_credentials": {
    "base_url": "https://test-emr.example.com",
    "client_id": "test_client_id",
    "client_secret": "test_client_secret",
    "redirect_uri": "http://localhost:8000/auth/callback"
  },
  "api_keys": {
    "openai_api_key": "sk-test-your-testing-key",
    "twilio_account_sid": "test_account_sid",
    "twilio_auth_token": "test_auth_token",
    "azure_speech_key": "test_speech_key",
    "azure_speech_region": "eastus"
  },
  "operational_hours": {
    "monday": {"start": "09:00", "end": "17:00"},
    "tuesday": {"start": "09:00", "end": "17:00"},
    "wednesday": {"start": "09:00", "end": "17:00"},
    "thursday": {"start": "09:00", "end": "17:00"},
    "friday": {"start": "09:00", "end": "17:00"},
    "saturday": {"closed": true},
    "sunday": {"closed": true}
  },
  "system_settings": {
    "log_level": "INFO",
    "max_call_duration_minutes": 10,
    "enable_audit_logging": true,
    "audit_log_rotation_mb": 10,
    "enable_metrics": true,
    "test_mode": true
  }
}
```

#### 2. Test Environment Setup
```powershell
# Set testing environment
$env:VOICE_AI_ENV = "testing"
$env:VOICE_AI_CONFIG = "config.test.json"

# Run tests with coverage
poetry run pytest --cov=src --cov-report=html

# Run integration tests
poetry run pytest tests/integration/ -v

# Run performance tests
poetry run pytest tests/performance/ -v
```

#### 3. Test Data Management
```powershell
# Initialize test database
poetry run python scripts/init_test_data.py

# Clean test data between runs
poetry run python scripts/clean_test_data.py
```

### Testing Environment Features

#### Automated Testing
- Unit tests with mocked dependencies
- Integration tests with test EMR instance
- End-to-end tests with Playwright
- Performance benchmarking

#### Test Data
- Synthetic patient data (HIPAA compliant)
- Mock appointment scenarios
- Test voice recordings
- Automated test case generation

#### CI/CD Integration
```yaml
# Example GitHub Actions configuration
- name: Setup Test Environment
  run: |
    cp config.test.json config.json
    poetry install --with dev
    poetry run pytest --cov=src --cov-fail-under=80
```

## Production Environment

### Purpose
- Live medical practice deployment
- Maximum security and compliance
- High availability and monitoring
- Audit logging and compliance

### Setup Steps

#### 1. Production Configuration
Create `config.prod.json` with encrypted sensitive values:
```json
{
  "practice_name": "Your Medical Practice Name",
  "emr_credentials": {
    "base_url": "https://your-emr-instance.com",
    "client_id": "ENCRYPTED_PROD_CLIENT_ID",
    "client_secret": "ENCRYPTED_PROD_CLIENT_SECRET",
    "redirect_uri": "https://your-domain.com/auth/callback"
  },
  "api_keys": {
    "openai_api_key": "ENCRYPTED_OPENAI_KEY",
    "twilio_account_sid": "ENCRYPTED_TWILIO_SID",
    "twilio_auth_token": "ENCRYPTED_TWILIO_TOKEN",
    "azure_speech_key": "ENCRYPTED_AZURE_KEY",
    "azure_speech_region": "your-azure-region"
  },
  "operational_hours": {
    "monday": {"start": "08:00", "end": "17:00"},
    "tuesday": {"start": "08:00", "end": "17:00"},
    "wednesday": {"start": "08:00", "end": "17:00"},
    "thursday": {"start": "08:00", "end": "17:00"},
    "friday": {"start": "08:00", "end": "17:00"},
    "saturday": {"start": "09:00", "end": "13:00"},
    "sunday": {"closed": true}
  },
  "system_settings": {
    "log_level": "WARNING",
    "max_call_duration_minutes": 8,
    "enable_audit_logging": true,
    "audit_log_rotation_mb": 25,
    "enable_monitoring": true,
    "production_mode": true
  }
}
```

#### 2. Production Security Setup
```powershell
# Set secure environment variables
$env:VOICE_AI_ENV = "production"
$env:VOICE_AI_CONFIG = "config.prod.json"
$env:ENCRYPTION_KEY = "your-32-character-encryption-key"

# Set secure file permissions (requires administrator)
icacls config.prod.json /grant:r "SYSTEM:F" /grant:r "Administrators:F" /inheritance:r
```

#### 3. Production Server Setup
```powershell
# Start production server
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4

# Or with production WSGI server (recommended)
poetry run gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Production Deployment Hardening

#### Security Configuration
1. **Encryption**: All sensitive config values encrypted
2. **HTTPS**: SSL/TLS certificates configured
3. **Firewall**: Windows Firewall configured for port 8000
4. **Audit Logging**: Comprehensive audit trail enabled
5. **Access Control**: File permissions restricted

#### Monitoring and Logging
```powershell
# Enable Windows Event Log integration
poetry run python scripts/setup_windows_logging.py

# Configure log rotation
poetry run python scripts/setup_log_rotation.py
```

#### Backup and Recovery
```powershell
# Backup configuration (excluding sensitive data)
poetry run python scripts/backup_config.py

# Database backup (if applicable)
poetry run python scripts/backup_database.py
```

## Docker Deployment (Optional)

### Development Container
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev
COPY . .
CMD ["poetry", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production Container
```dockerfile
FROM python:3.11-slim
RUN adduser --disabled-password --gecos '' appuser
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev --no-cache
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
CMD ["poetry", "run", "gunicorn", "src.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

### Docker Compose
```yaml
version: '3.8'
services:
  voice-ai:
    build: .
    ports:
      - "8000:8000"
    environment:
      - VOICE_AI_ENV=production
    volumes:
      - ./config.prod.json:/app/config.json:ro
      - ./logs:/app/logs
```

## Environment Comparison

| Feature | Development | Testing | Production |
|---------|------------|---------|------------|
| Hot Reload | ✅ Enabled | ❌ Disabled | ❌ Disabled |
| Debug Logging | ✅ DEBUG level | ℹ️ INFO level | ⚠️ WARNING level |
| Mock APIs | ✅ Enabled | ❌ Disabled | ❌ Disabled |
| Encryption | ❌ Optional | ✅ Recommended | ✅ Required |
| Monitoring | ❌ Basic | ✅ Enhanced | ✅ Full |
| Security | 🟨 Basic | 🟩 Enhanced | 🟩 Maximum |

## Environment Switching

### Quick Environment Switch
```powershell
# Switch to development
$env:VOICE_AI_CONFIG = "config.dev.json"

# Switch to testing
$env:VOICE_AI_CONFIG = "config.test.json"

# Switch to production
$env:VOICE_AI_CONFIG = "config.prod.json"
```

### Environment Validation
```powershell
# Validate current environment configuration
poetry run python -c "from src.config import get_config; print(get_config().practice_name)"
```

## Troubleshooting Environment Issues

### Common Problems

**Problem**: Configuration not loading
- **Check**: Environment variable `VOICE_AI_CONFIG` is set
- **Verify**: Config file exists and is readable
- **Solution**: Use absolute path to config file

**Problem**: Port already in use
- **Check**: `netstat -an | findstr :8000`
- **Solution**: Kill existing process or use different port

**Problem**: SSL certificate errors in production
- **Check**: Certificate validity and expiration
- **Solution**: Renew certificate or configure proper certificate chain

**Problem**: Mock services not working in development
- **Check**: `mock_external_apis: true` in config
- **Verify**: Mock service modules are installed
- **Solution**: Run `poetry install --with dev` to include mock dependencies

## Next Steps

After environment setup:
1. **Validate Configuration**: Run [validation procedures](validation-guide.md)
2. **Configure Monitoring**: Set up appropriate monitoring for your environment
3. **Security Review**: Review [security configuration](security-guide.md)
4. **Backup Setup**: Configure backup procedures for production
