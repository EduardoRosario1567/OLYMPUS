#!/bin/bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$ROOT/.olympus/runtime"
listener_pids(){ lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }
proc_cwd(){ lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1; }
kill_owned(){ port="$1"; dir="$2"; for pid in $(listener_pids "$port"); do cwd="$(proc_cwd "$pid")"; case "$cwd" in "$dir"|"$dir/"*) kill "$pid" 2>/dev/null || true;; esac; done; }
kill_owned 3000 "$ROOT/frontend"
kill_owned 3001 "$ROOT/frontend"
kill_owned 8000 "$ROOT"
for _ in $(seq 1 8); do [ -z "$(listener_pids 3000)$(listener_pids 3001)$(listener_pids 8000)" ] && break; sleep 1; done
for port in 3000 3001 8000; do
  for pid in $(listener_pids "$port"); do cwd="$(proc_cwd "$pid")"; case "$cwd" in "$ROOT"|"$ROOT/"*) kill -KILL "$pid" 2>/dev/null || true;; esac; done
done
rm -f "$RUNTIME_DIR/frontend.pid" "$RUNTIME_DIR/frontend.launch.pid" "$RUNTIME_DIR/backend.pid" "$RUNTIME_DIR/backend.launch.pid"
if [ "${OLYMPUS_PRESERVE_OMNIROUTE:-0}" != "1" ] && [ -f "$RUNTIME_DIR/omniroute.pid" ]; then pid="$(cat "$RUNTIME_DIR/omniroute.pid" 2>/dev/null || true)"; case "$pid" in ''|*[!0-9]*) ;; *) kill "$pid" 2>/dev/null || true;; esac; rm -f "$RUNTIME_DIR/omniroute.pid"; fi
echo "OLYMPUS encerrado."
exit 0
