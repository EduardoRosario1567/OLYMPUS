#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3 || true)"
fi
if [ -z "$PYTHON" ]; then
  echo "ERRO: Python 3 não foi encontrado. Abra start_olympus.command primeiro."
  read -r -p "Pressione ENTER para fechar."
  exit 1
fi

"$PYTHON" "$ROOT/scripts/configure_ai_providers.py"
read -r -p "Pressione ENTER para fechar."
