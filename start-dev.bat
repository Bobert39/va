@echo off
REM Voice AI Platform - Development Server Startup Script for Windows
REM This script starts the development server with hot reload

echo Voice AI Platform - Development Server
echo ========================================

REM Check if Poetry is installed
poetry --version >nul 2>&1
if errorlevel 1 (
    echo Error: Poetry not found. Please install Poetry first.
    echo Visit: https://python-poetry.org/docs/#installation
    pause
    exit /b 1
)

REM Check if we're in the right directory
if not exist pyproject.toml (
    echo Error: pyproject.toml not found. Please run from project root.
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Checking dependencies...
poetry run python -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    poetry install
    if errorlevel 1 (
        echo Error installing dependencies.
        pause
        exit /b 1
    )
)

REM Set environment variables
set ENVIRONMENT=development
set DEBUG=true

REM Start the development server
echo.
echo Starting development server...
echo Server will be available at: http://localhost:8000
echo API documentation: http://localhost:8000/docs
echo Dashboard: http://localhost:8000/dashboard
echo.
echo Press Ctrl+C to stop the server
echo.

poetry run uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir src --reload-dir static

echo.
echo Development server stopped.
pause