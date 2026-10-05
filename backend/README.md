# Olympus API (Fase 2 — foundation)

Requer o pacote `olympus` (Fase 1) disponível no PYTHONPATH — rode a partir
do diretório que contém tanto `backend/` quanto `olympus/` como irmãos.

## Rodar localmente

    pip install -r backend/requirements.txt
    export OLYMPUS_ADMIN_SENHA="troque-isso"
    export PYTHONPATH=.
    uvicorn app.main:app --reload --app-dir backend

Login: POST /auth/login {"email": "admin@olympus.local", "senha": "<OLYMPUS_ADMIN_SENHA>"}
Dashboard: GET /dashboard/summary (Authorization: Bearer <token>)

## Validação

Este backend roda de verdade na CI (`.github/workflows/ci.yml`), em
runners do GitHub com rede real — não no sandbox de desenvolvimento, que
não tem acesso a `pip`/`npm`. A primeira rodada da CI já pegou um bug real
de path (`PYTHONPATH=.` resolvido depois de um `cd backend`, apontando pro
lugar errado) — corrigido e re-validado.

## Backend Postgres

`OLYMPUS_DB_BACKEND=postgres` ainda não está com a Session real conectada
em `app/core/deps.py` — é um TODO explícito, não um bug escondido.

## Memória compartilhada

A memória usa SQLite local por padrão. Para compartilhar contexto entre
instalações e IAs, configure `OLYMPUS_MEMORY_DATABASE_URL` com uma URL
PostgreSQL protegida. O contrato da API permanece igual e o SQLite continua
disponível para desenvolvimento/offline.
# Higgsfield

O OLYMPUS possui um adaptador separado para a API oficial da Higgsfield. Ele
não entra no OmniRoute nem no fallback textual: gerações de imagem/vídeo são
jobs assíncronos e exigem autorização paga explícita por solicitação.

Configure no ambiente protegido do backend:

```text
HIGGSFIELD_API_KEY_ID=
HIGGSFIELD_API_KEY_SECRET=
OLYMPUS_HIGGSFIELD_URL=https://api.higgsfield.ai
```

O fluxo é `POST /media/higgsfield/generations`, seguido por
`GET /media/higgsfield/generations/{request_id}`. O segredo nunca é enviado ao
frontend. A integração usa somente a API oficial; repositórios ou automações
de terceiros não fazem parte da cadeia de produção.
