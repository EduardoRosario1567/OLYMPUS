import importlib.util
from pathlib import Path
import sys
import unittest


ROOT=Path(__file__).resolve().parents[1]
BACKEND=ROOT/"backend"
if str(BACKEND) not in sys.path: sys.path.insert(0,str(BACKEND))


class SkillsApiV230Tests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("fastapi"),"FastAPI is optional")
    def test_catalog_import_approval_and_disable_routes_exist(self):
        from app.api.skills import router
        routes={(route.path,tuple(sorted(route.methods or ()))) for route in router.routes}
        paths={path for path,_methods in routes}
        self.assertIn("/skills",paths)
        self.assertIn("/skills/imports/github",paths)
        self.assertIn("/skills/{skill_id}/approve",paths)
        self.assertIn("/skills/{skill_id}",paths)


if __name__ == "__main__": unittest.main()
