# Voice AI Platform

Voice AI Platform for EMR Integration - A standalone application that enables voice-controlled appointment scheduling through integration with OpenEMR systems.

## Prerequisites

- Python 3.9+
- Windows 10+ (target deployment platform)
- 8GB RAM minimum
- Internet connection for cloud AI services

## Development Setup

1. Install Poetry (if not already installed):
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Run the development server:
   ```bash
   poetry run uvicorn src.main:app --reload
   ```

4. Access the application:
   - API Documentation: http://localhost:8000/docs
   - Dashboard: http://localhost:8000/dashboard

## Testing

Run tests with coverage:
```bash
poetry run pytest
```

## Code Quality

Format code:
```bash
poetry run black src/ tests/
```

Lint code:
```bash
poetry run flake8 src/ tests/
```

## Configuration

Copy `config.example.json` to `config.json` and configure for your environment.

## Architecture

This project follows a modular architecture with file-based configuration and zero-administration overhead for deployment to medical practices.