import os
import sys
import unittest

ROOT=os.path.dirname(os.path.dirname(__file__))
BACKEND=os.path.join(ROOT,'backend')
if BACKEND not in sys.path:
    sys.path.insert(0,BACKEND)


class TestCloudProjectsAPI(unittest.TestCase):
    def test_project_routes_exist(self):
        try:
            from app.api.cloud_projects import router
        except ImportError as exc:
            self.skipTest("backend dependencies unavailable: %s" % exc)
        paths={route.path for route in router.routes}
        self.assertIn('/cloud/projects', paths)
        self.assertIn('/cloud/projects/{project_id}', paths)
        self.assertIn('/cloud/projects/{project_id}/attachments', paths)
        self.assertIn('/cloud/projects/{project_id}/attachments/{attachment_id}', paths)
        self.assertIn('/cloud/projects/{project_id}/versions', paths)
        self.assertIn('/cloud/projects/{project_id}/versions/{version_id}/compare', paths)
        self.assertIn('/cloud/projects/{project_id}/versions/{version_id}/restore', paths)
        self.assertIn('/cloud/projects/{project_id}/preview-session', paths)
        self.assertIn('/cloud/projects/_preview/{token}/{asset_path:path}', paths)

    def test_github_routes_exist(self):
        try:
            from app.api.github import router
        except ImportError as exc:
            self.skipTest("backend dependencies unavailable: %s" % exc)
        paths={route.path for route in router.routes}
        for path in (
            '/cloud/github/connection',
            '/cloud/github/repositories',
            '/cloud/github/projects/{project_id}',
            '/cloud/github/projects/{project_id}/repository',
            '/cloud/github/projects/{project_id}/branches',
            '/cloud/github/projects/{project_id}/sync',
            '/cloud/github/projects/{project_id}/commits',
            '/cloud/github/projects/{project_id}/publish',
            '/cloud/github/projects/{project_id}/publication',
        ):
            self.assertIn(path, paths)

    def test_runner_routes_exist(self):
        try:
            from app.api.runner import router
        except ImportError as exc:
            self.skipTest("backend dependencies unavailable: %s" % exc)
        paths={route.path for route in router.routes}
        for path in (
            '/cloud/runner/enrollments',
            '/cloud/runner/activate',
            '/cloud/runner/token',
            '/cloud/runner/session',
            '/cloud/runner/releases/latest',
            '/cloud/runner/installations',
            '/cloud/runner/installations/{installation_id}',
        ):
            self.assertIn(path, paths)

    def test_railway_routes_exist(self):
        try:
            from app.api.railway import router
        except ImportError as exc:
            self.skipTest("backend dependencies unavailable: %s" % exc)
        paths={route.path for route in router.routes}
        for path in (
            '/cloud/railway/connection',
            '/cloud/railway/projects/{project_id}',
            '/cloud/railway/projects/{project_id}/service',
            '/cloud/railway/projects/{project_id}/secrets',
            '/cloud/railway/projects/{project_id}/secrets/{name}',
            '/cloud/railway/projects/{project_id}/deployments',
            '/cloud/railway/projects/{project_id}/rollback',
            '/cloud/railway/projects/{project_id}/domain',
        ):
            self.assertIn(path, paths)


if __name__ == '__main__':
    unittest.main()
