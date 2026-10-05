#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT/backend"
exec python3 -m uvicorn app.main:app --host "${OLYMPUS_HOST:-0.0.0.0}" --port "${OLYMPUS_PORT:-8000}"
