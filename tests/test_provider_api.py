import unittest
import importlib.util

class TestModelLabAPI(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is an optional HTTP-runtime dependency")
    def test_model_lab_endpoint_exists(self):
        from backend.app.api import providers as api
        paths = {route.path for route in api.router.routes}
        self.assertIn('/providers/models/lab', paths)
