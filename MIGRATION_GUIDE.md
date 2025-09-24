# Configuration Migration Guide: config.json → .env

## 📢 Important Notice

The Voice AI Platform is migrating from `config.json` to `.env` file configuration. This change improves security, simplifies deployment, and follows industry best practices.

## Why This Change?

### Problems with config.json:
- ❌ API keys in plain JSON files risk exposure
- ❌ Confusing dual configuration (both .env and config.json)
- ❌ Difficult environment-specific configurations
- ❌ Not container/cloud friendly

### Benefits of .env:
- ✅ Industry standard for configuration
- ✅ Automatic gitignore protection
- ✅ Easy environment variable injection
- ✅ Type-safe validation with Pydantic
- ✅ Single source of truth

## Migration Steps

### 1. Create Your .env File

```bash
# Copy the template
cp .env.example .env
```

### 2. Transfer Your Settings

Map your `config.json` values to the new `.env` format:

#### Practice Information
```json
// OLD (config.json)
"practice_name": "Medical Center"

// NEW (.env)
PRACTICE_NAME="Medical Center"
```

#### EMR Credentials
```json
// OLD (config.json)
"emr_credentials": {
  "base_url": "https://emr.example.com",
  "client_id": "abc123",
  "client_secret": "secret123"
}

// NEW (.env)
EMR_BASE_URL="https://emr.example.com"
EMR_CLIENT_ID="abc123"
EMR_CLIENT_SECRET="secret123"
```

#### API Keys
```json
// OLD (config.json)
"api_keys": {
  "openai_api_key": "sk-...",
  "twilio_account_sid": "AC...",
  "twilio_auth_token": "...",
  "azure_speech_key": "...",
  "azure_speech_region": "westus2"
}

// NEW (.env)
OPENAI_API_KEY="sk-..."
TWILIO_ACCOUNT_SID="AC..."
TWILIO_AUTH_TOKEN="..."
AZURE_SPEECH_KEY="..."
AZURE_SPEECH_REGION="westus2"
```

#### Operational Hours
```json
// OLD (config.json)
"operational_hours": {
  "monday": {"start": "09:00", "end": "17:00"},
  "sunday": {"closed": true}
}

// NEW (.env)
HOURS_MONDAY="09:00-17:00"
HOURS_SUNDAY="closed"
```

#### System Settings
```json
// OLD (config.json)
"system_settings": {
  "log_level": "INFO",
  "max_call_duration_minutes": 10
}

// NEW (.env)
LOG_LEVEL=INFO
MAX_CALL_DURATION_MINUTES=10
```

### 3. Update Your Code

The application now uses the new `settings.py` module:

```python
# OLD way (deprecated)
from src.config import ConfigurationManager
config_manager = ConfigurationManager()
config = config_manager.load_config()
api_key = config["api_keys"]["openai_api_key"]

# NEW way (recommended)
from src.settings import get_settings
settings = get_settings()
api_key = settings.openai_api_key.get_secret_value()
```

### 4. For Development

```bash
# Set development mode
echo "ALLOW_DEV_DEFAULTS=true" >> .env

# Add dashboard credentials
echo "DASHBOARD_USERNAME=admin" >> .env
echo "DASHBOARD_PASSWORD=admin" >> .env
```

### 5. For Production

```bash
# Ensure production settings
ALLOW_DEV_DEFAULTS=false
ENVIRONMENT=production
DEBUG=false

# Use strong passwords
DASHBOARD_PASSWORD="$(openssl rand -base64 32)"
```

## Environment-Specific Configuration

### Multiple Environments

Create environment-specific files:
- `.env.development` - Development settings
- `.env.staging` - Staging settings
- `.env.production` - Production settings

Load specific environment:
```bash
# Using dotenv
export ENV_FILE=.env.production
python src/main.py

# Or directly
cp .env.production .env
python src/main.py
```

### Docker Support

```dockerfile
# Dockerfile
FROM python:3.9
COPY . /app
WORKDIR /app

# Environment variables are injected at runtime
CMD ["python", "src/main.py"]
```

```bash
# Run with Docker
docker run --env-file .env your-image
```

## Security Best Practices

### 1. Never Commit .env Files

```bash
# .gitignore should include:
.env
.env.*
!.env.example
```

### 2. Use Secret Management

For production, consider:
- AWS Secrets Manager
- Azure Key Vault
- HashiCorp Vault
- Kubernetes Secrets

### 3. Validate Configuration

```python
from src.settings import get_settings

# On startup
settings = get_settings()
warnings = settings.validate_for_startup()

if warnings:
    for warning in warnings:
        logger.warning(warning)

if not settings.is_configured_for_production():
    logger.error("Missing required production settings!")
```

## Backward Compatibility

During transition, the `load_config()` function provides compatibility:

```python
from src.settings import load_config

# Returns config in old format from .env values
config = load_config()
```

## Deprecation Timeline

- **Current**: Both config.json and .env supported
- **Next Release**: config.json deprecated with warnings
- **Future Release**: config.json support removed

## Need Help?

If you encounter issues during migration:

1. Check `.env.example` for all available settings
2. Run validation: `python -c "from src.settings import get_settings; print(get_settings().get_sanitized_dict())"`
3. Review application logs for configuration warnings

## Quick Reference

### Essential Variables

```bash
# Minimum required for production
PRACTICE_NAME="Your Practice"
EMR_BASE_URL="https://your-emr.com"
EMR_CLIENT_ID="your-client-id"
EMR_CLIENT_SECRET="your-secret"
OPENAI_API_KEY="sk-..."
TWILIO_ACCOUNT_SID="AC..."
TWILIO_AUTH_TOKEN="..."
AZURE_SPEECH_KEY="..."
AZURE_SPEECH_REGION="westus2"
DASHBOARD_USERNAME="admin"
DASHBOARD_PASSWORD="secure-password"
```

### Development Setup

```bash
# Quick development setup
cat > .env << EOF
ALLOW_DEV_DEFAULTS=true
DEBUG=true
ENVIRONMENT=development
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=admin
EOF
```

The new configuration system is more secure, maintainable, and follows modern best practices. Make the switch today!
