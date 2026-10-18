# OLYMPUS Cloud Beta — checkpoint de staging (2026-10-18)

## Implantação em Railway
Projeto: `OLYMPUS Open Lovable Pilot`, ambiente `pilot`, **todos os novos serviços separados do piloto original**.

- `olympus-cloud-backend`: FastAPI, uma réplica, porta interna 8000, serviço sem domínio público, commit pinado `a1070978f7696b99fc3284fd60f21e323767b625`.
- `olympus-cloud-frontend`: Next.js 16.4.2, uma réplica, porta interna 3000, sem domínio público, commit pinado `872d78aaf8be6682d692cf12b6600ac1463bbfd3`.
- `olympus-cloud-private-access`: gateway de borda Bun com Basic Auth e sessão por cookie HttpOnly assinada, encaminha Bearer separado para o OLYMPUS. Código-fonte versionado em `deploy/railway/olympus-cloud-gateway.ts`; a função é implantada explicitamente, não por push automático.
- `olympus-beta-data`: volume persistente de 512 MB em `/data`, montado somente no backend.
- URL única: https://olympus-cloud-private-access-pilot.up.railway.app/
- Backend e frontend sem domínio público. O acesso público sem credenciais foi negado com **HTTP 401**.

## Testes concluídos
- GitHub Actions: build de dois contêineres, frontend `/login` 200, API backend via rewrite `/api/olympus/health` 200, missão sem token negada, JWT obrigatório em staging, e inicialização com volume vazio root-owned. Workflow `.github/workflows/cloud-container-smoke.yml`.
- CI geral backend/frontend: sucesso para as alterações da branch.
- Railway, via sonda privada temporária: Basic Auth → sessão HttpOnly → frontend 200 → `/api/olympus/health` 200 → `/api/olympus/auth/login` 200 → `/api/olympus/cloud/saas/organization` 200 (Bearer) → tentativa autenticada de missão não homologada negada com **503**.
- Backend foi reiniciado/reimplantado, e a sequência acima passou novamente. A integridade de registros históricos em mais de uma reinicialização ainda requer teste específico.
- A sonda temporária e suas referências a credenciais foram removidas após a validação.
- Antigos `open-lovable-upstream`, `olympus-lovable-staging` e `olympus-private-access` preservados.

## Segurança e escopo
- Variáveis secretas apenas no Railway; não incluir valores em git, logs ou documentos.
- `OLYMPUS_ENV=staging`, `OLYMPUS_MISSION_SANDBOX_VERIFIED=0`, `OLYMPUS_OPEN_LOVABLE_ENABLED=0`, `OLYMPUS_ENABLE_LEGACY_API=0`. Execução por modelos e previews executáveis continuam bloqueados deliberadamente.
- Login administrativo de homologação é provisório e deve ser vinculado ao e-mail confirmado pelo proprietário antes da entrega de acesso pessoal.
- Código-fonte GitHub permanece público. Autenticação web privada não muda a visibilidade do código.
- O backend usa arquivos SQLite no volume para SaaS/projetos; **não operar múltiplas réplicas nem comercializar como multiusuário em escala** antes da migração e do isolamento de execução.
- Serviço ativo no Railway pode gerar custo de infraestrutura.

## Próximos gates
1. Configurar acesso de homologação do usuário com e-mail confirmado e credenciais rotacionadas.
2. Provar persistência de um projeto entre reinicializações e backup/restauração.
3. Integrar execução de missão somente em ambiente isolado por tenant, idempotência, orçamentos e bloqueio de sobrecusto.
4. Garantir exportação fidedigna, build independente e Playwright desktop/mobile; corrigir casos Rosales Café sem alegações inventadas.
5. Testar UX completa como usuário, não apenas HTTP; revisar LGPD, logs, retenção e privacidade do repo.
6. Somente após gates, promover branch via PR revisado. `main` permanece em 3.0.8.

**Estado:** URL privada funcional para login e administração de homologação. Ainda NÃO apto à distribuição de missões de geração para clientes.
