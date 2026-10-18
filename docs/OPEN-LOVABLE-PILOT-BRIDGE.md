# Open Lovable como motor interno — piloto controlado

## O que esta branch entrega
Adapter Python para o pipeline EXISTENTE de missões cloud do OLYMPUS. Quando o recurso for explicitamente habilitado, tarefas da família \`web\` são delegadas ao Open Lovable; missões não-web continuam no motor OLYMPUS. A API atual \`/cloud/missions\`, autenticação, eventos e verificador final são preservados.

Fluxo do adapter: \`create-ai-sandbox-v2\` → \`generate-ai-code-stream\` (SSE) → \`apply-ai-code-stream\` (SSE) → copiar fontes validadas para workspace do OLYMPUS → verificação normal no CloudRuntime. **Não marca entrega como publicada fora do verificador existente.**

## Regra crítica
O upstream firecrawl/open-lovable no commit \`806b8072...\` usa \`global.sandboxState\`, \`global.conversationState\` e \`terminateAll()\`; não oferece isolamento real por usuário. O lock desta branch funciona apenas em um processo. **Não habilitar para múltiplos clientes, múltiplas réplicas ou upstream compartilhado.** O endpoint HTTP expõe comandos de sandbox e só deve permanecer atrás de acesso protegido.

## Ativação (NÃO executar antes dos gates abaixo)
- \`OLYMPUS_OPEN_LOVABLE_ENABLED=1\`: opt-in; default desligado.
- \`OLYMPUS_OPEN_LOVABLE_EXCLUSIVE=1\`: declaração operacional de upstream reservado (não substitui isolamento distribuído).
- \`OLYMPUS_OPEN_LOVABLE_URL=http://open-lovable-upstream.railway.internal:8080\` somente se backend OLYMPUS estiver na mesma rede privada Railway. Alternativa HTTPS do proxy protegido com \`OLYMPUS_OPEN_LOVABLE_USER\` e \`OLYMPUS_OPEN_LOVABLE_PASSWORD\`.
- \`OLYMPUS_OPEN_LOVABLE_MODEL\`: ID de modelo efetivamente disponível na chave do provedor (sem default presumido).

Não escrever credenciais no GitHub e não modificar variáveis existentes do Groq/E2B.

## Bloqueios antes de produção
1. Substituir o estado global no upstream por sessões realmente isoladas e vinculadas ao tenant.
2. O verificador HTML atual do OLYMPUS não comprova a qualidade de uma aplicação React/Vite; criar verificação de build e browser em sandbox seguro. O index.html do Vite, sozinho, não prova que o site funciona.
3. Garantir persistência, idempotência e retomada segura de trabalhos longos.
4. Testar E2B + Groq ponta a ponta com missão Rosales Café, preview visual, download de fontes, falhas e custo real.
5. Testar implantação controlada do backend OLYMPUS no Railway; o piloto existente hospeda somente Open Lovable e proxy privado.

## Verificações desta entrega
- Testes locais simulados de criação e validação de arquivos; caminhos inseguros bloqueados; erro de upstream; concorrência; fallback do motor não-web; recurso desligado por padrão.
- Não executado: chamada real às APIs Groq/E2B, build React, navegador E2E, integração com implantação do OLYMPUS no Railway.

**Status:** ponte implementada em branch de trabalho; rollout de produção deliberadamente bloqueado.
