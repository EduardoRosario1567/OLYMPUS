import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import identidade_com_permissao
from olympus.skills.catalog import SkillCatalog


router = APIRouter(prefix="/skills", tags=["skills"])
_can_read = identidade_com_permissao("projects.read")
_can_manage = identidade_com_permissao("members.manage")
_ROOT = Path(__file__).resolve().parents[3]
CATALOG = SkillCatalog(os.environ.get("OLYMPUS_SKILLS_DIR", str(_ROOT / ".olympus" / "skills")))


class GitHubSkillImport(BaseModel):
    url: str = Field(min_length=19, max_length=500)


class SkillStatusUpdate(BaseModel):
    status: str = Field(pattern="^disabled$")


@router.get("")
def list_skills(_identity=Depends(_can_read)):
    rows = CATALOG.list()
    return {
        "skills": rows,
        "counts": {
            "active": sum(item["status"] == "active" for item in rows),
            "review_required": sum(item["status"] == "review_required" for item in rows),
            "blocked": sum(item["status"] == "blocked" for item in rows),
        },
        "import_policy": {
            "source": "public_github_https",
            "automatic_execution": False,
            "review_required": True,
        },
    }


@router.post("/imports/github", status_code=201)
def import_github(payload: GitHubSkillImport, _identity=Depends(_can_manage)):
    try:
        result = CATALOG.import_github(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=502, detail="Não foi possível baixar o repositório informado.") from exc
    return {
        "imported": list(result.imported),
        "status": result.status,
        "findings": list(result.findings),
        "message": "Skill importada para revisão; nenhuma instrução foi executada.",
    }


@router.post("/{skill_id}/approve")
def approve_skill(skill_id: str, _identity=Depends(_can_manage)):
    try:
        return CATALOG.approve(skill_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Skill não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.patch("/{skill_id}")
def update_skill(skill_id: str, payload: SkillStatusUpdate, _identity=Depends(_can_manage)):
    try:
        return CATALOG.disable(skill_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Skill externa não encontrada.")
