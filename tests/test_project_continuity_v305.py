from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest

from olympus.cloud.project_catalog import ProjectCatalogError, remove_project, rename_project


ROOT = Path(__file__).resolve().parents[1]


def _catalog(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "projects": [
                    {"project_id": "p1", "tenant_id": "t1", "name": "Alpha", "created_at": 1.0, "updated_at": 1.0},
                    {"project_id": "p2", "tenant_id": "t1", "name": "Beta", "created_at": 2.0, "updated_at": 2.0},
                    {"project_id": "p1", "tenant_id": "t2", "name": "Outro tenant", "created_at": 3.0, "updated_at": 3.0},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_rename_preserves_other_projects_and_creates_backup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "projects.json"
        _catalog(path)
        updated = rename_project(path, "p1", "t1", "  Alpha Renomeado  ")
        assert updated["name"] == "Alpha Renomeado"
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["projects"]
        assert next(row for row in rows if row["project_id"] == "p1" and row["tenant_id"] == "t1")["name"] == "Alpha Renomeado"
        assert next(row for row in rows if row["project_id"] == "p1" and row["tenant_id"] == "t2")["name"] == "Outro tenant"
        assert list(path.parent.glob("projects.json.bak-v305-*"))


def test_remove_only_selected_project_and_tenant() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "projects.json"
        _catalog(path)
        removed = remove_project(path, "p1", "t1")
        assert removed["name"] == "Alpha"
        rows = json.loads(path.read_text(encoding="utf-8"))["projects"]
        assert not any(row["project_id"] == "p1" and row["tenant_id"] == "t1" for row in rows)
        assert any(row["project_id"] == "p1" and row["tenant_id"] == "t2" for row in rows)
        assert any(row["project_id"] == "p2" and row["tenant_id"] == "t1" for row in rows)


def test_invalid_rename_is_rejected_without_mutation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "projects.json"
        _catalog(path)
        before = path.read_text(encoding="utf-8")
        with pytest.raises(ProjectCatalogError):
            rename_project(path, "p1", "t1", "   ")
        assert path.read_text(encoding="utf-8") == before


def test_v305_frontend_contracts_are_present() -> None:
    sidebar = (ROOT / "frontend/components/layout/sidebar.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend/services/api.ts").read_text(encoding="utf-8")
    assert 'href={`/missao?project_id=${encodeURIComponent(project.project_id)}`}' in sidebar
    assert "Abrir / continuar" in sidebar
    assert "Renomear" in sidebar
    assert "Excluir" in sidebar
    assert "export function Brand" in sidebar
    assert "export function Sidebar" in sidebar
    assert "export function MobileNav" in sidebar
    mission = (ROOT / "frontend/app/missao/page.tsx").read_text(encoding="utf-8")
    assert "useSearchParams" in mission
    assert 'requestedProjectId = searchParams.get("project_id")' in mission
    assert "[pronto, requestedProjectId]" in mission
    assert "listarCloudExecucoes({ project_id: projectId, limit: 1 })" in mission
    assert "renomearCloudProjeto" in api
    assert "excluirCloudProjeto" in api
    assert "method: 'PATCH'" in api
    assert "method: 'DELETE'" in api


def test_v305_backend_routes_are_recoverable_and_busy_safe() -> None:
    source = (ROOT / "backend/app/api/cloud_runtime.py").read_text(encoding="utf-8")
    assert '@router.patch("/projects/{project_id}")' in source
    assert '@router.delete("/projects/{project_id}", status_code=204)' in source
    assert "project_is_busy" in source
    assert '"project-trash"' in source
    assert "project.renamed" in source
    assert "project.deleted" in source
