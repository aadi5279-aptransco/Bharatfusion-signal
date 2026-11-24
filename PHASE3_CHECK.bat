@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Install application dependencies with INSTALL_INSIGHTS.bat first.
  exit /b 1
)
.venv\Scripts\python.exe -m unittest insights.tests.test_alpha_research -v
if errorlevel 1 exit /b 1
call PHASE2_CHECK.bat
if errorlevel 1 exit /b 1
echo Phase 3A offline foundation checks passed. No AI model is trained or certified.
endlocal
