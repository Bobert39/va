#!/usr/bin/env python3
"""
Development server startup script for Voice AI Platform
Provides convenient development environment with hot reload
"""

import os
import sys
import subprocess
from pathlib import Path

def check_poetry():
    """Check if Poetry is available"""
    try:
        subprocess.run(["poetry", "--version"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def check_dependencies():
    """Check if dependencies are installed"""
    try:
        result = subprocess.run(
            ["poetry", "run", "python", "-c", "import fastapi, uvicorn"],
            check=True,
            capture_output=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

def install_dependencies():
    """Install project dependencies"""
    print("Installing dependencies with Poetry...")
    try:
        subprocess.run(["poetry", "install"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        return False

def start_dev_server():
    """Start the development server with hot reload"""
    print("Starting Voice AI Platform development server...")
    print("Server will be available at: http://localhost:8000")
    print("API documentation: http://localhost:8000/docs")
    print("Dashboard: http://localhost:8000/dashboard")
    print("\nPress Ctrl+C to stop the server")

    try:
        subprocess.run([
            "poetry", "run", "uvicorn",
            "src.main:app",
            "--host", "127.0.0.1",
            "--port", "8000",
            "--reload",
            "--reload-dir", "src",
            "--reload-dir", "static"
        ], check=True)
    except KeyboardInterrupt:
        print("\n\nShutting down development server...")
    except subprocess.CalledProcessError as e:
        print(f"Error starting server: {e}")
        return False

    return True

def main():
    """Main entry point"""
    print("Voice AI Platform - Development Server")
    print("=" * 40)

    # Check if we're in the right directory
    if not Path("pyproject.toml").exists():
        print("Error: pyproject.toml not found. Please run from project root.")
        sys.exit(1)

    # Check Poetry
    if not check_poetry():
        print("Error: Poetry not found. Please install Poetry first.")
        print("Visit: https://python-poetry.org/docs/#installation")
        sys.exit(1)

    # Check dependencies
    if not check_dependencies():
        print("Dependencies not installed or outdated.")
        if not install_dependencies():
            sys.exit(1)

    # Set development environment variables
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DEBUG"] = "true"

    # Start server
    if not start_dev_server():
        sys.exit(1)

if __name__ == "__main__":
    main()