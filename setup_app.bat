@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is niet gevonden. Installeer Python 3.11 of nieuwer en vink "Add Python to PATH" aan.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo De installatie is niet gelukt. Controleer de internetverbinding voor deze eenmalige installatie.
  pause
  exit /b 1
)
echo Installatie gereed. Hierna kan de app zonder internet werken.
pause
