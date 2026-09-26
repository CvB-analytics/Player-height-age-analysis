@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo De app is nog niet geinstalleerd.
  echo Dubbelklik eerst eenmalig op setup_app.bat.
  pause
  exit /b 1
)
echo De volleybal-app wordt gestart. Dit venster mag open blijven.
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --browser.gatherUsageStats false
if errorlevel 1 pause
