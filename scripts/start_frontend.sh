#!/usr/bin/env bash
# Sobe o frontend do Olympus.
set -euo pipefail

cd frontend

if [ ! -f .env.local ]; then
  echo ".env.local não existe. Copiando de .env.local.example..."
  cp .env.local.example .env.local
fi

if [ ! -d node_modules ]; then
  echo "node_modules ausente — rodando npm install..."
  npm install
fi

npm run dev
