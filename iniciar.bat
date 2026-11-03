@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creando el entorno virtual por primera vez...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
  .venv\Scripts\python -m playwright install chromium
)
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Se creo el archivo .env: completa tu usuario y contrasena y volve a abrir este archivo.
  notepad .env
  pause
  exit /b
)
.venv\Scripts\python app.py
pause
