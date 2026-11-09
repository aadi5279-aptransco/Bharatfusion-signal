@echo off
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 (
 echo Install Python 3.11 for Windows from python.org, including Tcl/Tk and the Python launcher.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
 echo Installation failed. Check the error above and internet access.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m unittest discover -s tests -v
pause
