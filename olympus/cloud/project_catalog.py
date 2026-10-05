from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import os
import shutil
import tempfile
import time
import uuid
from typing import Any, Dict, Optional, Tuple, Union


class ProjectCatalogError(RuntimeError):
    pass


def _matches(record: Any, project_id: str, tenant_id: str) -> bool:
    if not isinstance(record, dict):
        return False
    if str(record.get("project_id", "")) != str(project_id):
        return False
    record_tenant = str(record.get("tenant_id", tenant_id) or tenant_id)
    return record_tenant == str(tenant_id)


def _find_record(node: Any, project_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    if _matches(node, project_id, tenant_id):
        return node
    if isinstance(node, dict):
        for value in node.values():
            found = _find_record(value, project_id, tenant_id)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_record(value, project_id, tenant_id)
            if found is not None:
                return found
    return None


def _delete_record(node: Any, project_id: str, tenant_id: str) -> Tuple[Any, bool]:
    if isinstance(node, list):
        changed = False
        output = []
        for value in node:
            if _matches(value, project_id, tenant_id):
                changed = True
                continue
            new_value, child_changed = _delete_record(value, project_id, tenant_id)
            output.append(new_value)
            changed = changed or child_changed
        return output, changed

    if isinstance(node, dict):
        output = {}
        changed = False
        for key, value in node.items():
            if str(key) == str(project_id) and _matches(value, project_id, tenant_id):
                changed = True
                continue
            if _matches(value, project_id, tenant_id):
                changed = True
                continue
            new_value, child_changed = _delete_record(value, project_id, tenant_id)
            output[key] = new_value
            changed = changed or child_changed
        return output, changed

    return node, False


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectCatalogError("Catálogo de projetos não encontrado.") from exc
    except (OSError, ValueError, TypeError) as exc:
        raise ProjectCatalogError("Catálogo de projetos inválido.") from exc


def _atomic_write(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak-v305-{stamp}-{uuid.uuid4().hex}")
    if path.exists():
        shutil.copy2(path, backup)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
    return backup


def rename_project(path: Union[str, Path], project_id: str, tenant_id: str, new_name: str) -> Dict[str, Any]:
    clean_name = " ".join(str(new_name or "").strip().split())
    if not clean_name:
        raise ProjectCatalogError("Informe um nome para o projeto.")
    if len(clean_name) > 160:
        raise ProjectCatalogError("O nome do projeto deve ter no máximo 160 caracteres.")

    catalog_path = Path(path)
    data = _load(catalog_path)
    updated = deepcopy(data)
    record = _find_record(updated, project_id, tenant_id)
    if record is None:
        raise ProjectCatalogError("Projeto não encontrado.")
    record["name"] = clean_name
    record["updated_at"] = time.time()
    _atomic_write(catalog_path, updated)
    return dict(record)


def remove_project(path: Union[str, Path], project_id: str, tenant_id: str) -> Dict[str, Any]:
    catalog_path = Path(path)
    data = _load(catalog_path)
    current = _find_record(data, project_id, tenant_id)
    if current is None:
        raise ProjectCatalogError("Projeto não encontrado.")
    updated, changed = _delete_record(deepcopy(data), project_id, tenant_id)
    if not changed:
        raise ProjectCatalogError("Projeto não encontrado.")
    _atomic_write(catalog_path, updated)
    return dict(current)
