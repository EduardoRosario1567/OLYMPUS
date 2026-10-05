#!/bin/zsh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

PROGRESS_PID=""
PROGRESS_TMP=""

cleanup_progress() {
  if [ -n "$PROGRESS_PID" ] && kill -0 "$PROGRESS_PID" 2>/dev/null; then
    kill "$PROGRESS_PID" 2>/dev/null || true
  fi
  if [ -n "$PROGRESS_TMP" ] && [ -f "$PROGRESS_TMP" ]; then
    rm -f "$PROGRESS_TMP"
  fi
  PROGRESS_PID=""
  PROGRESS_TMP=""
}

trap cleanup_progress EXIT INT TERM

run_with_progress() {
  local label="$1"
  shift

  PROGRESS_TMP=$(mktemp "${TMPDIR:-/tmp}/olympus-progress.XXXXXX")
  "$@" >"$PROGRESS_TMP" 2>&1 &
  PROGRESS_PID=$!

  local started=$(date +%s)

  while kill -0 "$PROGRESS_PID" 2>/dev/null; do
    local now=$(date +%s)
    local elapsed=$((now - started))
    printf '\r\033[2K● OLYMPUS trabalhando... %02d:%02d' "$((elapsed / 60))" "$((elapsed % 60))" >&2
    sleep 1
  done

  wait "$PROGRESS_PID"
  local status=$?
  local ended=$(date +%s)
  local elapsed=$((ended - started))

  if [ "$status" -eq 0 ]; then
    printf '\r\033[2K✓ OLYMPUS concluído %02d:%02d\n' "$((elapsed / 60))" "$((elapsed % 60))" >&2
  else
    printf '\r\033[2K✗ OLYMPUS falhou %02d:%02d\n' "$((elapsed / 60))" "$((elapsed % 60))" >&2
  fi

  cat "$PROGRESS_TMP"
  rm -f "$PROGRESS_TMP"
  PROGRESS_PID=""
  PROGRESS_TMP=""
  return "$status"
}

clear

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║                                            ║"
echo "║                 O L Y M P U S              ║"
echo "║                                            ║"
echo "║              DEV AGENT  •  0.4             ║"
echo "║                                            ║"
echo "╚════════════════════════════════════════════╝"
echo ""

echo "Verificando sistema..."

if ! curl -s --max-time 2 \
  http://127.0.0.1:20128/v1/models >/dev/null; then

    echo "○ OmniRoute offline — iniciando..."
    omniroute serve --daemon >/dev/null 2>&1
    sleep 3
fi

if ! curl -s --max-time 2 \
  http://127.0.0.1:20128/v1/models >/dev/null; then

    echo ""
    echo "✗ Não foi possível iniciar o OmniRoute."
    echo ""
    read "?Pressione ENTER para fechar."
    exit 1
fi

echo "● Sistema online"
echo "● OpenRouter Free Models Router"
echo "● FREE MODE"
echo ""
echo "──────────────────────────────────────────────"
echo ""
echo "O que você quer construir?"
echo ""

read "TASK?> "

echo ""
echo "● Modo autônomo sem target obrigatório"
echo "  OLYMPUS investigará o repositório antes de decidir quais arquivos alterar."
echo ""
echo "──────────────────────────────────────────────"
echo ""

START=$(date +%s)
set +e
python3 scripts/olympus_task.py \
    "$TASK" \
    --root "$ROOT" \
    --timeout 30
STATUS=$?
set -e
END=$(date +%s)
ELAPSED=$((END - START))

echo ""
echo "──────────────────────────────────────────────"
echo ""
if [ "$STATUS" -eq 0 ]; then
    echo "✓ TAREFA CONCLUÍDA"
    echo "OLYMPUS STATUS: PASS"
else
    echo "✗ TAREFA NÃO CONCLUÍDA"
    echo "OLYMPUS STATUS: FAIL/BLOCKED"
fi
echo "Tempo total: ${ELAPSED}s"

echo ""
echo "──────────────────────────────────────────────"
echo ""
read "?Pressione ENTER para fechar."
