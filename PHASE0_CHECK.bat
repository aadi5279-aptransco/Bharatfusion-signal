@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run INSTALL_INSIGHTS.bat first.
 pause
 exit /b 1
)
echo Read-only Dhan verification. Uses your local .env and sends no orders.
echo Run with --live to contact Dhan; otherwise only checks local configuration.
".venv\Scripts\python.exe" -m insights.phase0_check %*
pause
