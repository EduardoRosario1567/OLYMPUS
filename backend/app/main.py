import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Ancorado em __file__ (backend/app/main.py -> parents[1] é backend/), não no CWD:
    # `uvicorn app.main:app` (rodado de dentro de backend/) e
    # `uvicorn backend.app.main:app --app-dir backend` (rodado da raiz do repo)
    # tinham CWDs diferentes, e load_dotenv() sem argumento só busca dotenv
    # subindo a árvore a partir do CWD — podia silenciosamente não achar o .env.
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass  # sem python-dotenv instalado: segue com variáveis de ambiente do sistema mesmo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, dashboard, projects, executions, logs

app = FastAPI(title="Olympus API", version="0.1.0")

origens = os.environ.get("OLYMPUS_CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(executions.router)
app.include_router(logs.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
