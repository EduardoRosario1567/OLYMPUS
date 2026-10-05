import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class TestCloudAPIContract(unittest.TestCase):
    def test_cloud_routes_exist(self):
        try:
            from app.api.cloud_runtime import router
        except ImportError as exc:
            self.skipTest("backend dependencies unavailable: %s" % exc)
        paths = {route.path for route in router.routes}
        self.assertIn("/cloud/missions", {p.replace("/cloud", "/cloud") for p in paths})
        self.assertIn("/cloud/executions/{execution_id}", paths)
        self.assertIn("/cloud/executions/{execution_id}/events", paths)
        self.assertIn("/cloud/executions/{execution_id}/cancel", paths)
        self.assertIn("/cloud/executions/{execution_id}/resume", paths)


if __name__ == "__main__":
    unittest.main()
