"""E2B web build adapter: upload curated files, build remotely, validate locally.

This module is opt-in infrastructure, not an AI agent or a public preview URL.
The returned artifact can be previewed using the existing private project preview
service once an authorized caller registers/copies its verified files.
"""
import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from scripts.preserve_static_delivery import preserve_validated_site

MAX_SOURCE_FILES = 250
MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_OUTPUT_BYTES = 24 * 1024 * 1024
MAX_OUTPUT_FILES = 150
SAFE_STATIC = frozenset({".html", ".css", ".js", ".json", ".svg", ".png", ".jpg",
                         ".jpeg", ".webp", ".gif", ".ico", ".txt", ".woff", ".woff2"})
SAFE_REACT = SAFE_STATIC | frozenset({".jsx", ".ts", ".tsx"})
REACT_ROOT_FILES = frozenset({"package.json", "package-lock.json", "index.html",
                               "vite.config.js", "vite.config.mjs", "vite.config.ts"})
BLOCKED = frozenset({".git", ".env", ".olympus", "node_modules", ".next",
                     ".venv", "dist", "build", "__pycache__", "attachments",
                     "imports", "credentials", "secrets"})


def source_bundle(workspace, mode):
    """Return a ZIP of only explicitly approved source files."""
    if mode not in ("static", "react"):
        raise ValueError("BLOCKED: invalid web build mode")
    path = Path(workspace)
    if path.is_symlink() or not path.resolve(strict=True).is_dir():
        raise ValueError("BLOCKED: invalid workspace")
    root = path.resolve()
    if mode == "static" and not (root / "site" / "index.html").is_file():
        raise ValueError("BLOCKED: static site/index.html required")
    if mode == "react":
        pkg = root / "package.json"
        lock = root / "package-lock.json"
        if not pkg.is_file() or not lock.is_file() or pkg.is_symlink() or lock.is_symlink():
            raise ValueError("BLOCKED: React requires package.json and package-lock.json")
        package = json.loads(pkg.read_text(encoding="utf-8"))
        if package.get("scripts", {}).get("build") != "vite build":
            raise ValueError("BLOCKED: only standard vite build script allowed")

    chosen = []
    total = 0
    for candidate in sorted(root.rglob("*")):
        rel = candidate.relative_to(root)
        parts = rel.parts
        if any(part.startswith(".") or part.lower() in BLOCKED for part in parts):
            continue
        allowed = (
            (mode == "static" and parts[0] == "site" and candidate.suffix.lower() in SAFE_STATIC)
            or (mode == "react" and (
                (len(parts) == 1 and parts[0] in REACT_ROOT_FILES)
                or (parts[0] in ("src", "public") and candidate.suffix.lower() in SAFE_REACT)
            ))
        )
        if not allowed:
            continue
        if candidate.is_symlink():
            raise ValueError("BLOCKED: source symlink")
        if not candidate.is_file():
            continue
        size = candidate.stat().st_size
        total += size
        if total > MAX_SOURCE_BYTES or len(chosen) >= MAX_SOURCE_FILES:
            raise ValueError("BLOCKED: source transfer limit exceeded")
        chosen.append((rel.as_posix(), candidate.read_bytes()))
    if not chosen:
        raise ValueError("BLOCKED: empty source bundle")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel, content in chosen:
            archive.writestr(rel, content)
    return output.getvalue()


def _extract_verified_output(payload, destination):
    """Copy downloaded build files into a fresh staging area, never trust ZIP paths."""
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError("BLOCKED: remote build archive too large")
    count = total = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_OUTPUT_FILES + 1:
            raise ValueError("BLOCKED: too many remote build files")
        for item in infos:
            name = item.filename
            rel = PurePosixPath(name)
            if not name.startswith("site/") or rel.is_absolute() or ".." in rel.parts:
                raise ValueError("BLOCKED: unsafe build archive path")
            if item.is_dir():
                continue
            if len(rel.parts) < 2 or rel.suffix.lower() not in SAFE_STATIC:
                raise ValueError("BLOCKED: unexpected remote output file")
            if item.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError("BLOCKED: output symlink")
            count += 1
            total += item.file_size
            if count > MAX_OUTPUT_FILES or total > MAX_OUTPUT_BYTES or item.file_size > 8 * 1024 * 1024:
                raise ValueError("BLOCKED: remote output exceeds limits")
            target = Path(destination).joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as stream, target.open("xb") as file:
                import shutil
                shutil.copyfileobj(stream, file, length=64 * 1024)
    if count == 0:
        raise ValueError("BLOCKED: remote build returned no files")


def build_and_preserve(workspace, mode, delivery_root, mission_id, environ=None,
                       sandbox_factory=None):
    """Remote E2B build, local deterministic verification, then private preservation.

    Returns BUILD_VERIFIED (not mission DONE); model and browser evidence are separate.
    No untrusted generated code executes on the host.
    """
    env = os.environ if environ is None else environ
    if env.get("OLYMPUS_REMOTE_SANDBOX_AUTHORIZED") != "1":
        raise PermissionError("BLOCKED: remote sandbox expense not authorized")
    if not env.get("E2B_API_KEY"):
        raise RuntimeError("BLOCKED: E2B_API_KEY unavailable")
    if mode == "react" and env.get("OLYMPUS_REMOTE_BUILD_NETWORK_AUTHORIZED") != "1":
        raise PermissionError("BLOCKED: React dependency network usage not authorized")
    bundle = source_bundle(workspace, mode)
    if sandbox_factory is None:
        try:
            from e2b import Sandbox
        except ImportError as exc:
            raise RuntimeError("BLOCKED: E2B SDK not installed") from exc
        sandbox_factory = Sandbox.create

    sandbox = sandbox_factory(
        timeout=300, api_key=env["E2B_API_KEY"], envs={},
        allow_internet_access=mode == "react",
        network={"allow_public_traffic": False},
    )
    try:
        sandbox.files.write("/home/user/olympus-source.zip", bundle)
        commands = [
            "mkdir -p /home/user/olympus-work",
            "python3 -m zipfile -e /home/user/olympus-source.zip /home/user/olympus-work",
        ]
        if mode == "react":
            commands.extend((
                "cd /home/user/olympus-work && npm ci --ignore-scripts --no-audit --no-fund",
                "cd /home/user/olympus-work && npm run build -- --outDir site",
            ))
        commands.append(
            "cd /home/user/olympus-work && python3 -m zipfile -c /home/user/olympus-output.zip site"
        )
        for command in commands:
            result = sandbox.commands.run(command, timeout=240)
            if result.exit_code != 0:
                raise RuntimeError("BLOCKED: remote build command failed: " +
                                   str(result.stderr or "")[-600:])
        payload = bytes(sandbox.files.read("/home/user/olympus-output.zip", format="bytes"))
        with tempfile.TemporaryDirectory(prefix="olympus-web-build-") as stage:
            _extract_verified_output(payload, stage)
            artifact = preserve_validated_site(stage, delivery_root, mission_id)
        return {"status": "BUILD_VERIFIED", "artifact": artifact, "provider": "e2b",
                "model_inference_verified": False, "browser_verified": False}
    finally:
        sandbox.kill()
