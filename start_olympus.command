#!/bin/bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$ROOT/.olympus/runtime"
mkdir -p "$RUNTIME_DIR"
EXPECTED_VERSION="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$ROOT/frontend/public/olympus-version.json" | head -n 1)"
[ -n "$EXPECTED_VERSION" ] || { echo "ERRO: versão OLYMPUS não identificada."; exit 1; }
export OLYMPUS_MODEL_TIMEOUT="${OLYMPUS_MODEL_TIMEOUT:-90}"

listener_pids(){ lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }
listener_alive(){ ps -p "$1" -o pid= >/dev/null 2>&1; }
listener_cwd(){ lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1; }
backend_body(){ curl -fsS --max-time 2 -H 'Cache-Control: no-cache' "http://127.0.0.1:8000/health?ts=$(date +%s)" 2>/dev/null || true; }
frontend_body(){ curl -fsS --max-time 2 -H 'Cache-Control: no-cache' "http://127.0.0.1:3000/olympus-version.json?ts=$(date +%s)" 2>/dev/null || true; }
body_is_current(){
  "$PYTHON_BIN" -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("version")==sys.argv[1] and (sys.argv[2]!="frontend" or d.get("product")=="olympus") else 1)' "$EXPECTED_VERSION" "$1" 2>/dev/null
}
backend_is_current(){ backend_body | body_is_current backend; }
frontend_is_current(){ frontend_body | body_is_current frontend; }
wait_current(){ which="$1"; seconds="$2"; for _ in $(seq 1 "$seconds"); do if "$which"; then return 0; fi; sleep 1; done; return 1; }

safe_stop_port(){
  port="$1"; expected_cwd="$2"; label="$3"
  pids="$(listener_pids "$port")"
  [ -n "$pids" ] || return 0
  for pid in $pids; do
    listener_alive "$pid" || { echo "ERRO: o processo mudou; tente iniciar novamente."; return 1; }
    cwd="$(listener_cwd "$pid")"
    [ "$cwd" = "$expected_cwd" ] || {
      echo "ERRO: porta $port pertence a outro processo; $label não será encerrado."
      echo "PID=$pid CWD=$cwd"
      return 1
    }
  done
  for pid in $pids; do
    listener_alive "$pid" && [ "$(listener_cwd "$pid")" = "$expected_cwd" ] || {
      echo "ERRO: identidade do processo mudou; não será encerrado."; return 1;
    }
    kill "$pid" 2>/dev/null || true
  done
  for _ in $(seq 1 12); do [ -z "$(listener_pids "$port")" ] && return 0; sleep 1; done
  for pid in $pids; do
    # A listener may have restarted or a PID may have been reused during TERM.
    remaining="$(listener_pids "$port" | tr '\n' ' ')"
    case " $remaining " in *" $pid "*) ;; *) continue ;; esac
    listener_alive "$pid" || { echo "ERRO: o processo mudou; tente iniciar novamente."; return 1; }
    cwd="$(listener_cwd "$pid")"
    [ "$cwd" = "$expected_cwd" ] || {
      echo "ERRO: o processo da porta $port mudou de identidade; não será encerrado."
      return 1
    }
    kill -KILL "$pid" 2>/dev/null || true
  done
  for _ in $(seq 1 5); do [ -z "$(listener_pids "$port")" ] && return 0; sleep 1; done
  echo "ERRO: não foi possível liberar a porta $port."
  return 1
}

echo "Iniciando OLYMPUS $EXPECTED_VERSION..."
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
if [ -x "$ROOT/.venv/bin/python" ] && ! "$ROOT/.venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "ERRO: .venv usa Python antigo. Instale a candidata em uma pasta nova; dados e credenciais serão preservados."; exit 1;
fi

for t in curl node npm lsof; do command -v "$t" >/dev/null 2>&1 || { echo "ERRO: componente ausente: $t"; exit 1; }; done

if ! curl -sS --max-time 2 http://127.0.0.1:20128/v1/models >/dev/null 2>&1; then
  if command -v omniroute >/dev/null 2>&1; then nohup omniroute serve >"$RUNTIME_DIR/omniroute.log" 2>&1 & echo $! >"$RUNTIME_DIR/omniroute.pid"; fi
fi

[ -x "$ROOT/.venv/bin/python" ] || "$PYTHON_BIN" -m venv "$ROOT/.venv" || exit 1
if [ ! -f "$ROOT/backend/.env" ]; then "$ROOT/.venv/bin/python" "$ROOT/scripts/first_run_setup.py" --template "$ROOT/backend/.env.example" --output "$ROOT/backend/.env" || exit 1; fi
if ! "$ROOT/.venv/bin/python" -c 'import fastapi,jwt,uvicorn' >/dev/null 2>&1; then "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt" || exit 1; fi
chmod 600 "$ROOT/backend/.env"

# Reinicie sempre a instância da mesma versão iniciada com variáveis transitórias.
# Explicit start = clean backend process. Known transient diagnostic overrides are removed.
safe_stop_port 8000 "$ROOT" "backend OLYMPUS" || exit 1
(cd "$ROOT" && env -u OLYMPUS_OMNIROUTE_URL PYTHONPATH="$ROOT" nohup "$ROOT/.venv/bin/python" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 >"$RUNTIME_DIR/backend.log" 2>&1 & echo $! >"$RUNTIME_DIR/backend.launch.pid")
if ! wait_current backend_is_current 30; then echo "ERRO: backend $EXPECTED_VERSION não iniciou. Consulte .olympus/runtime/backend.log"; exit 1; fi
bp="$(listener_pids 8000 | head -1)"; [ -n "$bp" ] && echo "$bp" >"$RUNTIME_DIR/backend.pid"

if [ ! -x "$ROOT/frontend/node_modules/.bin/next" ]; then (cd "$ROOT/frontend" && npm install) || exit 1; fi

# 3.0.6: nunca reutilize um Next/Turbopack antigo em um start explícito.
# A versão anterior podia responder HTTP 200 e ainda manter chunks/hidratação obsoletos.
safe_stop_port 3000 "$ROOT/frontend" "frontend OLYMPUS" || exit 1
rm -rf "$ROOT/frontend/.next"
(cd "$ROOT/frontend" && NEXT_TELEMETRY_DISABLED=1 nohup npm run dev -- --hostname 127.0.0.1 --port 3000 >"$RUNTIME_DIR/frontend.log" 2>&1 & echo $! >"$RUNTIME_DIR/frontend.launch.pid")
if ! wait_current frontend_is_current 90; then echo "ERRO: frontend $EXPECTED_VERSION não iniciou. Consulte .olympus/runtime/frontend.log"; exit 1; fi
fp="$(listener_pids 3000 | head -1)"; [ -n "$fp" ] && echo "$fp" >"$RUNTIME_DIR/frontend.pid"

echo "OLYMPUS $EXPECTED_VERSION pronto."
command -v open >/dev/null 2>&1 && open http://localhost:3000 >/dev/null 2>&1 || true
exit 0
