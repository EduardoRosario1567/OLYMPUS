from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.deps import identidade_autenticada, identidade_com_permissao
from app.core.saas import PLATFORM
from app.core.security import emitir_token
from app.core.tenancy import identity_for
from olympus.saas.platform import AuthorizationError, EntitlementError


router = APIRouter(prefix="/cloud/saas", tags=["saas"])


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class OrganizationSwitch(BaseModel):
    organization_id: str = Field(min_length=3, max_length=128)


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = Field(pattern="^(admin|builder|viewer)$")


class InvitationAccept(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=1024)


class MemberRoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|builder|viewer)$")


def _organization_view(value):
    return asdict(value)


def _member_view(value):
    return asdict(value)


@router.get("/organization")
def current_organization(identity=Depends(identidade_com_permissao("organization.read"))):
    organization = PLATFORM.get_organization(identity.tenant_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")
    return {**_organization_view(organization), "role": PLATFORM.role_for(identity.tenant_id, identity.user_id)}


@router.get("/organizations")
def organizations(identity=Depends(identidade_autenticada)):
    return {"organizations": [_organization_view(item) for item in PLATFORM.organizations_for(identity.user_id)]}


@router.post("/organizations", status_code=201)
def create_organization(payload: OrganizationCreate, identity=Depends(identidade_autenticada)):
    try:
        return _organization_view(PLATFORM.create_organization(identity.user_id, identity.email, payload.name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/organizations/switch")
def switch_organization(payload: OrganizationSwitch, identity=Depends(identidade_autenticada)):
    if PLATFORM.role_for(payload.organization_id, identity.user_id) is None:
        raise HTTPException(status_code=404, detail="Organização não encontrada.")
    return {"access_token": emitir_token(identity.email, payload.organization_id), "token_type": "bearer"}


@router.get("/members")
def members(identity=Depends(identidade_com_permissao("members.read"))):
    return {"members": [_member_view(item) for item in PLATFORM.list_members(identity.tenant_id, identity.user_id)]}


@router.post("/invitations", status_code=201)
def invite(payload: InvitationCreate, identity=Depends(identidade_com_permissao("members.manage"))):
    try:
        invitation, token = PLATFORM.invite(identity.tenant_id, identity.user_id, payload.email, payload.role)
        return {**asdict(invitation), "invitation_token": token}
    except EntitlementError as exc:
        raise HTTPException(status_code=402, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/invitations/accept")
def accept_invitation(payload: InvitationAccept):
    identity = identity_for(payload.email)
    try:
        member = PLATFORM.accept_invitation(payload.token, identity.user_id, identity.email, payload.password)
        return {
            "access_token": emitir_token(identity.email, member.organization_id),
            "token_type": "bearer",
            "organization_id": member.organization_id,
        }
    except (AuthorizationError, ValueError):
        raise HTTPException(status_code=400, detail="O convite é inválido, expirou ou já foi utilizado.")


@router.patch("/members/{member_user_id}")
def update_member(member_user_id: str, payload: MemberRoleUpdate, identity=Depends(identidade_com_permissao("members.manage"))):
    try:
        return _member_view(PLATFORM.update_member_role(identity.tenant_id, identity.user_id, member_user_id, payload.role))
    except KeyError:
        raise HTTPException(status_code=404, detail="Membro não encontrado.")
    except AuthorizationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.delete("/members/{member_user_id}", status_code=204)
def remove_member(member_user_id: str, identity=Depends(identidade_com_permissao("members.manage"))):
    try:
        PLATFORM.remove_member(identity.tenant_id, identity.user_id, member_user_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Membro não encontrado.")
    except AuthorizationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/usage")
def usage(identity=Depends(identidade_com_permissao("usage.read"))):
    return PLATFORM.usage(identity.tenant_id, identity.user_id)


@router.get("/audit")
def audit(limit: int = Query(default=100, ge=1, le=500), identity=Depends(identidade_com_permissao("audit.read"))):
    return {
        "events": [asdict(item) for item in PLATFORM.audit(identity.tenant_id, identity.user_id, limit)],
        "chain_valid": PLATFORM.verify_audit_chain(identity.tenant_id),
    }
