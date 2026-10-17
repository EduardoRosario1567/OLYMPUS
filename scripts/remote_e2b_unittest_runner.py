"""Optional, cost-gated E2B sandbox verification of agent-generated Python.

E2B runs remotely. This module does NOT prove full OS isolation, attest
provider integrity, run a web browser, or authorize paid usage automatically.
Only allowlisted files are uploaded. Never forward the host environment.
"""
import io
import os
import re
import zipfile
from pathlib import Path

MAX_FILES = 250
MAX_BYTES = 3_000_000
ALLOWED_ROOTS = frozenset({"tests", "app", "src", "olympus", "backend", "scripts"})
EXCLUDED_PARTS = frozenset({
    ".git", ".olympus", ".env", ".venv", "venv", "__pycache__",
    "node_modules", ".next", "dist", "build", "credentials", "secrets",
})
MODULE_RE = re.compile(r"tests(?:\.[A-Za-z_][A-Za-z_0-9]*)+")


def build_python_bundle(workspace):
    path = Path(workspace)
    if path.is_symlink():
        raise ValueError("BLOCKED: workspace symlink")
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("BLOCKED: workspace not a directory")

    entries = []
    total = 0
    for file in root.rglob("*"):
        rel = file.relative_to(root)
        parts = rel.parts
        if any(part.startswith(".") or part in EXCLUDED_PARTS for part in parts):
            continue
        if not parts or parts[0] not in ALLOWED_ROOTS:
            continue
        if file.is_symlink():
            raise ValueError("BLOCKED: symlink in sandbox source tree")
        if not file.is_file() or file.suffix != ".py":
            continue
        if any(word in file.stem.lower() for word in ("secret", "token", "credential", "password", "api_key")):
            continue
        size = file.stat().st_size
        total += size
        if total > MAX_BYTES or len(entries) >= MAX_FILES:
            raise ValueError("BLOCKED: remote sandbox transfer limit")
        entries.append((rel.as_posix(), file.read_bytes()))

    if not any(name.startswith("tests/") and name.endswith(".py") for name, _ in entries):
        raise ValueError("BLOCKED: no Python tests in workspace")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in sorted(entries):
            zf.writestr(name, data)
    return archive.getvalue()


def execute(workspace, module, timeout=60, environ=None):
    env = os.environ if environ is None else environ
    if not isinstance(module, str) or not MODULE_RE.fullmatch(module):
        raise ValueError("BLOCKED: invalid Python test module")
    if env.get("OLYMPUS_REMOTE_SANDBOX_AUTHORIZED") != "1":
        raise PermissionError("BLOCKED: remote sandbox usage not authorized")
    if not env.get("E2B_API_KEY"):
        raise RuntimeError("BLOCKED: E2B_API_KEY missing")
    if not 1 <= timeout <= 180:
        raise ValueError("BLOCKED: remote test timeout outside limits")

    bundle = build_python_bundle(workspace)
    try:
        from e2b import Sandbox
    except ImportError as exc:
        raise RuntimeError("BLOCKED: install optional 'e2b' Python SDK") from exc

    sandbox = None
    try:
        # SDK authentication uses E2B_API_KEY on the host. It is never copied
        # into sandbox envs or the uploaded zip.
        sandbox = Sandbox.create(
            timeout=timeout + 20,
            secure=True,
            allow_internet_access=False,
            envs={},
        )
        sandbox.files.write("/home/user/olympus-agent.zip", bundle)
        # The module name is restricted to dotted identifiers, not shell syntax.
        # Only fixed shell segments are used beyond that value.
        command = (
            "python3 -m zipfile -e /home/user/olympus-agent.zip /home/user/olympus-agent"
            " && cd /home/user/olympus-agent"
            " && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v " + module
        )
        result = sandbox.commands.run(command, timeout=timeout)
        out = str(result.stdout or "")[-6000:]
        err = str(result.stderr or "")[-6000:]
        tests = re.search(r"^Ran ([1-9][0-9]*) tests? in ", err, re.M)
        skipped = re.search(r"^OK \(skipped=([0-9]+)\)", err, re.M)
        executed = int(tests.group(1)) if tests else 0
        if skipped:
            executed -= int(skipped.group(1))
        okay = bool(re.search(r"^OK(?:\s|\(|$)", err, re.M))
        success = result.exit_code == 0 and executed > 0 and okay
        return {
            "status": "DONE" if success else "BLOCKED",
            "exit_code": result.exit_code if not success else 0,
            "stdout": out,
            "stderr": err,
            "sandbox_provider": "e2b",
            "sandbox_id": getattr(sandbox, "sandbox_id", None),
            "provider_real": True,
        }
    finally:
        if sandbox is not None:
            sandbox.kill()
