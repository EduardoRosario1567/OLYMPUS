#!/bin/bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$SOURCE_ROOT/frontend/public/olympus-version.json" | head -n 1)"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "ERRO: este pacote piloto foi preparado exclusivamente para macOS."
  read -r -p "Pressione ENTER para fechar."
  exit 1
fi

missing=""
for tool in ditto curl python3 node npm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing="$missing $tool"
  fi
done
if [ -n "$missing" ]; then
  echo "ERRO: componentes necessários não encontrados:$missing"
  echo "Instale Python 3.9 ou superior e Node.js 20.9 ou superior antes de continuar."
  read -r -p "Pressione ENTER para fechar."
  exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "ERRO: o Python precisa ser 3.9 ou superior."
  read -r -p "Pressione ENTER para fechar."
  exit 1
fi
if ! node -e 'const [major,minor]=process.versions.node.split(".").map(Number); process.exit(major>20 || (major===20 && minor>=9) ? 0 : 1)'; then
  echo "ERRO: o Node.js precisa ser 20.9 ou superior."
  read -r -p "Pressione ENTER para fechar."
  exit 1
fi

TARGET_ROOT="$HOME/Documents/OLYMPUS-PILOTO"
if [ -d "$TARGET_ROOT" ]; then
  echo "Instalação existente detectada. Executando atualização cumulativa segura."
  exec "$SOURCE_ROOT/ATUALIZAR-OLYMPUS.command" "$TARGET_ROOT"
fi

mkdir -p "$(dirname "$TARGET_ROOT")"
ditto "$SOURCE_ROOT" "$TARGET_ROOT"
chmod +x \
  "$TARGET_ROOT/INSTALAR-OLYMPUS.command" \
  "$TARGET_ROOT/ATUALIZAR-OLYMPUS.command" \
  "$TARGET_ROOT/start_olympus.command" \
  "$TARGET_ROOT/stop_olympus.command" \
  "$TARGET_ROOT/configure_ai.command"

echo
echo "INSTALAÇÃO LOCAL: PASS"
echo "Versão: $VERSION"
echo "Pasta: $TARGET_ROOT"
echo "Nenhum projeto, banco ou segredo de outro usuário foi importado."
echo

"$TARGET_ROOT/start_olympus.command"
