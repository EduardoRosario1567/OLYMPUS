# Open Lovable como motor interno — piloto controlado

## Contrato de integração no OLYMPUS
A API normal de missões cloud autentica a organização e atribui workspaces por execução. O adapter opt-in roteia somente missões web para Open Lovable; todo o restante continua sob o orquestrador original. As execuções React **não são publicadas** até haver comprovação de navegador independente.

Fluxo: criar sandbox → confirmar ID → gerar React → aplicar → confirmar ID → build remoto → exportar snapshot autenticado do mesmo ID → verificar hash SHA-256 de cada arquivo e hash do manifesto → confirmar ID → preparar workspace de revisão. As fontes escritas devem ser exclusivamente aquelas obtidas na exportação; arquivos sintéticos não podem ser adicionados depois de afirmar que um build passou.

## Importante: upstream original não entrega snapshot íntegro
O Open Lovable original grava \`global.activeSandboxProvider\`, mas suas rotas de ZIP e leitura de fontes referenciam \`global.activeSandbox\`. A ponte **não usa essas rotas como prova**. O endpoint de referência está em \`integrations/open_lovable_upstream/app/api/olympus-export/route.ts\` e precisa ser instalado e auditado em um fork dedicado; ele **NÃO está operacional no Railway atualmente**.

Esse endpoint usa um segredo dedicado e exporta somente fontes UTF-8 seguras, com hashes. Não exporta binários: projetos que exigirem imagens locais devem permanecer bloqueados até um mecanismo binário íntegro ser acrescentado. O servidor de geração continua com estado global; nenhum dado torna automaticamente a aplicação multiusuário.

## Flags, sempre DESLIGADAS até homologação
- \`OLYMPUS_OPEN_LOVABLE_ENABLED=1\` liga o adapter somente em ambiente não-produtivo.
- \`OLYMPUS_OPEN_LOVABLE_EXCLUSIVE=1\` habilita execução única local, mas não isola pods, usuários nem processos remotos.
- \`OLYMPUS_OPEN_LOVABLE_PILOT_TENANT_ID\`: identificador da organização explicitamente autorizada; sem ele, ou se o tenant divergir, missões continuam no motor original sem usar o sandbox compartilhado.
- \`OLYMPUS_OPEN_LOVABLE_URL\`: host privado \`http://*.railway.internal\`, se ambos os serviços estiverem na mesma rede; ou proxy HTTPS protegido por Basic.
- \`OLYMPUS_OPEN_LOVABLE_USER\` / \`OLYMPUS_OPEN_LOVABLE_PASSWORD\` para o proxy HTTPS.
- \`OLYMPUS_OPEN_LOVABLE_EXPORT_TOKEN\`: segredo do adapter; corresponde a \`OLYMPUS_BRIDGE_EXPORT_TOKEN\` no fork upstream.
- \`OLYMPUS_OPEN_LOVABLE_MODEL\`: nome de modelo disponível e testado.

**Nunca colocar tokens no GitHub ou no frontend.** Preservar chaves Groq/E2B existentes.

## Barreiras reais
1. **Sessões:** sandbox e conversa globais no upstream. Um lock de threads + lease de arquivo POSIX (diretório privado `OLYMPUS_OPEN_LOVABLE_LOCK_DIR`) impede concorrência entre processos no mesmo host, mas NÃO entre réplicas Railway, clientes conectados diretamente ao upstream ou tenants. Corrigir por tenant e missão ou instância descartável única por execução.
2. **Fontes:** endpoint autenticado de snapshot precisa ser instalado em upstream dedicado e testado com E2B real, sem arquivos ausentes, truncados ou trocados. É obrigatório hash consistente do conteúdo real após o build.
3. **Qualidade:** React/Vite necessita build independente no snapshot exportado e Playwright real (desktop e mobile), além de verificação visual, acessibilidade, dados, imagens e licenças.
4. **Confiabilidade e custos:** executar Rosales Café de ponta a ponta com Groq/E2B reais, idempotência, interrupção, retomada, TTL do sandbox, limites de gasto e logs redigidos.
5. **Deploy:** staging privado, depois rollout com rollback. O Railway atual hospeda Open Lovable e proxy; não é um backend OLYMPUS completo.

## Evidências disponíveis
- 11 testes offline de contrato, incluindo exportação ausente, adulterada, caminhos inseguros, troca de sandbox, ausência de token, concorrência e bloqueio em produção.
- CI normal valida backend, frontend, npm audit, interface Playwright e fallback. A nova exportação é um contrato simulado, **não um teste com upstream real**.
- Tudo fica em branch de trabalho, com PR em rascunho; nenhuma alteração em \`main\` ou deploy automático.

**Estado atual: a ponte é código em homologação. Não declarar Rosales Café concluído nem ativar produção.**
