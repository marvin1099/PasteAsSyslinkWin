@echo off
cd /d "%~dp0"
uv sync
if %errorlevel% neq 0 (
    echo uv sync failed!
    pause
    exit /b %errorlevel%
)
uv run build.py
if %errorlevel% neq 0 (
    echo Build failed!
    pause
    exit /b %errorlevel%
)
pause
