@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Run INSTALL.bat first.
 pause
 exit /b 1
)
echo Installing optional local Kronos dependencies. Downloads can be large.
.venv\Scripts\python.exe -m pip install -r requirements-kronos.txt
if errorlevel 1 (
 echo Kronos installation failed. Review the error above.
 pause
 exit /b 1
)
echo Testing official Kronos-mini with synthetic candles. First run downloads weights.
.venv\Scripts\python.exe kronos_adapter.py
pause
