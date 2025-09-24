# Setup Troubleshooting Guide

## Overview
This guide provides solutions to common installation, configuration, and setup issues encountered when deploying the Voice AI Platform.

## Issue Categories

### 🐍 Python & Poetry Issues
### 🔧 Configuration Problems
### 🌐 Network & API Connectivity
### 💾 File System & Permissions
### 🚀 Application Startup Issues
### 📊 Performance Problems

---

## 🐍 Python & Poetry Issues

### Poetry Installation Failures

#### Issue: Poetry installer fails with SSL/TLS errors
```
SSL: CERTIFICATE_VERIFY_FAILED
```

**Solution 1**: Use trusted hosts
```powershell
python -m pip install --trusted-host pypi.org --trusted-host pypi.python.org poetry
```

**Solution 2**: Configure corporate proxy (if behind firewall)
```powershell
$env:HTTP_PROXY = "http://proxy.company.com:8080"
$env:HTTPS_PROXY = "http://proxy.company.com:8080"
python -m pip install poetry
```

**Solution 3**: Download and install manually
1. Download poetry installer from https://install.python-poetry.org/
2. Save as `install-poetry.py`
3. Run: `python install-poetry.py`

#### Issue: `poetry` command not found after installation
```
'poetry' is not recognized as an internal or external command
```

**Solution 1**: Add Poetry to PATH permanently
```powershell
# Add to PowerShell profile
$profilePath = $PROFILE
if (!(Test-Path $profilePath)) {
    New-Item -ItemType File -Path $profilePath -Force
}
Add-Content $profilePath '$env:PATH += ";$env:USERPROFILE\AppData\Roaming\Python\Scripts"'

# Reload profile
. $PROFILE
```

**Solution 2**: Use full path temporarily
```powershell
$env:USERPROFILE\AppData\Roaming\Python\Scripts\poetry.exe --version
```

**Solution 3**: Create alias
```powershell
Set-Alias poetry "$env:USERPROFILE\AppData\Roaming\Python\Scripts\poetry.exe"
```

### Python Version Issues

#### Issue: Wrong Python version installed
```
ERROR: This package requires Python >=3.9,<4.0
```

**Solution**: Install correct Python version
```powershell
# Check current version
python --version

# If multiple Python versions, use specific version
py -3.9 --version
py -3.10 --version

# Use specific version with Poetry
poetry env use python3.9
# or
poetry env use C:\Python39\python.exe
```

#### Issue: Multiple Python versions causing conflicts
```
ERROR: No matching distribution found
```

**Solution**: Create clean virtual environment
```powershell
# List available Python versions
py -0

# Remove existing virtual environment
poetry env remove python

# Create new environment with specific Python version
poetry env use py -3.10

# Verify environment
poetry env info
```

### Dependency Installation Issues

#### Issue: `poetry install` fails with build errors
```
Microsoft Visual C++ 14.0 is required
```

**Solution**: Install Microsoft Visual C++ Build Tools
1. Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Install "C++ build tools" workload
3. Restart PowerShell
4. Retry: `poetry install`

**Alternative**: Use pre-compiled packages
```powershell
poetry add --group dev wheel setuptools
poetry install
```

#### Issue: Long path errors on Windows
```
OSError: [Errno 2] No such file or directory: 'very\long\path\...'
```

**Solution**: Enable long path support (requires Administrator)
```powershell
# Run as Administrator
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force

# Restart system for changes to take effect
```

#### Issue: Poetry hangs on "Resolving dependencies"
```
Resolving dependencies... (This may take a few minutes)
```

**Solution 1**: Clear Poetry cache
```powershell
poetry cache clear . --all
poetry install
```

**Solution 2**: Disable parallel installer
```powershell
poetry config installer.parallel false
poetry install
```

**Solution 3**: Increase timeout
```powershell
poetry config installer.max-workers 1
poetry install --timeout 300
```

---

## 🔧 Configuration Problems

### Configuration File Issues

#### Issue: Configuration file not found
```
FileNotFoundError: [Errno 2] No such file or directory: 'config.json'
```

**Solution 1**: Verify file exists and location
```powershell
# Check current directory
pwd
ls config.json

# Use absolute path
$env:VOICE_AI_CONFIG = "C:\full\path\to\config.json"
```

**Solution 2**: Create from example
```powershell
# Copy example configuration
copy config.example.json config.json

# Edit with your settings
notepad config.json
```

#### Issue: JSON syntax errors in configuration
```
JSONDecodeError: Expecting ',' delimiter
```

**Solution**: Validate JSON syntax
```powershell
# Test JSON validity
poetry run python -m json.tool config.json

# Common fixes:
# - Add missing commas between fields
# - Escape backslashes in paths: "C:\\path\\to\\file"
# - Use double quotes, not single quotes
```

**Valid JSON example**:
```json
{
  "practice_name": "Valid Practice Name",
  "emr_credentials": {
    "base_url": "https://example.com",
    "client_id": "valid_id"
  }
}
```

### Encryption Issues

#### Issue: Cannot decrypt encrypted values
```
CryptoError: Failed to decrypt configuration value
```

**Solution 1**: Set encryption key
```powershell
$env:VOICE_AI_ENCRYPTION_KEY = "your-32-character-encryption-key"
```

**Solution 2**: Re-encrypt values
```powershell
# Re-encrypt all sensitive values
poetry run python scripts/encrypt_config.py --reencrypt

# Or encrypt specific field
poetry run python scripts/encrypt_config.py --field "api_keys.openai_api_key" --value "sk-your-key"
```

**Solution 3**: Use unencrypted values for testing
```json
{
  "api_keys": {
    "openai_api_key": "sk-your-actual-key-here"
  }
}
```

#### Issue: Encryption key too short
```
ValueError: Encryption key must be 32 characters
```

**Solution**: Generate proper encryption key
```powershell
# Generate 32-character key
$key = [System.Web.Security.Membership]::GeneratePassword(32, 0)
Write-Host "Generated key: $key"
$env:VOICE_AI_ENCRYPTION_KEY = $key
```

---

## 🌐 Network & API Connectivity

### API Authentication Issues

#### Issue: OpenAI API authentication failed
```
AuthenticationError: Invalid API key
```

**Solution 1**: Verify API key format
```powershell
# Check key format (should start with sk-)
echo $config.api_keys.openai_api_key

# Test key directly
curl -H "Authorization: Bearer sk-your-key" https://api.openai.com/v1/models
```

**Solution 2**: Check account status
1. Visit https://platform.openai.com/account/api-keys
2. Verify key is active and not revoked
3. Check usage limits and billing status

#### Issue: Twilio API authentication failed
```
TwilioRestException: HTTP 401 error: Unable to create record
```

**Solution**: Verify Twilio credentials
```powershell
# Check Account SID format (should start with AC)
echo "Account SID: AC..."

# Test credentials
curl -X GET "https://api.twilio.com/2010-04-01/Accounts.json" \
  -u "your_account_sid:your_auth_token"
```

#### Issue: Azure Speech Service authentication failed
```
ClientAuthenticationError: Invalid subscription key
```

**Solution**: Verify Azure configuration
```powershell
# Check subscription key and region
$region = "eastus"  # Your region
$key = "your-key"   # Your subscription key

# Test connection
curl -X POST "https://$region.api.cognitive.microsoft.com/sts/v1.0/issueToken" \
  -H "Ocp-Apim-Subscription-Key: $key"
```

### Network Connectivity Issues

#### Issue: Connection timeouts to external APIs
```
ConnectTimeout: HTTPSConnectionPool(...): Read timed out
```

**Solution 1**: Check internet connectivity
```powershell
# Test basic connectivity
ping google.com
nslookup api.openai.com

# Test HTTPS connectivity
curl -I https://api.openai.com/v1/models
```

**Solution 2**: Configure proxy settings (corporate networks)
```powershell
# Set proxy environment variables
$env:HTTP_PROXY = "http://proxy.company.com:8080"
$env:HTTPS_PROXY = "http://proxy.company.com:8080"
$env:NO_PROXY = "localhost,127.0.0.1"

# Test with proxy
curl --proxy "http://proxy.company.com:8080" https://api.openai.com/v1/models
```

**Solution 3**: Increase timeout values
```json
{
  "system_settings": {
    "api_timeout_seconds": 30,
    "connection_retries": 3
  }
}
```

#### Issue: Port already in use
```
OSError: [WinError 10048] Only one usage of each socket address is normally permitted
```

**Solution 1**: Find and kill process using port
```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID with actual process ID)
taskkill /PID 1234 /F
```

**Solution 2**: Use different port
```powershell
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8001
```

**Solution 3**: Wait for port to be released
```powershell
# Windows may hold the port for a few minutes after application closes
# Wait 2-5 minutes and retry
```

---

## 💾 File System & Permissions

### File Permission Issues

#### Issue: Permission denied accessing configuration files
```
PermissionError: [Errno 13] Permission denied: 'config.json'
```

**Solution 1**: Run as Administrator
```powershell
# Right-click PowerShell and "Run as administrator"
# Then retry your commands
```

**Solution 2**: Change file permissions
```powershell
# Give current user full control
icacls config.json /grant "%USERNAME%:F"

# Or reset permissions to default
icacls config.json /reset
```

**Solution 3**: Move to user directory
```powershell
# Move config to user's home directory
move config.json $env:USERPROFILE\config.json
$env:VOICE_AI_CONFIG = "$env:USERPROFILE\config.json"
```

#### Issue: Cannot create log files
```
PermissionError: [Errno 13] Permission denied: 'logs/audit.log'
```

**Solution 1**: Create logs directory with proper permissions
```powershell
mkdir logs
icacls logs /grant "%USERNAME%:F"
```

**Solution 2**: Use alternative log location
```json
{
  "system_settings": {
    "log_directory": "C:\\Users\\%USERNAME%\\AppData\\Local\\VoiceAI\\logs"
  }
}
```

### Disk Space Issues

#### Issue: Not enough disk space for installation
```
OSError: [Errno 28] No space left on device
```

**Solution**: Check and free up disk space
```powershell
# Check disk space
Get-WmiObject -Class Win32_LogicalDisk | Select-Object DeviceID, @{Name="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}}, @{Name="Free(GB)";Expression={[math]::Round($_.FreeSpace/1GB,2)}}

# Clean Poetry cache
poetry cache clear . --all

# Clean pip cache
python -m pip cache purge

# Clean temporary files
Remove-Item $env:TEMP\* -Recurse -Force -ErrorAction SilentlyContinue
```

---

## 🚀 Application Startup Issues

### Import Errors

#### Issue: Module not found errors
```
ModuleNotFoundError: No module named 'src'
```

**Solution 1**: Set PYTHONPATH
```powershell
$env:PYTHONPATH = "src"
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**Solution 2**: Run from project root directory
```powershell
# Ensure you're in the project root
pwd
ls src/  # Should show source files

# Run from correct location
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

#### Issue: FastAPI application not starting
```
ImportError: cannot import name 'app' from 'src.main'
```

**Solution**: Verify main application file exists
```powershell
# Check main.py exists and has app object
ls src/main.py
Get-Content src/main.py | Select-String "app ="
```

### Database Connection Issues

#### Issue: Database connection failed
```
OperationalError: could not connect to database
```

**Solution 1**: Check database configuration
```json
{
  "database": {
    "url": "sqlite:///./voice_ai.db",
    "echo": false
  }
}
```

**Solution 2**: Initialize database
```powershell
# Create database tables
poetry run python scripts/init_database.py

# Or use alembic if configured
poetry run alembic upgrade head
```

### Configuration Loading Issues

#### Issue: Configuration validation failed
```
ValidationError: practice_name is required
```

**Solution**: Check required fields in config.json
```json
{
  "practice_name": "Required - Your Practice Name",
  "emr_credentials": {
    "base_url": "Required - https://your-emr.com",
    "client_id": "Required - your_client_id",
    "client_secret": "Required - your_client_secret",
    "redirect_uri": "Required - callback URL"
  },
  "api_keys": {
    "openai_api_key": "Required - sk-your-key",
    "twilio_account_sid": "Required - AC...",
    "twilio_auth_token": "Required - auth_token",
    "azure_speech_key": "Required - subscription_key",
    "azure_speech_region": "Required - eastus"
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

---

## 📊 Performance Problems

### High Memory Usage

#### Issue: Application consumes excessive memory
```
MemoryError: Unable to allocate memory
```

**Solution 1**: Check for memory leaks
```powershell
# Monitor memory usage
Get-Process | Where-Object {$_.ProcessName -like "*python*"} | Select-Object ProcessName, WS

# Restart application periodically
```

**Solution 2**: Optimize configuration
```json
{
  "system_settings": {
    "max_concurrent_calls": 5,
    "log_level": "WARNING",
    "enable_debug": false
  }
}
```

### Slow Response Times

#### Issue: API endpoints respond slowly (>5 seconds)
```
RequestTimeout: Request timed out
```

**Solution 1**: Check external API response times
```powershell
# Test OpenAI API directly
Measure-Command {
  curl -H "Authorization: Bearer sk-your-key" https://api.openai.com/v1/models
}
```

**Solution 2**: Optimize logging level
```json
{
  "system_settings": {
    "log_level": "WARNING"
  }
}
```

**Solution 3**: Enable caching (if available)
```json
{
  "system_settings": {
    "enable_caching": true,
    "cache_ttl_seconds": 300
  }
}
```

---

## 🔧 Quick Fix Scripts

### Automated Troubleshooting Script

Create a comprehensive troubleshooting script:

```powershell
# Save as troubleshoot.ps1
@"
Write-Host "Voice AI Platform Troubleshooting Script" -ForegroundColor Green

# Check Python
Write-Host "`n1. Checking Python installation..." -ForegroundColor Yellow
try {
    `$pythonVersion = python --version 2>&1
    Write-Host "✅ Python: `$pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found or not in PATH" -ForegroundColor Red
}

# Check Poetry
Write-Host "`n2. Checking Poetry installation..." -ForegroundColor Yellow
try {
    `$poetryVersion = poetry --version 2>&1
    Write-Host "✅ Poetry: `$poetryVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Poetry not found or not in PATH" -ForegroundColor Red
    Write-Host "   Try: `$env:PATH += ';`$env:USERPROFILE\AppData\Roaming\Python\Scripts'" -ForegroundColor Yellow
}

# Check virtual environment
Write-Host "`n3. Checking virtual environment..." -ForegroundColor Yellow
try {
    poetry env info
    Write-Host "✅ Virtual environment configured" -ForegroundColor Green
} catch {
    Write-Host "❌ Virtual environment issue" -ForegroundColor Red
    Write-Host "   Try: poetry install" -ForegroundColor Yellow
}

# Check configuration
Write-Host "`n4. Checking configuration file..." -ForegroundColor Yellow
if (Test-Path "config.json") {
    Write-Host "✅ config.json found" -ForegroundColor Green
    try {
        python -m json.tool config.json > `$null
        Write-Host "✅ config.json is valid JSON" -ForegroundColor Green
    } catch {
        Write-Host "❌ config.json has syntax errors" -ForegroundColor Red
        Write-Host "   Try: python -m json.tool config.json" -ForegroundColor Yellow
    }
} else {
    Write-Host "❌ config.json not found" -ForegroundColor Red
    Write-Host "   Try: copy config.example.json config.json" -ForegroundColor Yellow
}

# Check port availability
Write-Host "`n5. Checking port availability..." -ForegroundColor Yellow
`$portCheck = netstat -an | Select-String ":8000"
if (`$portCheck) {
    Write-Host "⚠️  Port 8000 is in use" -ForegroundColor Yellow
    Write-Host "   Process using port: `$portCheck" -ForegroundColor Yellow
} else {
    Write-Host "✅ Port 8000 is available" -ForegroundColor Green
}

Write-Host "`nTroubleshooting complete!" -ForegroundColor Green
"@ | Out-File -FilePath "troubleshoot.ps1"

# Run the script
.\troubleshoot.ps1
```

### Environment Reset Script

For clean slate troubleshooting:

```powershell
# Save as reset_environment.ps1
@"
Write-Host "Resetting Voice AI Platform Environment" -ForegroundColor Green

# Remove virtual environment
Write-Host "Removing virtual environment..." -ForegroundColor Yellow
poetry env remove --all

# Clear caches
Write-Host "Clearing caches..." -ForegroundColor Yellow
poetry cache clear . --all
python -m pip cache purge

# Reinstall dependencies
Write-Host "Reinstalling dependencies..." -ForegroundColor Yellow
poetry install

# Verify installation
Write-Host "Verifying installation..." -ForegroundColor Yellow
poetry run python -c "import src.main; print('✅ Import successful')"

Write-Host "Environment reset complete!" -ForegroundColor Green
"@ | Out-File -FilePath "reset_environment.ps1"
```

---

## Getting Additional Help

### When to Contact Support

Contact technical support if you experience:
- Issues not covered in this troubleshooting guide
- Persistent authentication failures after following solutions
- Performance problems that don't improve with optimization
- Critical security concerns or audit failures

### Information to Gather Before Contacting Support

1. **System Information**:
   ```powershell
   # Gather system info
   systeminfo | findstr /B /C:"OS Name" /C:"OS Version" /C:"System Type"
   python --version
   poetry --version
   ```

2. **Error Messages**: Copy exact error messages and stack traces

3. **Configuration**: Sanitized configuration file (remove sensitive data)

4. **Log Files**: Recent application and error logs

5. **Network Environment**: Corporate proxy/firewall information if applicable

### Self-Help Resources

- **Documentation**: Check all setup guides thoroughly
- **GitHub Issues**: Search for similar issues in project repository
- **Community Forums**: Check community discussions and solutions
- **Validation Guide**: Run full validation to identify specific failures

---

## Related Documentation

- [Installation Guide](installation-guide.md) - Initial setup instructions
- [Configuration Reference](configuration-reference.md) - Configuration details
- [Validation Guide](validation-guide.md) - System validation procedures
- [Environment Setup](environment-setup.md) - Environment-specific configuration
