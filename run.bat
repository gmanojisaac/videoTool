@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo   Comic Video MCP - Cinematic Video Generator
echo ==============================================

:: Detect Python executable
set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else if exist "..\mcp-tile-camera\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\mcp-tile-camera\.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python was not found on PATH or in .venv.
    echo Please install Python 3.11+ or run: python -m venv .venv
    pause
    exit /b 1
)

echo Using Python: %PYTHON_EXE%
echo Running comic video pipeline on comic.png...

"%PYTHON_EXE%" -c "import sys; sys.path.insert(0, '.'); from mcp_tools import create_comic_video; res = create_comic_video(image='comic.png', output='output/comic_video.mp4'); print('\n[SUCCESS] Rendered to:', res['video_path'])"

if %errorlevel% neq 0 (
    echo [ERROR] Video generation failed.
    pause
    exit /b %errorlevel%
)

echo Opening generated video and output folder...
start "" "output\comic_video.mp4"
start "" "output"

echo Done!
