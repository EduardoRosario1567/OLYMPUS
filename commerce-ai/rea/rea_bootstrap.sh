#!/usr/bin/env bash
# OLYMPUS Commerce AI — checagem segura antes de configurar REA.
set -euo pipefail
echo "=== REA / OLYMPUS: PRE-REQUISITOS ==="
echo "Mac: $(uname -sm)"
if ! command -v node >/dev/null 2>&1; then
  echo "ERRO: Node.js nao encontrado."
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "ERRO: npm nao encontrado."
  exit 1
fi
echo "Node: $(node -v)"
echo "npm: $(npm -v)"
node -e 'let v=process.versions.node.split(".").map(Number);if(!((v[0]===22&&v[1]>=19)||(v[0]===24&&v[1]>=11)||v[0]>=26))process.exit(1)' || {
  echo "ERRO: o REA requer Node 22.19+, 24.11+ ou 26+."
  exit 1
}
echo "Claude Code: $(command -v claude || echo indisponivel)"
echo "Espaco livre:"
df -h "$HOME" | tail -1
echo
echo "=== FONTE OFICIAL ==="
echo "GitHub: https://github.com/morluto/rea"
echo "npm: rea-agents"
echo "REA nao substitui Ollama, nem desbloqueia a franquia do Gemma."
echo "REA pode analisar arquivos, aplicativos ou dados para os quais haja permissao."
echo "O setup oficial alterara registros MCP/skills dos agentes selecionados;"
echo "ele apresenta um plano e solicita aprovacao antes de gravar."
echo
if [ "${1:-}" = "--configurar" ]; then
  echo "=== INICIANDO SETUP OFICIAL INTERATIVO ==="
  cd "$HOME"
  npx rea-agents setup
else
  echo "Diagnostico concluido. Nenhuma instalacao executada."
  echo "Para iniciar a configuracao do REA: bash rea_bootstrap.sh --configurar"
fi
