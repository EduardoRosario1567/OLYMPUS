#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "OLYMPUS — validação do núcleo"
echo
PYTHON_BIN="python3"
if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

if ! "$PYTHON_BIN" -c 'import fastapi, jwt, uvicorn' >/dev/null 2>&1; then
  echo "Instalando dependências do backend..."
  "$PYTHON_BIN" -m pip install -r "$ROOT_DIR/backend/requirements.txt" || exit 1
fi

if [ ! -x "$ROOT_DIR/frontend/node_modules/.bin/next" ]; then
  echo "Instalando dependências do frontend..."
  (cd "$ROOT_DIR/frontend" && npm ci) || exit 1
fi

echo "Provisionando navegador real para validação..."
(cd "$ROOT_DIR/frontend" && npx playwright install chromium) || {
  echo "BLOQUEADO: não foi possível instalar o Chromium real."
  exit 2
}

echo "Construindo frontend de produção..."
(cd "$ROOT_DIR/frontend" && npm run build) || exit 1
echo "Executando regressão do backend e núcleo..."
PYTHONPATH="$ROOT_DIR" "$PYTHON_BIN" -W error::ResourceWarning -m unittest discover -s "$ROOT_DIR/tests" -q
PYTHONPATH="$ROOT_DIR" "$PYTHON_BIN" scripts/core_runtime_e2e.py
PYTHONPATH="$ROOT_DIR" "$PYTHON_BIN" scripts/provider_matrix_e2e.py
PYTHONPATH="$ROOT_DIR" "$PYTHON_BIN" scripts/blind_mission_gate.py

echo
echo "NÚCLEO VALIDADO: todos os gates locais passaram."
read -r -p "Pressione Enter para fechar..." _
