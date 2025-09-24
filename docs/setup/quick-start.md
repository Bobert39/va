# Quick Start Guide - Experienced Developers

## Overview
**Target Time**: < 10 minutes to running system
**Audience**: Experienced developers familiar with Python, Poetry, and web APIs
**Prerequisites**: Python 3.9+, basic understanding of EMR integration

## ⚡ Express Setup (5 minutes)

### 1. Install & Setup (2 minutes)
```powershell
# Verify Python version (3.9, 3.10, or 3.11)
python --version

# Install Poetry if not present
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Clone project and install dependencies
git clone <repository-url>
cd voice-ai-platform
poetry install

# Verify installation
poetry run python -c "print('✅ Installation successful')"
```

### 2. Configure (2 minutes)
```powershell
# Create config from template
copy config.example.json config.json

# Quick config for development (edit these values)
@{
  practice_name = "Dev Practice"
  emr_credentials = @{
    base_url = "http://localhost:8080"
    client_id = "dev_client"
    client_secret = "dev_secret"
    redirect_uri = "http://localhost:8000/auth/callback"
  }
  api_keys = @{
    openai_api_key = "sk-your-openai-key"
    twilio_account_sid = "AC-your-twilio-sid"
    twilio_auth_token = "your-twilio-token"
    azure_speech_key = "your-azure-key"
    azure_speech_region = "eastus"
  }
  operational_hours = @{
    monday = @{start="09:00"; end="17:00"}
    tuesday = @{start="09:00"; end="17:00"}
    wednesday = @{start="09:00"; end="17:00"}
    thursday = @{start="09:00"; end="17:00"}
    friday = @{start="09:00"; end="17:00"}
    saturday = @{closed=$true}
    sunday = @{closed=$true}
  }
  system_settings = @{
    log_level = "DEBUG"
    max_call_duration_minutes = 10
    enable_audit_logging = $true
    audit_log_rotation_mb = 10
  }
} | ConvertTo-Json -Depth 10 | Out-File config.json
```

### 3. Start & Validate (1 minute)
```powershell
# Start development server
poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Quick health check (in new terminal)
curl http://localhost:8000/health

# Open API docs
start http://localhost:8000/docs
```

---

## 🚀 One-Line Commands

**Complete setup for experienced developers**:
```powershell
# Single command setup (modify API keys first)
git clone <repo> && cd voice-ai-platform && poetry install && cp config.example.json config.json && echo "Edit config.json with your API keys, then run: poetry run uvicorn src.main:app --reload"
```

**Development server with debug**:
```powershell
$env:PYTHONPATH="src"; poetry run uvicorn src.main:app --reload --log-level debug
```

**Production server**:
```powershell
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🔧 Developer Shortcuts

### Environment Setup
```powershell
# Set development environment variables
$env:VOICE_AI_ENV = "development"
$env:VOICE_AI_CONFIG = "config.dev.json"
$env:PYTHONPATH = "src"

# Quick virtual environment check
poetry env info --path
```

### Configuration Shortcuts
```powershell
# Test config loading
poetry run python -c "from src.config import get_config; print(get_config().practice_name)"

# Validate JSON syntax
python -m json.tool config.json

# Generate encryption key
[System.Web.Security.Membership]::GeneratePassword(32, 0)
```

### API Testing
```powershell
# Health check
curl http://localhost:8000/health

# API documentation
curl http://localhost:8000/openapi.json

# Test configuration endpoint
curl http://localhost:8000/api/config
```

### Database Operations
```powershell
# Initialize database (if applicable)
poetry run python scripts/init_database.py

# Reset database for testing
poetry run python scripts/reset_database.py
```

---

## 📁 Project Structure Quick Reference

```
voice-ai-platform/
├── src/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── services/            # Business logic services
│   ├── api/                 # API route definitions
│   └── models/              # Data models
├── tests/
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── e2e/                 # End-to-end tests
├── docs/
│   └── setup/               # Setup documentation
├── config.json              # Configuration file (create from example)
├── pyproject.toml           # Poetry dependencies and settings
└── README.md                # Basic project information
```

---

## 🧪 Testing & Quality

### Run All Tests
```powershell
# Full test suite with coverage
poetry run pytest --cov=src --cov-report=html

# Quick unit tests only
poetry run pytest tests/unit/ -v

# Integration tests
poetry run pytest tests/integration/ -v
```

### Code Quality
```powershell
# Format code
poetry run black src/ tests/

# Lint code
poetry run flake8 src/ tests/

# Type checking
poetry run mypy src/

# Security scan
poetry run bandit -r src/
```

### Pre-commit Setup
```powershell
# Install pre-commit hooks
poetry run pre-commit install

# Run hooks manually
poetry run pre-commit run --all-files
```

---

## 🔌 API Integration Essentials

### OpenAI Configuration
```json
{
  "api_keys": {
    "openai_api_key": "sk-proj-your-key-here"
  }
}
```
**Test**: `curl -H "Authorization: Bearer sk-your-key" https://api.openai.com/v1/models`

### Twilio Setup
```json
{
  "api_keys": {
    "twilio_account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "twilio_auth_token": "your-auth-token"
  }
}
```
**Test**: `curl -u "sid:token" https://api.twilio.com/2010-04-01/Accounts.json`

### Azure Speech Service
```json
{
  "api_keys": {
    "azure_speech_key": "your-subscription-key",
    "azure_speech_region": "eastus"
  }
}
```
**Test**: `curl -H "Ocp-Apim-Subscription-Key: key" https://eastus.api.cognitive.microsoft.com/sts/v1.0/issueToken -X POST`

---

## 🐛 Common Quick Fixes

### Module Import Issues
```powershell
# Fix PYTHONPATH
$env:PYTHONPATH = "src"

# Or run from project root
cd /path/to/voice-ai-platform
```

### Port Conflicts
```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID)
taskkill /PID 1234 /F

# Or use different port
poetry run uvicorn src.main:app --port 8001
```

### Poetry Issues
```powershell
# Clear cache and reinstall
poetry cache clear . --all
poetry install

# Reset virtual environment
poetry env remove python
poetry install
```

---

## 🔄 Development Workflow

### Standard Development Loop
```powershell
# 1. Start development server
poetry run uvicorn src.main:app --reload

# 2. Make changes to code

# 3. Run tests
poetry run pytest tests/unit/

# 4. Check code quality
poetry run black src/
poetry run flake8 src/

# 5. Commit changes
git add .
git commit -m "feat: your changes"
```

### Debug Mode
```powershell
# Enable debug logging
$env:VOICE_AI_LOG_LEVEL = "DEBUG"

# Start with debug
poetry run uvicorn src.main:app --reload --log-level debug
```

### Production Testing
```powershell
# Test with production-like settings
$env:VOICE_AI_ENV = "production"
poetry run uvicorn src.main:app --workers 2 --port 8000
```

---

## 📊 Performance Monitoring

### Quick Performance Check
```powershell
# Response time test
Measure-Command { curl http://localhost:8000/health }

# Memory usage
Get-Process python | Select-Object WorkingSet64

# Load test (if ab.exe available)
ab -n 100 -c 10 http://localhost:8000/health
```

---

## 🔐 Security Essentials

### Encryption Setup
```powershell
# Generate encryption key
$key = [System.Web.Security.Membership]::GeneratePassword(32, 0)
$env:VOICE_AI_ENCRYPTION_KEY = $key

# Encrypt sensitive values
poetry run python scripts/encrypt_config.py --field "api_keys.openai_api_key" --value "sk-your-key"
```

### Production Security
```powershell
# Secure config file permissions (requires admin)
icacls config.json /grant:r "SYSTEM:F" /grant:r "Administrators:F" /inheritance:r

# Firewall rule for port 8000
netsh advfirewall firewall add rule name="Voice AI" dir=in action=allow protocol=TCP localport=8000
```

---

## 🚨 Troubleshooting Speedrun

### Can't start application?
```powershell
# Check basics
python --version  # 3.9-3.11?
poetry --version  # 1.6+?
ls config.json    # Exists?
netstat -an | findstr :8000  # Port free?
```

### API calls failing?
```powershell
# Test external APIs directly
curl -H "Authorization: Bearer sk-your-key" https://api.openai.com/v1/models
curl -u "twilio_sid:token" https://api.twilio.com/2010-04-01/Accounts.json
```

### Import errors?
```powershell
$env:PYTHONPATH = "src"
cd /path/to/project/root
```

---

## 📚 Essential Documentation Links

- **Full Setup**: [Installation Guide](installation-guide.md) (for comprehensive setup)
- **Configuration**: [Configuration Reference](configuration-reference.md) (all options)
- **Troubleshooting**: [Troubleshooting Guide](troubleshooting.md) (detailed solutions)
- **Validation**: [Validation Guide](validation-guide.md) (testing procedures)
- **API Docs**: http://localhost:8000/docs (when running)

---

## 💡 Pro Tips

### Productivity Shortcuts
- **Use Poetry shell**: `poetry shell` to activate virtual environment
- **Hot reload**: `--reload` flag automatically restarts on code changes
- **Debug endpoint**: Access `/api/debug` for detailed system information
- **Log streaming**: `tail -f logs/app.log` to watch logs in real-time

### Configuration Tips
- **Environment overrides**: Use `$env:VOICE_AI_*` variables for temporary config changes
- **Multiple configs**: Use `$env:VOICE_AI_CONFIG` to switch between config files
- **Config validation**: Run `poetry run python -c "from src.config import validate_config; validate_config()"` to validate

### Testing Tips
- **Quick smoke test**: `curl http://localhost:8000/health` after any changes
- **Auto-testing**: Use `pytest-watch` for continuous testing during development
- **Coverage focus**: `--cov-report=term-missing` shows which lines need tests

### Performance Tips
- **Development**: Use single worker with `--reload`
- **Testing**: Use `--workers 1` for consistent testing
- **Production**: Use `--workers 4` (or CPU count) for production

---

## 🎯 Success Criteria

✅ **Setup Complete When**:
- Server starts without errors in < 30 seconds
- Health endpoint returns `200 OK`
- API documentation accessible at `/docs`
- External API connections successful (OpenAI, Twilio, Azure)
- Log files created and updating

✅ **Ready for Development When**:
- Hot reload working (changes trigger restart)
- Tests pass: `pytest tests/unit/`
- Code quality checks pass: `black` and `flake8`
- Debug logging available

✅ **Production Ready When**:
- All validation steps pass (see [Validation Guide](validation-guide.md))
- Security configuration complete
- Monitoring and logging configured
- Backup procedures in place

**Time to Success**: Experienced developers should achieve setup complete status in < 10 minutes with proper API keys.
