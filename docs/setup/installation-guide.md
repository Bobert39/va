# Voice AI Platform - Installation Guide

## Overview
This guide provides step-by-step instructions for installing and setting up the Voice AI Platform on Windows 10+ systems.

## System Requirements

### Hardware Requirements
- **CPU**: Intel Core i3 or AMD equivalent (minimum), Intel Core i5 or better (recommended)
- **RAM**: 8GB minimum, 16GB recommended for optimal performance
- **Storage**: 10GB available disk space for installation and logs
- **Network**: Internet connection required for cloud AI services

### Software Requirements
- **Operating System**: Windows 10 version 1903 or later, Windows 11
- **Python**: Version 3.9, 3.10, or 3.11 (Python 3.12+ not yet supported)
- **PowerShell**: Version 5.1 or later (included with Windows 10+)

### Prerequisites Validation
Run these commands to verify your system meets requirements:

```powershell
# Check Windows version
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion

# Check PowerShell version
$PSVersionTable.PSVersion

# Check available RAM
Get-WmiObject -Class Win32_ComputerSystem | Select-Object @{Name="RAM (GB)";Expression={[math]::Round($_.TotalPhysicalMemory/1GB,2)}}

# Check disk space (C: drive)
Get-WmiObject -Class Win32_LogicalDisk -Filter "DeviceID='C:'" | Select-Object @{Name="Free Space (GB)";Expression={[math]::Round($_.FreeSpace/1GB,2)}}
```

## Python 3.9+ Installation

### Option 1: Microsoft Store (Recommended for Windows 11)
1. Open Microsoft Store
2. Search for "Python 3.11"
3. Install the official Python from Python Software Foundation
4. Verify installation:
   ```powershell
   python --version
   ```

### Option 2: Python.org Installer (Recommended for Windows 10)
1. Download Python from https://www.python.org/downloads/
2. **Critical**: Choose Python 3.9, 3.10, or 3.11 (not 3.12+)
3. Run installer with these settings:
   - ✅ **Check "Add Python to PATH"**
   - ✅ **Check "Install for all users"** (if administrator)
4. Click "Install Now"
5. Verify installation:
   ```powershell
   python --version
   pip --version
   ```

### Troubleshooting Python Installation
**Problem**: `python` command not found
- **Solution**: Restart PowerShell/Command Prompt after installation
- **Alternative**: Use `py` instead of `python` command

**Problem**: Multiple Python versions installed
- **Solution**: Use `py -3.9` or `py -3.10` to specify version
- **Check versions**: `py -0` lists all installed versions

## Poetry Installation and Setup

### Install Poetry
```powershell
# Install Poetry using official installer
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
```

### Configure Poetry PATH
Add Poetry to your PATH by adding this to your PowerShell profile:

```powershell
# Check if profile exists
Test-Path $PROFILE

# Create profile if it doesn't exist
if (!(Test-Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force
}

# Add Poetry to PATH
Add-Content $PROFILE '$env:PATH += ";$env:USERPROFILE\AppData\Roaming\Python\Scripts"'

# Reload profile
. $PROFILE
```

### Verify Poetry Installation
```powershell
poetry --version
```

### Poetry Configuration (Optional but Recommended)
```powershell
# Create virtual environments in project directory
poetry config virtualenvs.in-project true

# Verify configuration
poetry config --list
```

### Troubleshooting Poetry Installation
**Problem**: `poetry` command not found after installation
- **Solution 1**: Restart PowerShell completely
- **Solution 2**: Manually add to PATH: `$env:PATH += ";$env:USERPROFILE\AppData\Roaming\Python\Scripts"`
- **Solution 3**: Use full path: `python -m poetry`

**Problem**: SSL certificate verification failed
- **Solution**: Use `--trusted-host` option:
  ```powershell
  python -m pip install --trusted-host pypi.org --trusted-host pypi.python.org poetry
  ```

## Project Setup

### Clone or Download Project
```powershell
# If using git
git clone <repository-url>
cd voice-ai-platform

# If downloaded as ZIP, extract and navigate to folder
cd path\to\voice-ai-platform
```

### Install Dependencies
```powershell
# Install all dependencies (takes 2-5 minutes)
poetry install

# Verify installation
poetry show
```

### Create Configuration File
```powershell
# Copy example configuration
copy config.example.json config.json

# Open for editing (replace with your preferred editor)
notepad config.json
```

## Dependency Installation Troubleshooting

### Common Issues and Solutions

**Problem**: `poetry install` fails with SSL errors
```powershell
# Solution: Configure Poetry to use system certificates
poetry config certificates.system-store true
```

**Problem**: Build tools missing (Microsoft Visual C++ errors)
- **Solution**: Install Microsoft Visual C++ Build Tools
  1. Download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
  2. Install "C++ build tools" workload
  3. Restart PowerShell and retry `poetry install`

**Problem**: Long paths not supported
```powershell
# Solution: Enable long path support (requires administrator)
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

**Problem**: Poetry takes too long to resolve dependencies
```powershell
# Solution: Clear Poetry cache
poetry cache clear . --all
poetry install
```

**Problem**: Permission denied errors
- **Solution**: Run PowerShell as Administrator
- **Alternative**: Install to user directory only

## Virtual Environment Best Practices

### Recommended Workflow
```powershell
# Always activate virtual environment before working
poetry shell

# Or run commands through poetry
poetry run python script.py
poetry run pytest
```

### Virtual Environment Troubleshooting
**Problem**: Virtual environment not activating
```powershell
# Manual activation (Windows)
.venv\Scripts\Activate.ps1

# If execution policy prevents activation
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Problem**: Package not found after installation
- **Solution**: Ensure you're in the virtual environment
- **Check**: `poetry env info` shows correct environment

## Next Steps

After successful installation:

1. **Configure Application**: Edit `config.json` with your settings
2. **Validate Installation**: Run system validation commands
3. **Environment Setup**: Configure development/testing/production environments
4. **First Run**: Start the application and verify functionality

See the following guides:
- [Environment-Specific Setup](environment-setup.md)
- [Configuration Reference](configuration-reference.md)
- [First-Run Validation](validation-guide.md)

## Version Compatibility Matrix

| Component | Supported Versions | Tested Versions | Notes |
|-----------|-------------------|-----------------|-------|
| Windows | 10 (1903+), 11 | 10 (21H2), 11 (22H2) | Older versions may work but unsupported |
| Python | 3.9.x, 3.10.x, 3.11.x | 3.9.18, 3.10.12, 3.11.5 | 3.12+ not yet supported |
| Poetry | 1.6.0+ | 1.6.1, 1.7.0 | Older versions may have dependency issues |
| PowerShell | 5.1+ | 5.1, 7.x | Core versions (7.x) recommended |

## Getting Help

If you encounter issues not covered in this guide:

1. **Check Common Issues**: Review [Setup Troubleshooting](troubleshooting.md)
2. **Validate Environment**: Run [validation commands](validation-guide.md)
3. **System Requirements**: Verify your system meets all requirements above
4. **Clean Installation**: Consider starting fresh with a clean Python/Poetry installation
