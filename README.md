# Olympus — Alpha

Sistema de orquestração de IAs para engenharia de software. Este é o
ponto de entrada único: como subir o app completo (backend + frontend)
localmente e navegar por ele.

## Estrutura

```
olympus/     núcleo (Fase 1) + persistência + read layer — não é um app, é a lógica
backend/     API FastAPI que expõe o núcleo pra interface
frontend/    Next.js — login, dashboard, projetos, execuções, logs
scripts/     start_backend.sh, start_frontend.sh, seed_demo.py
```

`backend/` e `frontend/` são processos separados. Rode os dois ao mesmo
tempo, em dois terminais.

## Pré-requisitos

- Python 3.11+
- Node.js 18+
- Nada de banco externo — a Alpha usa SQLite local (`olympus_dev.db`)

## CI — validação real, não simulada

Este sandbox de desenvolvimento não tem acesso à rede para `pip`/`npm`
(ver `.github/workflows/ci.yml` — mesmos comandos, rodando de verdade).
O workflow do GitHub Actions faz, em runners com rede real:

- instala as dependências do backend e do frontend
- sobe o backend de verdade, espera o `/health` responder
- roda a suíte de testes (`pytest tests/ -v`)
- roda o seed 2x e confirma que a segunda vez não duplica nada
- faz login de verdade via HTTP, extrai o JWT, chama `/dashboard/summary`,
  `/projects`, `/executions`, `/logs` com o token — e confirma que sem
  token vem 401
- builda o frontend (`next build`) e sobe em modo produção (`next start`)
- confirma que a página inicial responde

Cada push ou PR dispara isso. O resultado fica na aba **Actions** do
repositório, com log completo de cada passo — inclusive os que falharem.

Nota: ainda não existe `package-lock.json` commitado (nunca rodei
`npm install` com rede de verdade), então a CI usa `npm install` em vez de
`npm ci`. Assim que alguém rodar `npm install` localmente com rede, vale
commitar o `package-lock.json` gerado e trocar o workflow pra `npm ci`
(mais estrito/reprodutível).

## Subir em 4 passos

**Terminal 1 — backend:**

```bash
./scripts/start_backend.sh
```

Na primeira vez ele para e pede pra você editar `backend/.env` (pelo menos
`OLYMPUS_ADMIN_SENHA`). Roda de novo depois de editar.

**Terminal 2 — frontend:**

```bash
./scripts/start_frontend.sh
```

**(Opcional) dados de exemplo**, pra não abrir o dashboard vazio na primeira vez:

```bash
export PYTHONPATH=.
python3 scripts/seed_demo.py
```

Isso cria 2 projetos e roda tarefas de verdade pelo motor de decisão —
não é número inventado, é o pipeline real gravando no mesmo banco que o
backend lê. É idempotente: rodar de novo não duplica nada.

**Abrir:** `http://localhost:3000` → login com o email/senha do
`backend/.env` → dashboard → navega por Projetos / Execuções / Logs pela
sidebar → Sair.

## O que esperar

- Sem rodar o seed, tudo aparece vazio ou "não disponível" — é o
  comportamento correto (nada de dado fake escondendo entidade não
  implementada).
- "Agentes" no dashboard aparece como "pendente de modelagem" — nunca foi
  implementado como entidade real. "Projetos" já é real desde a Fase 2.2
  e conta valores de verdade.
- O motor de decisão (classificador, policy engine, fallback, downgrade
  por custo, provider availability) roda 100% no backend. O frontend só
  consome API — nunca decide nada.

## Rodando só o núcleo (sem subir nada)

```bash
export PYTHONPATH=.
python3 -m olympus.demo               # motor de decisão isolado, sem banco
python3 -m olympus.demo_persistente   # pipeline completo + persistência real
```

## Documentação mais detalhada

- `backend/README.md` — variáveis de ambiente, troca pra Postgres, o que
  não foi validado ainda
