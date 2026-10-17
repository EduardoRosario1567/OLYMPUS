"""Consolidation guard: static deliveries must not run in a temporary host directory."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi import HTTPException
from app.api import missions as mod


class StaticDeliverySafetyTests(unittest.TestCase):
    def test_static_request_is_rejected_before_mission_or_thread_creation(self):
        before = len(mod._MISSIONS)
        with patch.object(mod.threading, "Thread", side_effect=AssertionError("started thread")):
            with patch.object(mod.uuid, "uuid4", side_effect=AssertionError("created mission ID")):
                with self.assertRaises(HTTPException) as error:
                    mod.create_mission(mod.MissionCreate(
                        task="Crie o site Rosales Cafe", static_delivery=True
                    ))
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("BLOCKED", str(error.exception.detail))
        self.assertEqual(len(mod._MISSIONS), before)

    def test_default_mission_schema_retains_backwards_compatibility(self):
        request = mod.MissionCreate(task="Executar diagnostico")
        self.assertFalse(request.static_delivery)
        view = mod.MissionView(
            id="abc", task="Executar diagnostico", status="queued",
            created_at=1.0, updated_at=1.0, elapsed_seconds=0
        )
        self.assertFalse(view.delivery_available)

    def test_temporary_workspace_does_not_claim_os_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mod._seed_workspace(root)
            readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("OS-level isolation is NOT verified", readme)


if __name__ == "__main__":
    unittest.main()
