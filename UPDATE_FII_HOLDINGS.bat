@echo off
setlocal
set "PROJECT_DIR=H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights"
if not "%~1"=="" set "PROJECT_DIR=%~1"
if not exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
  echo Existing Python environment not found in "%PROJECT_DIR%".
  echo Run this file with your actual project folder as its argument.
  pause
  exit /b 1
)
echo Close the running application before continuing.
pause
"%PROJECT_DIR%\.venv\Scripts\python.exe" "%~dp0tools\install_fii_holdings_update.py" --project "%PROJECT_DIR%"
if errorlevel 1 goto failed
pushd "%PROJECT_DIR%"
".venv\Scripts\python.exe" -m unittest discover -s insights\tests -q
if errorlevel 1 goto failed_pushed
".venv\Scripts\python.exe" -m unittest discover -s tests -q
if errorlevel 1 goto failed_pushed
pushd web
call npm run build
if errorlevel 1 (
  popd
  goto failed_pushed
)
popd
popd
echo Update installed and tests/build passed. Start START_INSIGHTS.bat in your existing project.
pause
exit /b 0
:failed_pushed
popd
:failed
echo Update validation failed. Keep this output and send the error. Do not restart yet.
pause
exit /b 1
