#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ "$(uname -s)" != "Darwin" ]; then
  echo "ERRO: este atualizador é exclusivo para macOS."
  exit 1
fi
exec python3 "$ROOT/scripts/update_macos.py" --source "$ROOT" "$@"
