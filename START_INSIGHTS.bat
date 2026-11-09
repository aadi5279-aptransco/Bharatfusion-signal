@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo First run INSTALL_INSIGHTS.bat
 pause
 exit /b 1
)
start "" "http://127.0.0.1:8765"
.venv\Scripts\python.exe run_insights.py
if errorlevel 1 pause
