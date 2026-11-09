@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 py -3.11 -m venv .venv
 if errorlevel 1 python -m venv .venv
 if errorlevel 1 (echo Python 3.11 or later required.& pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install -r requirements-insights.txt
if errorlevel 1 (echo Python dependencies failed.& pause & exit /b 1)
where npm >nul 2>&1
if errorlevel 1 (echo Install Node.js LTS first, then rerun this installer.& pause & exit /b 1)
pushd web
call npm install
if errorlevel 1 (popd & echo React npm install failed.& pause & exit /b 1)
call npm run build
if errorlevel 1 (popd & echo React build failed.& pause & exit /b 1)
popd
.venv\Scripts\python.exe -m unittest discover -s tests -q
if errorlevel 1 (echo Existing test suite failed.& pause & exit /b 1)
.venv\Scripts\python.exe -m unittest discover -s insights\tests -q
if errorlevel 1 (echo Market Insights tests failed.& pause & exit /b 1)
if not exist .env copy .env.example .env >nul
if not exist .env (echo Missing .env template.& pause & exit /b 1)
echo Installation complete. Edit .env to configure Dhan and verified holiday calendar.
pause
