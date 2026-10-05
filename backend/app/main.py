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
from fastapi.staticfiles import StaticFiles
from app.core.security import validar_configuracao_producao

from app.api import auth, dashboard, projects, executions, logs, missions, providers, skills, cloud_runtime, cloud_projects, github, railway, runner, memory, artifacts, media, saas
from app.api import skills_fabric

validar_configuracao_producao()
APP_VERSION = "3.0.9"
APP_BUILD = "DELIVERY-QUALITY-RC1"
app = FastAPI(title="Olympus API", version=APP_VERSION)

origens = [item.strip() for item in os.environ.get(
    "OLYMPUS_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",") if item.strip()]
if os.environ.get("OLYMPUS_ENV", "development").lower() in {"production", "prod"} and "*" in origens:
    raise RuntimeError("CORS curinga não é permitido em produção.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origens,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

app.include_router(auth.router)
app.include_router(providers.router)
app.include_router(skills.router)
app.include_router(skills_fabric.router)
app.include_router(cloud_runtime.router)
app.include_router(cloud_projects.router)
app.include_router(github.router)
app.include_router(railway.router)
app.include_router(runner.router)
app.include_router(memory.router)
app.include_router(artifacts.router)
app.include_router(media.router)
app.include_router(saas.router)

# The pre-cloud API uses a global development repository without tenant
# columns. It is excluded by default so a SaaS account can never read it.
if os.environ.get("OLYMPUS_ENABLE_LEGACY_API") == "1":
    app.include_router(dashboard.router)
    app.include_router(projects.router)
    app.include_router(executions.router)
    app.include_router(logs.router)
    app.include_router(missions.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": APP_VERSION, "build": APP_BUILD}


@app.on_event("shutdown")
def shutdown_runtimes() -> None:
    cloud_runtime._STUDIO_RUNTIMES.close()
    cloud_runtime._RUNTIME.close()


WEB_TESTER = Path(__file__).resolve().parents[2] / "web-tester"
is_production = os.environ.get("OLYMPUS_ENV", "development").strip().lower() in {"production", "prod"}
if WEB_TESTER.is_dir() and (not is_production or os.environ.get("OLYMPUS_ENABLE_TESTER") == "1"):
    app.mount("/tester", StaticFiles(directory=str(WEB_TESTER), html=True), name="tester")
