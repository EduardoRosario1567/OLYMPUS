from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool
from typing import List, Optional

from app.core.deps import identidade_com_permissao
from olympus.skills.fabric import SkillsFabric

router = APIRouter(prefix="/skills-fabric", tags=["skills-fabric"])
_read = identidade_com_permissao("projects.read")
_manage = identidade_com_permissao("members.manage")


class FabricUpdate(BaseModel):
    enabled: Optional[StrictBool] = None
    disabled_skills: Optional[List[str]] = None


@router.get("")
def catalog(identity=Depends(_read)):
    return SkillsFabric(tenant_id=identity.tenant_id).catalog()


@router.patch("")
def configure(payload: FabricUpdate, identity=Depends(_manage)):
    fabric = SkillsFabric(tenant_id=identity.tenant_id)
    if payload.enabled is None and payload.disabled_skills is None:
        raise HTTPException(status_code=400, detail="Informe uma configuração.")
    try:
        fabric.configure(payload.enabled, payload.disabled_skills)
    except ValueError:
        raise HTTPException(status_code=400, detail="Configuração de skill inválida.")
    except OSError:
        raise HTTPException(status_code=503, detail="Não foi possível salvar a configuração.")
    return fabric.catalog()
