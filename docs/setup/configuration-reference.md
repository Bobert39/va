# Configuration Reference Guide

## Overview
Complete reference for configuring the Voice AI Platform, including all configuration fields, validation rules, and practical examples.

## Configuration File Structure

The Voice AI Platform uses a JSON configuration file (`config.json`) with the following top-level sections:

```json
{
  "practice_name": "Your Practice Name",
  "emr_credentials": {
    "base_url": "https://your-emr.com",
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "redirect_uri": "http://localhost:8000/auth/callback"
  },
  "api_keys": {
    "openai_api_key": "sk-your-api-key",
    "twilio_account_sid": "AC...",
    "twilio_auth_token": "your_auth_token",
    "azure_speech_key": "your_azure_key",
    "azure_speech_region": "eastus"
  },
  "operational_hours": {
    "monday": {"start": "09:00", "end": "17:00"}
  },
  "system_settings": {
    "log_level": "INFO",
    "max_call_duration_minutes": 10,
    "enable_audit_logging": true,
    "audit_log_rotation_mb": 10
  }
}
```

## Practice Information

### practice_name
**Type**: String
**Required**: Yes
**Description**: Display name for your medical practice
**Validation**: 1-100 characters, no special characters except spaces, hyphens, and apostrophes

**Examples**:
```json
{
  "practice_name": "Riverside Family Medicine"
}
```

```json
{
  "practice_name": "Dr. Smith's Pediatric Clinic"
}
```

**Common Issues**:
- Avoid special characters like `&`, `@`, `#`
- Keep under 100 characters for display purposes
- Use official practice name for compliance

## EMR Credentials

### emr_credentials
**Type**: Object
**Required**: Yes
**Description**: OAuth2 credentials for EMR system integration

#### emr_credentials.base_url
**Type**: String (URL)
**Required**: Yes
**Description**: Base URL of your EMR system
**Validation**: Must be valid HTTPS URL (HTTP allowed for development)

**Examples**:
```json
{
  "emr_credentials": {
    "base_url": "https://your-practice.openemr.com"
  }
}
```

```json
{
  "emr_credentials": {
    "base_url": "https://emr.medicalpractice.local:8443"
  }
}
```

#### emr_credentials.client_id
**Type**: String
**Required**: Yes
**Description**: OAuth2 client ID from your EMR system
**Validation**: 1-255 characters, alphanumeric plus hyphens and underscores
**Security**: Can be encrypted using system encryption key

**Example**:
```json
{
  "emr_credentials": {
    "client_id": "voice-ai-client-2023"
  }
}
```

#### emr_credentials.client_secret
**Type**: String
**Required**: Yes
**Description**: OAuth2 client secret from your EMR system
**Validation**: 1-255 characters
**Security**: Should always be encrypted in production

**Example**:
```json
{
  "emr_credentials": {
    "client_secret": "ENCRYPTED:AES256:abc123def456..."
  }
}
```

#### emr_credentials.redirect_uri
**Type**: String (URL)
**Required**: Yes
**Description**: OAuth2 callback URL for authentication flow
**Validation**: Must match registered redirect URI in EMR system

**Examples**:
```json
{
  "emr_credentials": {
    "redirect_uri": "http://localhost:8000/auth/callback"
  }
}
```

```json
{
  "emr_credentials": {
    "redirect_uri": "https://voice-ai.yourpractice.com/auth/callback"
  }
}
```

**Complete EMR Credentials Example**:
```json
{
  "emr_credentials": {
    "base_url": "https://your-practice.openemr.com",
    "client_id": "voice-ai-client-2023",
    "client_secret": "ENCRYPTED:AES256:abc123def456...",
    "redirect_uri": "https://voice-ai.yourpractice.com/auth/callback"
  }
}
```

## API Keys

### api_keys
**Type**: Object
**Required**: Yes
**Description**: External service API credentials

#### api_keys.openai_api_key
**Type**: String
**Required**: Yes
**Description**: OpenAI API key for natural language processing
**Validation**: Must start with `sk-` followed by alphanumeric characters
**Security**: Should be encrypted in production

**Example**:
```json
{
  "api_keys": {
    "openai_api_key": "sk-proj-abc123def456ghi789..."
  }
}
```

#### api_keys.twilio_account_sid
**Type**: String
**Required**: Yes
**Description**: Twilio Account SID for voice communication
**Validation**: Must start with `AC` followed by 32 hexadecimal characters
**Security**: Can be encrypted but not strictly required

**Example**:
```json
{
  "api_keys": {
    "twilio_account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

#### api_keys.twilio_auth_token
**Type**: String
**Required**: Yes
**Description**: Twilio Auth Token for API authentication
**Validation**: 32 character hexadecimal string
**Security**: Should be encrypted in production

**Example**:
```json
{
  "api_keys": {
    "twilio_auth_token": "ENCRYPTED:AES256:def456ghi789..."
  }
}
```

#### api_keys.azure_speech_key
**Type**: String
**Required**: Yes
**Description**: Azure Speech Service subscription key
**Validation**: 32 character hexadecimal string
**Security**: Should be encrypted in production

**Example**:
```json
{
  "api_keys": {
    "azure_speech_key": "ENCRYPTED:AES256:ghi789jkl012..."
  }
}
```

#### api_keys.azure_speech_region
**Type**: String
**Required**: Yes
**Description**: Azure Speech Service region
**Validation**: Must be valid Azure region code

**Valid Regions**:
- `eastus`, `westus`, `westus2`
- `centralus`, `southcentralus`
- `northeurope`, `westeurope`
- `japaneast`, `southeastasia`

**Example**:
```json
{
  "api_keys": {
    "azure_speech_region": "eastus"
  }
}
```

**Complete API Keys Example**:
```json
{
  "api_keys": {
    "openai_api_key": "ENCRYPTED:AES256:abc123...",
    "twilio_account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "twilio_auth_token": "ENCRYPTED:AES256:def456...",
    "azure_speech_key": "ENCRYPTED:AES256:ghi789...",
    "azure_speech_region": "eastus"
  }
}
```

## Operational Hours

### operational_hours
**Type**: Object
**Required**: Yes
**Description**: Practice operating hours for each day of the week

Each day can have:
- **Business hours**: `{"start": "HH:MM", "end": "HH:MM"}`
- **Closed**: `{"closed": true}`
- **24 hours**: `{"start": "00:00", "end": "23:59"}`

**Time Format**: 24-hour format (HH:MM)
**Validation**: Start time must be before end time

#### Standard Business Hours Example
```json
{
  "operational_hours": {
    "monday": {"start": "09:00", "end": "17:00"},
    "tuesday": {"start": "09:00", "end": "17:00"},
    "wednesday": {"start": "09:00", "end": "17:00"},
    "thursday": {"start": "09:00", "end": "17:00"},
    "friday": {"start": "09:00", "end": "17:00"},
    "saturday": {"start": "09:00", "end": "13:00"},
    "sunday": {"closed": true}
  }
}
```

#### Extended Hours Example
```json
{
  "operational_hours": {
    "monday": {"start": "07:00", "end": "19:00"},
    "tuesday": {"start": "07:00", "end": "19:00"},
    "wednesday": {"start": "07:00", "end": "19:00"},
    "thursday": {"start": "07:00", "end": "19:00"},
    "friday": {"start": "07:00", "end": "19:00"},
    "saturday": {"start": "08:00", "end": "16:00"},
    "sunday": {"start": "10:00", "end": "14:00"}
  }
}
```

#### Split Hours Example
```json
{
  "operational_hours": {
    "monday": {"start": "08:00", "end": "12:00"},
    "monday_afternoon": {"start": "13:00", "end": "17:00"}
  }
}
```

**Note**: Split hours require custom configuration - contact support for setup.

## System Settings

### system_settings
**Type**: Object
**Required**: Yes
**Description**: Application behavior and system configuration

#### system_settings.log_level
**Type**: String (Enum)
**Required**: Yes
**Description**: Logging verbosity level
**Valid Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

**Recommendations**:
- **Development**: `DEBUG` for detailed troubleshooting
- **Testing**: `INFO` for moderate detail
- **Production**: `WARNING` or `ERROR` for minimal logging

**Example**:
```json
{
  "system_settings": {
    "log_level": "INFO"
  }
}
```

#### system_settings.max_call_duration_minutes
**Type**: Integer
**Required**: Yes
**Description**: Maximum duration for voice calls in minutes
**Validation**: 1-30 minutes (recommended: 5-15)

**Example**:
```json
{
  "system_settings": {
    "max_call_duration_minutes": 10
  }
}
```

#### system_settings.enable_audit_logging
**Type**: Boolean
**Required**: Yes
**Description**: Enable comprehensive audit logging for compliance
**Recommendation**: Always `true` for medical practices

**Example**:
```json
{
  "system_settings": {
    "enable_audit_logging": true
  }
}
```

#### system_settings.audit_log_rotation_mb
**Type**: Integer
**Required**: Yes (if audit logging enabled)
**Description**: Audit log file size before rotation in MB
**Validation**: 1-100 MB (recommended: 10-25)

**Example**:
```json
{
  "system_settings": {
    "audit_log_rotation_mb": 15
  }
}
```

#### Optional System Settings

#### system_settings.enable_monitoring
**Type**: Boolean
**Required**: No
**Default**: `false`
**Description**: Enable application performance monitoring

#### system_settings.monitoring_endpoint
**Type**: String (URL)
**Required**: No (if monitoring enabled)
**Description**: External monitoring service endpoint

#### system_settings.session_timeout_minutes
**Type**: Integer
**Required**: No
**Default**: `60`
**Description**: User session timeout in minutes

#### system_settings.max_concurrent_calls
**Type**: Integer
**Required**: No
**Default**: `10`
**Description**: Maximum simultaneous voice calls

**Complete System Settings Example**:
```json
{
  "system_settings": {
    "log_level": "INFO",
    "max_call_duration_minutes": 8,
    "enable_audit_logging": true,
    "audit_log_rotation_mb": 20,
    "enable_monitoring": true,
    "session_timeout_minutes": 30,
    "max_concurrent_calls": 5
  }
}
```

## Encryption and Key Management

### Encrypted Fields
The following fields should be encrypted in production:
- `emr_credentials.client_secret`
- `api_keys.openai_api_key`
- `api_keys.twilio_auth_token`
- `api_keys.azure_speech_key`

### Encryption Format
```
ENCRYPTED:AES256:base64-encoded-encrypted-data
```

### Setting Up Encryption

#### 1. Generate Encryption Key
```powershell
# Generate 32-character encryption key
$key = [System.Web.Security.Membership]::GeneratePassword(32, 0)
$env:VOICE_AI_ENCRYPTION_KEY = $key
```

#### 2. Encrypt Sensitive Values
```powershell
# Using built-in encryption utility
poetry run python scripts/encrypt_config.py --field "api_keys.openai_api_key" --value "sk-your-api-key"
```

#### 3. Environment Variable
Set encryption key as environment variable:
```powershell
$env:VOICE_AI_ENCRYPTION_KEY = "your-32-character-encryption-key"
```

## Environment Variable Overrides

### Supported Environment Variables
Configuration values can be overridden using environment variables:

| Environment Variable | Configuration Path | Example |
|---------------------|-------------------|---------|
| `VOICE_AI_PRACTICE_NAME` | `practice_name` | `"Main Street Clinic"` |
| `VOICE_AI_EMR_BASE_URL` | `emr_credentials.base_url` | `"https://emr.clinic.com"` |
| `VOICE_AI_OPENAI_KEY` | `api_keys.openai_api_key` | `"sk-..."` |
| `VOICE_AI_LOG_LEVEL` | `system_settings.log_level` | `"DEBUG"` |

### Setting Environment Variables
```powershell
# Override log level for debugging
$env:VOICE_AI_LOG_LEVEL = "DEBUG"

# Override practice name
$env:VOICE_AI_PRACTICE_NAME = "Emergency Clinic Mode"
```

## Practice-Specific Configuration Examples

### Small Family Practice
```json
{
  "practice_name": "Riverside Family Medicine",
  "emr_credentials": {
    "base_url": "https://riverside.openemr.com",
    "client_id": "riverside-voice-ai",
    "client_secret": "ENCRYPTED:AES256:...",
    "redirect_uri": "http://localhost:8000/auth/callback"
  },
  "api_keys": {
    "openai_api_key": "ENCRYPTED:AES256:...",
    "twilio_account_sid": "AC...",
    "twilio_auth_token": "ENCRYPTED:AES256:...",
    "azure_speech_key": "ENCRYPTED:AES256:...",
    "azure_speech_region": "eastus"
  },
  "operational_hours": {
    "monday": {"start": "08:00", "end": "17:00"},
    "tuesday": {"start": "08:00", "end": "17:00"},
    "wednesday": {"start": "08:00", "end": "17:00"},
    "thursday": {"start": "08:00", "end": "17:00"},
    "friday": {"start": "08:00", "end": "17:00"},
    "saturday": {"closed": true},
    "sunday": {"closed": true}
  },
  "system_settings": {
    "log_level": "INFO",
    "max_call_duration_minutes": 8,
    "enable_audit_logging": true,
    "audit_log_rotation_mb": 15
  }
}
```

### Large Multi-Specialty Clinic
```json
{
  "practice_name": "Metropolitan Medical Center",
  "emr_credentials": {
    "base_url": "https://mmc.epic.com",
    "client_id": "mmc-voice-ai-prod",
    "client_secret": "ENCRYPTED:AES256:...",
    "redirect_uri": "https://voice.metropolitanmedical.com/auth/callback"
  },
  "api_keys": {
    "openai_api_key": "ENCRYPTED:AES256:...",
    "twilio_account_sid": "AC...",
    "twilio_auth_token": "ENCRYPTED:AES256:...",
    "azure_speech_key": "ENCRYPTED:AES256:...",
    "azure_speech_region": "westus2"
  },
  "operational_hours": {
    "monday": {"start": "06:00", "end": "22:00"},
    "tuesday": {"start": "06:00", "end": "22:00"},
    "wednesday": {"start": "06:00", "end": "22:00"},
    "thursday": {"start": "06:00", "end": "22:00"},
    "friday": {"start": "06:00", "end": "22:00"},
    "saturday": {"start": "07:00", "end": "20:00"},
    "sunday": {"start": "08:00", "end": "18:00"}
  },
  "system_settings": {
    "log_level": "WARNING",
    "max_call_duration_minutes": 12,
    "enable_audit_logging": true,
    "audit_log_rotation_mb": 50,
    "enable_monitoring": true,
    "max_concurrent_calls": 25,
    "session_timeout_minutes": 20
  }
}
```

## Configuration Validation

### Built-in Validation
The application validates configuration on startup:

```powershell
# Validate configuration without starting server
poetry run python -c "from src.config import validate_config; validate_config('config.json')"
```

### Common Validation Errors

**Invalid URL Format**:
```
Error: emr_credentials.base_url must be a valid URL
Fix: Ensure URL includes protocol (https://) and valid domain
```

**Missing Required Field**:
```
Error: practice_name is required
Fix: Add practice_name field to configuration
```

**Invalid Time Format**:
```
Error: operational_hours.monday.start must be in HH:MM format
Fix: Use 24-hour format like "09:00"
```

**Encryption Key Missing**:
```
Error: Cannot decrypt encrypted fields - encryption key not set
Fix: Set VOICE_AI_ENCRYPTION_KEY environment variable
```

## Configuration Testing

### Test Configuration
```powershell
# Test configuration loading
poetry run python -c "from src.config import get_config; print('Config loaded successfully')"

# Test EMR connectivity
poetry run python scripts/test_emr_connection.py

# Test API keys
poetry run python scripts/test_api_keys.py
```

### Configuration Backup
```powershell
# Backup configuration (excluding secrets)
poetry run python scripts/backup_config.py

# Restore from backup
poetry run python scripts/restore_config.py backup-20231201.json
```

## Troubleshooting Configuration Issues

### Common Problems

**Problem**: Configuration file not found
```powershell
# Solution: Verify file exists and path is correct
ls config.json
$env:VOICE_AI_CONFIG = "C:\full\path\to\config.json"
```

**Problem**: Encrypted values not decrypting
```powershell
# Solution: Check encryption key is set
echo $env:VOICE_AI_ENCRYPTION_KEY
# Re-encrypt values if key changed
poetry run python scripts/encrypt_config.py --reencrypt
```

**Problem**: EMR authentication failing
- **Check**: EMR credentials are correct
- **Verify**: Redirect URI matches exactly
- **Test**: EMR system is accessible from your network

**Problem**: API calls failing
- **Check**: API keys are valid and active
- **Verify**: Account has sufficient credits/quota
- **Test**: Network allows outbound HTTPS connections

## Security Best Practices

### Configuration Security
1. **Encrypt all sensitive values** in production
2. **Restrict file permissions** on config.json
3. **Use environment variables** for deployment-specific values
4. **Regular rotation** of API keys and secrets
5. **Audit access** to configuration files

### File Permissions
```powershell
# Restrict access to config file (requires administrator)
icacls config.json /grant:r "SYSTEM:F" /grant:r "Administrators:F" /inheritance:r
```

### Version Control
- **Never commit** config.json with real credentials
- **Use config.example.json** for templates
- **Add config.json** to .gitignore

## Next Steps

After configuring:
1. **Validate Configuration**: Run validation scripts
2. **Test Connectivity**: Verify EMR and API connections
3. **First Run**: Start application and verify functionality
4. **Monitor Logs**: Check for configuration-related warnings

Related Guides:
- [Installation Guide](installation-guide.md)
- [Environment Setup](environment-setup.md)
- [Validation Procedures](validation-guide.md)
- [Troubleshooting Guide](troubleshooting.md)
