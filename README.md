# Voice AI Platform

Voice AI Platform for EMR Integration - A standalone application that enables voice-controlled appointment scheduling through integration with OpenEMR systems.

## 🚀 Quick Start

### For New Users
**[📖 Complete Setup Guide](docs/setup/README.md)** - Comprehensive installation and configuration (45-75 minutes)

### For Experienced Developers
**[⚡ Quick Start Guide](docs/setup/quick-start.md)** - Express setup in < 10 minutes

## 📋 System Requirements

- **Operating System**: Windows 10 version 1903+ or Windows 11
- **Python**: 3.9, 3.10, or 3.11 (3.12+ not yet supported)
- **RAM**: 8GB minimum (16GB recommended)
- **Storage**: 10GB available disk space
- **Network**: Internet connection for cloud AI services
- **Access**: Administrator privileges for installation

## 🛠️ Installation Options

### Option 1: Guided Installation (Recommended for New Users)
Follow the complete setup documentation:
1. **[Installation Guide](docs/setup/installation-guide.md)** - Step-by-step installation
2. **[Environment Setup](docs/setup/environment-setup.md)** - Environment configuration
3. **[Configuration Reference](docs/setup/configuration-reference.md)** - Configuration options
4. **[Validation Guide](docs/setup/validation-guide.md)** - System validation

### Option 2: Express Installation (Experienced Developers)
```powershell
# Verify Python 3.9-3.11
python --version

# Install Poetry
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Install dependencies
poetry install

# Create configuration
copy config.example.json config.json
# Edit config.json with your API keys

# Start development server
poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## 🔧 Development Quick Reference

### Start Development Server
```bash
poetry run uvicorn src.main:app --reload
```

### Access Application
- **API Documentation**: http://localhost:8000/docs
- **Dashboard**: http://localhost:8000/dashboard
- **Health Check**: http://localhost:8000/health

### Testing
```bash
# Run all tests with coverage
poetry run pytest --cov=src --cov-report=html

# Run unit tests only
poetry run pytest tests/unit/ -v
```

### Code Quality
```bash
# Format code
poetry run black src/ tests/

# Lint code
poetry run flake8 src/ tests/

# Type checking
poetry run mypy src/

# Security scan
poetry run bandit -r src/
```

## 📁 Project Structure
```
voice-ai-platform/
├── src/                     # Application source code
├── tests/                   # Test suites (unit, integration, e2e)
├── docs/                    # Documentation
│   ├── setup/              # Setup and installation guides
│   ├── architecture/       # System architecture documentation
│   └── qa/                 # Quality assurance documentation
├── config.json             # Configuration file (create from example)
├── pyproject.toml          # Poetry dependencies and project settings
└── README.md               # This file
```

## 🆘 Need Help?

### Common Issues
- **[Troubleshooting Guide](docs/setup/troubleshooting.md)** - Solutions to common problems
- **[Validation Guide](docs/setup/validation-guide.md)** - System testing and validation

### Documentation
- **[Complete Setup Documentation](docs/setup/README.md)** - All setup guides and references
- **[Architecture Documentation](docs/architecture/)** - System design and architecture
- **[API Documentation](http://localhost:8000/docs)** - Interactive API documentation (when running)

### Support
If you encounter issues not covered in the documentation:
1. Check the [troubleshooting guide](docs/setup/troubleshooting.md)
2. Run the [validation procedures](docs/setup/validation-guide.md)
3. Contact technical support with system information and error details

## 🏥 Production Deployment

For medical practice deployment, follow the production-focused setup path:
1. **[Installation Guide](docs/setup/installation-guide.md)** - Complete installation
2. **[Environment Setup - Production](docs/setup/environment-setup.md#production-environment)** - Security-focused configuration
3. **[Configuration Reference](docs/setup/configuration-reference.md)** - Encryption and compliance setup
4. **[Validation Guide - Level 4](docs/setup/validation-guide.md#level-4-production-readiness-validation)** - Production readiness validation

**Estimated Time**: 60-90 minutes for production-ready deployment

## 🔐 Security & Compliance

This application is designed for medical practice environments with:
- **HIPAA-aware architecture** with audit logging
- **Encryption support** for sensitive configuration data
- **Zero-administration deployment** for medical practices
- **File-based configuration** for easy management
- **Comprehensive validation procedures** for production deployment

## 📊 Architecture

This project follows a modular architecture with:
- **FastAPI** web framework for robust API development
- **Modular service architecture** for maintainability
- **File-based configuration** for zero-administration deployment
- **Comprehensive testing** with unit, integration, and e2e test suites
- **Production-ready deployment** with security and monitoring considerations

For detailed architecture information, see [Architecture Documentation](docs/architecture/README.md).
