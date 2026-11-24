@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Install the application dependencies first with INSTALL_INSIGHTS.bat.
  exit /b 1
)
.venv\Scripts\python.exe -m compileall -q patterns insights
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m unittest discover -s patterns/tests -v
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m unittest discover -s insights/tests -q
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m unittest discover -s tests -q
if errorlevel 1 exit /b 1
echo Phase 2 offline checks passed. This does not certify live data or profitability.
endlocal
