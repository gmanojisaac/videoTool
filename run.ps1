# Quick launcher for Comic Video MCP Pipeline
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Comic Video MCP - Cinematic Video Generator" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

# Locate Python
$python = ""
if (Test-Path "$scriptDir\.venv\Scripts\python.exe") {
    $python = "$scriptDir\.venv\Scripts\python.exe"
} elseif (Test-Path "$scriptDir\..\mcp-tile-camera\.venv\Scripts\python.exe") {
    $python = "$scriptDir\..\mcp-tile-camera\.venv\Scripts\python.exe"
} else {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        $python = "python"
    }
}

if (-not $python) {
    Write-Error "Python 3.11+ not found. Please install Python or set up a virtual environment (.venv)."
    exit 1
}

Write-Host "Using Python: $python" -ForegroundColor DarkGray
Write-Host "Running comic video pipeline on comic.png..." -ForegroundColor Yellow

& $python "$scriptDir\render_modes.py" "$scriptDir\comic.png" --mode both

if ($LASTEXITCODE -eq 0) {
    Write-Host "Opening video and output directory..." -ForegroundColor Green
    Start-Process "$scriptDir\output\desktop\comic_video.mp4"
    Start-Process "$scriptDir\output\mobile\comic_video.mp4"
    Start-Process "$scriptDir\output"
} else {
    Write-Error "Video generation failed with code $LASTEXITCODE."
}
