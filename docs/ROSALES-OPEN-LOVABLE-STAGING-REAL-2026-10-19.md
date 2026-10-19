# Missão Rosales Café — Open Lovable staging (19/10/2026)

## Ambiente real utilizado
- Serviço Railway privado: `olympus-lovable-staging` (snapshot Open Lovable Firecrawl fixado no commit `806b8072f28afea11fa2b028cac1449eff74c511`, com patch de roteamento Groq e exportação OLYMPUS).
- Gerador com Groq `openai/gpt-oss-120b`, sandbox descartável E2B, sem disponibilização pública e sem senhas administrativas.
- Serviço auxiliar de prova em Railway com reinício `NEVER`. Após os testes, `OLYMPUS_ROSALES_PROBE_ONCE=0` e a referência de token de exportação foi removida do auxiliar.
- Os serviços principais do OLYMPUS não foram alterados nesta missão.

## Tentativa inicial e bug exposto
O modelo `qwen/qwen3.8-27b` gerou arquivo React com import `./components/Hero`, sem escrever o componente correspondente. A API `run-command-v2` retornou `success:true` e `exitCode:0`, mas o campo `output` continha `RollupError: Could not resolve "./components/Hero"` e `Return code: 1`. **Não aceitar o status externo do wrapper como prova do build.**

## Prova 2 — Open Lovable gera, aplica, compila e exporta
No novo sandbox, prompt restrito a `src/App.jsx` e `src/index.css`, sem imagens externas e sem alegações comerciais não comprovadas:
- `generation: ok`, 2 arquivos.
- `apply: ok`, 2 arquivos escritos.
- `build: ok`, código **real** de saída `0` obtido do transcript do E2B.
- `export: ok`, 9 arquivos via `/api/olympus-export` protegido. Todos os hashes dos arquivos e o hash do manifesto foram validados. Manifesto SHA-256: `c3ec0d86ebc86ffe442c07d4038dcf91bc71ab65335a83344731afd8e0bdf911`.
- Uma checagem inicial marcou `contentApproved:false` por procurar URLs em **todos os nove arquivos**, incluindo metadados técnicos. A revisão do arquivo `src/App.jsx` mostrou apenas o conjunto de textos aprovados para Rosales Café; o CSS não faz chamadas externas.
- Os dois arquivos produzidos pelo Open Lovable foram preservados em `entregas/rosales-cafe-open-lovable-qa/src/`, separadamente dos arquivos do verificador.

## Prova independente — React/Vite/Chromium
Workflow: https://github.com/EduardoRosario1567/OLYMPUS/actions/runs/39253592269

- `npm run build` no runner GitHub Actions: **PASS**.
- Playwright Chromium: **390×844 (iPhone) PASS** e **1440×900 (desktop) PASS**.
- Cinco links internos verificados, links de navegação funcionais, **zero** transbordamento horizontal, erros de página ou requisições externas.
- Inspeção textual de alegações não confirmadas passou.
- Screenshots desktop/mobile estão no artifact privado `rosales-open-lovable-browser-evidence` do workflow (retenção de 7 dias).

## Limites, decisões e próximos gates
A missão foi executada diretamente pelo **Open Lovable em staging**, com QA independente. Ela **ainda não foi executada pelo comando comum da interface autenticada do OLYMPUS**, e o upstream mantém estado global entre sessões. Geração geral continua bloqueada até isolamento real por missão/tenant, controle de custo e habilitação explícita do roteador de entrega.

Não promover à `main`, não expor staging publicamente, não afirmar que uma missão para múltiplos usuários está homologada. Reaproveitar o validador de build real e o contrato de exportação no OLYMPUS.
