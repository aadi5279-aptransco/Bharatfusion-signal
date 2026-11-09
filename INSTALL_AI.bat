@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Run INSTALL.bat first.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
if errorlevel 1 (
 echo Installation failed. Send a screenshot of the error above.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 (
 echo Tests failed. Do not use this installation until resolved.
 pause
 exit /b 1
)
echo AI packages installed. FinBERT weights download on first live news analysis.
echo Use Train selected ML after collecting Dhan candles. No trained stock models are bundled.
pause
