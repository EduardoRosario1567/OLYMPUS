import os
import importlib.util
import sys
import time
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
BACKEND = os.path.join(ROOT, "backend")
os.environ["OLYMPUS_ENABLE_LEGACY_API"] = "1"
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

if not all(importlib.util.find_spec(name) for name in ("fastapi", "jwt")):
    raise unittest.SkipTest("FastAPI/PyJWT are optional HTTP-runtime dependencies")

from fastapi.testclient import TestClient
from app.main import app
from app.api.providers import _can_read
from app.core.tenancy import identity_for


class TestWebRuntimeAPI(unittest.TestCase):
    def setUp(self):
        # Provider diagnostics are protected like the rest of the provider
        # surface; exercise the route as the authenticated frontend does.
        app.dependency_overrides[_can_read] = lambda: identity_for("test@olympus.local")
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.pop(_can_read, None)

    def test_create_and_read_mission(self):
        with patch("app.api.missions._run_mission", lambda mission_id: None):
            response = self.client.post("/missions", json={"task": "Create a small helper"})
        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], "queued")
        fetched = self.client.get("/missions/%s" % data["id"])
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["task"], "Create a small helper")

    def test_unknown_mission_is_404(self):
        self.assertEqual(self.client.get("/missions/missing").status_code, 404)

    def test_events_endpoint(self):
        with patch("app.api.missions._run_mission", lambda mission_id: None):
            data = self.client.post("/missions", json={"task": "Test mission events"}).json()
        response = self.client.get("/missions/%s/events" % data["id"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["events"], [])

    def test_provider_health_never_raises(self):
        response = self.client.get("/providers/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["providers"][0]["id"], "omniroute")


if __name__ == "__main__":
    unittest.main()
