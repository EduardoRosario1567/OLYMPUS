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
for tool in ditto curl node npm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing="$missing $tool"
  fi
done
if [ -n "$missing" ]; then
  echo "ERRO: componentes necessários não encontrados:$missing"
  echo "Instale Python 3.11 ou superior e Node.js 22.23.2 (série 22) ou 24.15 (série 24) antes de continuar."
  read -r -p "Pressione ENTER para fechar."
  exit 1
fi

# Use a compatible interpreter without changing the system Python.
PYTHON_BIN=""
for candidate in "${OLYMPUS_PYTHON:-}" python3.13 python3.12 python3.11 python3; do
  [ -n "$candidate" ] || continue
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"; break
  fi
done
[ -n "$PYTHON_BIN" ] || { echo "ERRO: Python 3.11 ou superior necessário. O Python do sistema será preservado."; exit 1; }
node -e 'const [major,minor,patch]=process.versions.node.split(".").map(Number); process.exit((major===22 && (minor>23 || (minor===23 && patch>=2))) || (major===24 && minor>=15) ? 0 : 1)' || {
  echo "ERRO: use Node 22.23.2+ (série 22) ou 24.15+ (série 24). No macOS 12, use Node 22."; exit 1;
}

TARGET_ROOT="$HOME/Documents/OLYMPUS-PILOTO-$VERSION"
if [ -e "$TARGET_ROOT" ]; then
  TARGET_ROOT="$HOME/Documents/OLYMPUS-PILOTO-$VERSION-$(date +%Y%m%d-%H%M%S)"
fi

mkdir -p "$(dirname "$TARGET_ROOT")"
ditto "$SOURCE_ROOT" "$TARGET_ROOT"
chmod +x \
  "$TARGET_ROOT/INSTALAR-OLYMPUS.command" \
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
