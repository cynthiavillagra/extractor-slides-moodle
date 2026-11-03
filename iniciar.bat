@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creando el entorno virtual por primera vez...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
  .venv\Scripts\python -m playwright install chromium
)
.venv\Scripts\python app.py
pause
