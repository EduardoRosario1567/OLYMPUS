#!/usr/bin/env bash
# Sobe o backend do Olympus. Rode a partir da raiz do repo (a pasta que
# contém backend/ e olympus/ como irmãos).
set -euo pipefail

if [ ! -f backend/.env ]; then
  echo "backend/.env não existe. Copiando de backend/.env.example..."
  cp backend/.env.example backend/.env
  echo "Edite backend/.env (pelo menos OLYMPUS_ADMIN_SENHA) antes de continuar."
  exit 1
fi

export PYTHONPATH=.
cd backend
uvicorn app.main:app --reload --port 8000
