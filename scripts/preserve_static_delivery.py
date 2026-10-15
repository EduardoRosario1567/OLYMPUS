"""Persist only validated static mission outputs. Never execute delivered files."""
import os
import shutil
import tempfile
from pathlib import Path

from scripts.verificar_entrega_estatica import verify


def preserve_validated_site(workspace, destination_root, mission_id):
    """Copy workspace/site to an immutable-ish private delivery folder.

    Caller must provide a trusted, server-generated mission ID and private root.
    This is file validation, NOT OS-level process isolation.
    """
    if not mission_id or not mission_id.isascii() or not all(c.isalnum() or c in "-_" for c in mission_id):
        raise ValueError("invalid mission ID")
    source = Path(workspace) / "site"
    workspace_root = Path(workspace).resolve()
    if source.is_symlink() or source.resolve().parent != workspace_root:
        raise ValueError("invalid site directory")
    issues, count = verify(str(source), str(workspace_root))
    if issues:
        raise ValueError("BLOCKED: " + "; ".join(issues))
    root = Path(destination_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / mission_id
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("mission delivery already exists")
    staging = Path(tempfile.mkdtemp(prefix=".olympus-delivery-", dir=root))
    try:
        # A fresh tree prevents untrusted workspace metadata from being carried over.
        shutil.copytree(source, staging / "site", symlinks=False)
        post_issues, post_count = verify(str(staging / "site"), str(root))
        if post_issues or post_count != count:
            raise ValueError("BLOCKED: copied artifact failed validation")
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"status": "DONE", "path": str(destination / "site"), "files": count}
