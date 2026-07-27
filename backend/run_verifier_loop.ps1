# run_verifier_loop.ps1
# This script forcefully cleans up processes and the venv before running the verifier to prevent memory leaks

Write-Host "[*] Cleaning up old Python and Chrome processes..." -ForegroundColor Cyan

# Kill lingering chrome and chromedriver processes (silently continue if none exist)
Stop-Process -Name "chrome" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "chromedriver" -Force -ErrorAction SilentlyContinue

# We cannot easily kill all pythons because this script itself might be launched by a python wrapper,
# but we can assume the old verifier is done.

Write-Host "[*] Removing old virtual environment (.venv)..." -ForegroundColor Cyan
if (Test-Path ".venv") {
    Remove-Item -Recurse -Force ".venv"
}

Write-Host "[*] Recreating virtual environment and installing dependencies using uv..." -ForegroundColor Cyan
# Ensure uv is installed or use standard python venv if uv is missing. Assuming uv is available as per the project standard.
uv venv .venv
uv pip install -r requirements.txt python-dotenv gdown

Write-Host "[*] Environment clean. Starting the course verifier..." -ForegroundColor Green
uv run python autonomous_course_verifier.py link_compile.pdf
