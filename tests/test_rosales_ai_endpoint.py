"""Rosales pilot authenticated API handler tests; Groq is mocked and never charged."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"backend"))

from app.api import cloud_projects
from app.core.tenancy import Identity
from fastapi import HTTPException
from olympus.cloud.project_workspace import ProjectWorkspaceManager
from olympus.cloud.project_templates import INDEX_HTML, STYLE_CSS, write_rosales_mvp


class TestRosalesAIApi(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.manager=ProjectWorkspaceManager(self.directory.name)
        self.project=self.manager.create("Rosales Café — MVP de validação", tenant_id="tenant-admin")
        write_rosales_mvp(self.manager.project_root(self.project.project_id,tenant_id="tenant-admin"))
        self.owner=Identity("user-admin","adm@olympus.com","tenant-admin")
        self.other=Identity("user-other","other@example.test","tenant-other")
        self.runtime=SimpleNamespace(data_dir=Path(self.directory.name),projects=self.manager,
            project_is_busy=lambda pid,tenant:False,
            versions=SimpleNamespace(capture=lambda *args,**kwargs:SimpleNamespace(version_id="backup-ok")))
        self.vars={"OLYMPUS_ENV":"staging","OLYMPUS_ROSALES_AI_PILOT":"1",
            "OLYMPUS_ADMIN_EMAIL":"adm@olympus.com","GROQ_API_KEY":"fake-key-for-test-only-not-valid-123456",
            "OLYMPUS_ROSALES_GROQ_MODEL":"test-model"}
        self.runtime_patch=patch.object(cloud_projects,"_RUNTIME",self.runtime)
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)
        self.env_patch=patch.dict(os.environ,self.vars)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def fail_with(self,code,identity=None,project=None):
        with self.assertRaises(HTTPException) as failure:
            cloud_projects.generate_rosales_pilot(project or self.project.project_id,identity=identity or self.owner)
        self.assertEqual(failure.exception.status_code,code)

    def test_disabled_and_other_tenant_are_denied_without_provider_call(self):
        with patch.object(cloud_projects,"generate_rosales_static") as provider:
            with patch.dict(os.environ,{"OLYMPUS_ROSALES_AI_PILOT":"0"}):
                self.fail_with(503)
            self.fail_with(403,identity=self.other)
            with patch.dict(os.environ,{"OLYMPUS_ENV":"production"}):
                self.fail_with(503)
            provider.assert_not_called()

    def test_missing_project_and_wrong_name_do_not_consume_credit(self):
        with patch.object(cloud_projects,"generate_rosales_static") as provider:
            self.fail_with(404,project="unknown-project")
            other=self.manager.create("Outro site",tenant_id="tenant-admin")
            write_rosales_mvp(self.manager.project_root(other.project_id,tenant_id="tenant-admin"))
            self.fail_with(409,project=other.project_id)
            provider.assert_not_called()

    def test_generated_files_backup_and_second_attempt_blocked(self):
        html=INDEX_HTML.replace('class="hero"', 'class="hero hero-ai"')
        css=STYLE_CSS+"\n/* static-output-test */"
        with patch.object(cloud_projects,"generate_rosales_static",return_value=(html,css)) as provider, \
             patch.object(cloud_projects.PLATFORM,"record_action"):
            result=cloud_projects.generate_rosales_pilot(self.project.project_id,identity=self.owner)
            self.assertEqual(result["status"],"completed")
            self.assertEqual(result["provider"],"groq")
            self.assertTrue(result["static_only"])
            self.assertEqual(result["backup_version_id"],"backup-ok")
            self.assertEqual(set(result["files"]),{"index.html","style.css"})
            self.fail_with(409)
            provider.assert_called_once()
        root=self.manager.project_root(self.project.project_id,tenant_id="tenant-admin")
        self.assertIn("hero-ai",(root/"index.html").read_text("utf-8"))
        self.assertIn("static-output-test",(root/"style.css").read_text("utf-8"))

    def test_provider_error_does_not_change_page(self):
        from olympus.cloud.rosales_ai import RosalesAIError
        with patch.object(cloud_projects,"generate_rosales_static",side_effect=RosalesAIError("failure")), \
             patch.object(cloud_projects.PLATFORM,"record_action"):
            self.fail_with(409)
        root=self.manager.project_root(self.project.project_id,tenant_id="tenant-admin")
        self.assertEqual((root/"index.html").read_text("utf-8"),INDEX_HTML)
        self.assertEqual((root/"style.css").read_text("utf-8"),STYLE_CSS)


if __name__=="__main__":
    unittest.main()
