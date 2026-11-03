#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Creando el entorno virtual por primera vez..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -m playwright install chromium
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Se creó .env: completá tu usuario y contraseña y volvé a correr ./iniciar.sh"
  exit 0
fi
exec .venv/bin/python app.py
