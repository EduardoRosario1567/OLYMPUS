# OLYMPUS — implantação beta privada

Esta branch prepara **dois contêineres distintos**: frontend Next.js (porta interna 3000) e backend FastAPI (porta interna 8000).

## Arquitetura

- Browser → acesso privado / autenticação de borda → frontend:3000
- Frontend `/api/olympus/*` → rewrite same-origin → `http://olympus-cloud-backend.railway.internal:8000/*`
- Backend permanece exclusivamente na rede privada. Nunca gerar domínio público diretamente para backend.
- O frontend público não deve ser aberto antes do proxy autenticado. A autenticação OLYMPUS deve ser independente da autenticação de borda.
- O backend deve usar uma réplica e volume persistente no caminho `/data`, e `OLYMPUS_CLOUD_DATA_DIR=/data`. **SQLite compartilhado impede escalabilidade horizontal; não lançar multiusuário comercial** sem migração real para um DB adequado.
- `OLYMPUS_ENV=staging` exige JWT forte, rejeita CORS `*` e proíbe execução local de previews não isolados.
- Não habilitar `OLYMPUS_ENABLE_LEGACY_API`, `OLYMPUS_ALLOW_UNSANDBOXED_PREVIEW` ou `OLYMPUS_OPEN_LOVABLE_ENABLED` ao lançar a beta, até homologação.

## Testes automatizados

`.github/workflows/cloud-container-smoke.yml` constrói frontend e backend com o contexto raiz e roda login HTML + healthcheck FastAPI via URL same-origin, além de recusar missões sem token e iniciar staging sem JWT.

## Bloqueios para entregar uma URL aos usuários

1. Contêineres aprovados no CI.
2. Um serviço de backend Railway com volume e segredos exclusivamente configurados no Railway; frontend só acessado por gateway privado.
3. Realizar autenticação ponta a ponta com login OLYMPUS e confirmar que dados e projetos sobrevivem ao restart.
4. Motor de missão com sandbox isolado, verificador de React/Playwright e cópia fiel dos arquivos; não utilizar missão cloud em aberto sem A01.
5. Revisão de segurança e conformidade LGPD, política de retenção/backup, limite de custos e visibilidade do código GitHub (atualmente público).

**Não trata esta branch como produto final**. O OLYMPUS principal e o Open Lovable do piloto são preservados.
