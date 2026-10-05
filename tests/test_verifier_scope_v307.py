from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "tools" / "patch_verifier_identity.py"
spec = importlib.util.spec_from_file_location("patch_verifier_identity", PATCHER)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def test_legacy_identity_gate_is_neutralized_without_breaking_block():
    src = '''def check(task, html):\n    errors = []\n    if "olympus" in task.lower() and "olympus" not in html.lower():\n        errors.append("include the requested Olympus identity")\n    return errors\n'''
    patched, changed = module.patch_text(src)
    assert changed
    assert "legacy global Olympus identity gate disabled" in patched
    assert 'errors.append("include the requested Olympus identity")' not in patched
    compile(patched, "<fixture>", "exec")
    ns = {}
    exec(compile(patched, "<fixture>", "exec"), ns)
    assert ns["check"]("Use skills available in OLYMPUS to build Rosales Café", "Rosales Café") == []


def test_patcher_is_idempotent():
    src = '''def check(task):\n    errors=[]\n    if True:\n        errors.append("include the requested Olympus identity")\n    return errors\n'''
    once, changed = module.patch_text(src)
    assert changed
    twice, changed_again = module.patch_text(once)
    assert not changed_again
    assert once == twice
