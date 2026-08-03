# Olympus API (Fase 2 — foundation)

Requer o pacote `olympus` (Fase 1) disponível no PYTHONPATH — rode a partir
do diretório que contém tanto `backend/` quanto `olympus/` como irmãos.

## Rodar localmente

    pip install -r backend/requirements.txt
    export OLYMPUS_ADMIN_SENHA="troque-isso"
    export PYTHONPATH=.
    uvicorn backend.app.main:app --reload --app-dir backend

Login: POST /auth/login {"email": "admin@olympus.local", "senha": "<OLYMPUS_ADMIN_SENHA>"}
Dashboard: GET /dashboard/summary (Authorization: Bearer <token>)

## Não validado neste sandbox

Este código não pôde ser executado aqui (sandbox sem acesso à rede, logo
sem `pip install`). Sintaxe foi checada com `py_compile`; a lógica de
negócio por trás (dashboard_service, pipeline, decision_engine) foi
testada de verdade em `olympus/services/test_dashboard_service.py`.
Antes de considerar isso pronto, rode localmente com as dependências reais.

## Backend Postgres

`OLYMPUS_DB_BACKEND=postgres` ainda não está com a Session real conectada
em `app/core/deps.py` — é um TODO explícito, não um bug escondido.
