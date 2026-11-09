@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Existing installation not found in this folder. Run INSTALL.bat for a new installation.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 (
 echo Tests failed. Send a screenshot of this output before starting the app.
 pause
 exit /b 1
)
echo Update checks passed. Open START.bat to launch version 0.7.1.
pause
