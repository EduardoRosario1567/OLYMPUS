import os
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

class TestAuthTenant(unittest.TestCase):
    def setUp(self):
        os.environ["OLYMPUS_ADMIN_EMAIL"] = "admin@olympus.local"
        os.environ["OLYMPUS_ADMIN_SENHA"] = "secret"
        os.environ["OLYMPUS_JWT_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"

    def tearDown(self):
        for key in ("OLYMPUS_ADMIN_EMAIL", "OLYMPUS_ADMIN_SENHA", "OLYMPUS_JWT_SECRET"):
            os.environ.pop(key, None)

    @unittest.skipUnless(importlib.util.find_spec("jwt"), "PyJWT is an optional HTTP-runtime dependency")
    def test_token_contains_stable_identity_and_tenant(self):
        from app.core.security import autenticar, validar_identity
        token = autenticar("admin@olympus.local", "secret")
        identity = validar_identity(token)
        self.assertIsNotNone(identity)
        self.assertTrue(identity.user_id.startswith("usr_"))
        self.assertTrue(identity.tenant_id.startswith("tnt_"))

    def test_tenant_is_different_for_different_identity(self):
        from app.core.tenancy import identity_for
        self.assertNotEqual(identity_for("a@example.com").tenant_id, identity_for("b@example.com").tenant_id)

    def test_project_isolation_by_tenant(self):
        from olympus.cloud.project_workspace import ProjectWorkspaceManager
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ProjectWorkspaceManager(tmp)
            a = mgr.create("A", "same-id", tenant_id="tenant-a")
            self.assertEqual(a.tenant_id, "tenant-a")
            with self.assertRaises(ValueError):
                mgr.create("A2", "same-id", tenant_id="tenant-b")
            with self.assertRaises(KeyError):
                mgr.execution_workspace("same-id", "exec", tenant_id="tenant-b")
            self.assertTrue(mgr.execution_workspace("same-id", "exec", tenant_id="tenant-a").is_dir())

    def test_project_list_is_tenant_scoped(self):
        from olympus.cloud.project_workspace import ProjectWorkspaceManager
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ProjectWorkspaceManager(tmp)
            mgr.create("A", "a", tenant_id="tenant-a")
            mgr.create("B", "b", tenant_id="tenant-b")
            self.assertEqual([p.project_id for p in mgr.list(tenant_id="tenant-a")], ["a"])
            self.assertEqual([p.project_id for p in mgr.list(tenant_id="tenant-b")], ["b"])

if __name__ == "__main__":
    unittest.main()
