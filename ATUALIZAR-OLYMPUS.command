#!/bin/bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")" && pwd)"
TARGET_ROOT="${1:-${OLYMPUS_TARGET_ROOT:-$HOME/Documents/OLYMPUS-PILOTO}}"
MANIFEST="$SOURCE_ROOT/frontend/public/olympus-version.json"
VERSION="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$MANIFEST" | head -n 1)"
BUILD="$(sed -n 's/.*"build"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$MANIFEST" | head -n 1)"

[ "$(uname -s)" = "Darwin" ] || { echo "ERRO: atualização suportada apenas no macOS."; exit 1; }
[ -n "$VERSION" ] && [ -n "$BUILD" ] || { echo "ERRO: manifesto de versão inválido."; exit 1; }
for tool in ditto curl python3 node npm lsof; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERRO: componente ausente: $tool"; exit 1; }
done

if [ ! -d "$TARGET_ROOT" ]; then
  echo "Nenhuma instalação existente em $TARGET_ROOT; executando instalação limpa."
  mkdir -p "$(dirname "$TARGET_ROOT")"
  ditto "$SOURCE_ROOT" "$TARGET_ROOT"
  chmod +x "$TARGET_ROOT"/*.command 2>/dev/null || true
  exec "$TARGET_ROOT/start_olympus.command"
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
PARENT="$(dirname "$TARGET_ROOT")"
STAGE="$PARENT/.olympus-stage-$STAMP-$$"
ROLLBACK="$PARENT/.olympus-rollback-$STAMP-$$"
PERSIST="$PARENT/.olympus-persist-$STAMP-$$"
cleanup(){ rm -rf "$STAGE" "$PERSIST"; }
trap cleanup EXIT

echo "Preparando atualização OLYMPUS $VERSION ($BUILD)..."
rm -rf "$STAGE" "$ROLLBACK" "$PERSIST"
mkdir -p "$STAGE" "$PERSIST"
ditto "$SOURCE_ROOT" "$STAGE"

preserve_file(){
  rel="$1"
  if [ -f "$TARGET_ROOT/$rel" ]; then
    mkdir -p "$PERSIST/$(dirname "$rel")"
    ditto "$TARGET_ROOT/$rel" "$PERSIST/$rel"
  fi
}
preserve_dir(){
  rel="$1"
  if [ -d "$TARGET_ROOT/$rel" ]; then
    mkdir -p "$PERSIST/$(dirname "$rel")"
    ditto "$TARGET_ROOT/$rel" "$PERSIST/$rel"
  fi
}

preserve_file "backend/.env"
preserve_file "frontend/.env.local"
preserve_file ".olympus/provider-settings.json"
preserve_file ".olympus/runtime/capacity-fabric.json"
preserve_file ".olympus/runtime/omniroute-pools.json"
preserve_dir ".olympus/cloud"
preserve_dir "projects"
preserve_dir "data"
preserve_dir "backend/data"

for db in "$TARGET_ROOT"/*.db "$TARGET_ROOT"/backend/*.db; do
  [ -f "$db" ] || continue
  case "$db" in
    "$TARGET_ROOT"/*) rel="${db#$TARGET_ROOT/}" ;;
    *) continue ;;
  esac
  preserve_file "$rel"
done

if [ -x "$TARGET_ROOT/stop_olympus.command" ]; then
  OLYMPUS_PRESERVE_OMNIROUTE=1 "$TARGET_ROOT/stop_olympus.command" || true
fi

# Runtime/build artefacts are never carried into the new release.
rm -rf "$STAGE/.venv" "$STAGE/frontend/node_modules" "$STAGE/frontend/.next" "$STAGE/.git"
rm -rf "$STAGE/.olympus/runtime"
mkdir -p "$STAGE/.olympus/runtime"

if [ -d "$PERSIST" ]; then
  ditto "$PERSIST" "$STAGE"
fi

chmod +x "$STAGE"/*.command 2>/dev/null || true
[ ! -f "$STAGE/backend/.env" ] || chmod 600 "$STAGE/backend/.env"
[ ! -f "$STAGE/frontend/.env.local" ] || chmod 600 "$STAGE/frontend/.env.local"
[ ! -f "$STAGE/.olympus/provider-settings.json" ] || chmod 600 "$STAGE/.olympus/provider-settings.json"

mv "$TARGET_ROOT" "$ROLLBACK"
mv "$STAGE" "$TARGET_ROOT"

rollback(){
  echo "ERRO: nova versão não passou no smoke test; restaurando instalação anterior."
  [ -x "$TARGET_ROOT/stop_olympus.command" ] && OLYMPUS_PRESERVE_OMNIROUTE=1 "$TARGET_ROOT/stop_olympus.command" >/dev/null 2>&1 || true
  rm -rf "$TARGET_ROOT"
  mv "$ROLLBACK" "$TARGET_ROOT"
  [ -x "$TARGET_ROOT/start_olympus.command" ] && "$TARGET_ROOT/start_olympus.command" || true
  exit 1
}

"$TARGET_ROOT/start_olympus.command" || rollback

backend="$(curl -fsS --max-time 4 -H 'Cache-Control: no-cache' "http://127.0.0.1:8000/health?ts=$(date +%s)" 2>/dev/null || true)"
frontend="$(curl -fsS --max-time 4 -H 'Cache-Control: no-cache' "http://127.0.0.1:3000/olympus-version.json?ts=$(date +%s)" 2>/dev/null || true)"
printf '%s' "$backend" | grep -Eq '"version"[[:space:]]*:[[:space:]]*"'"$VERSION"'"' || rollback
printf '%s' "$frontend" | grep -Eq '"version"[[:space:]]*:[[:space:]]*"'"$VERSION"'"' || rollback
printf '%s' "$frontend" | grep -Eq '"build"[[:space:]]*:[[:space:]]*"'"$BUILD"'"' || rollback

rm -rf "$ROLLBACK"
trap - EXIT
cleanup

echo
echo "============================================================"
echo " OLYMPUS $VERSION ATUALIZADO E VALIDADO"
echo "============================================================"
echo "Build: $BUILD"
echo "Diretório: $TARGET_ROOT"
echo "Credenciais, bancos, projetos e configurações preservados."
echo "Arquivos antigos/substituídos removidos após validação."
echo "============================================================"
