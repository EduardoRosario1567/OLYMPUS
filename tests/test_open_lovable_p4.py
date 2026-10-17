"""P4 HTTP security contract: real Olympus JWT/RBAC with isolated test databases.

Every request exercises the actual FastAPI dependencies, not override stubs.
Does not contact providers, start sandboxes or require a Mac.
"""
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import deps, security
from app.core.tenancy import identity_for
from app.core.open_lovable_p4_store import ReservationStore, ReservationConflict, ReservationMissing
from app.api import open_lovable_p4, cloud_runtime
from olympus.saas.platform import SaaSPlatform
from olympus.cloud.project_workspace import ProjectWorkspaceManager


class OpenLovableP4HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.platform = SaaSPlatform(cls.root / "saas.sqlite3")
        cls.projects = ProjectWorkspaceManager(str(cls.root / "projects"))
        cls.env = patch.dict(os.environ, {
            "OLYMPUS_OPEN_LOVABLE_P4": "1",
            "OLYMPUS_ENV": "development",
            "OLYMPUS_DB_BACKEND": "sqlite",
            "OLYMPUS_OPEN_LOVABLE_P4_DB": str(cls.root / "reservations.sqlite3"),
        })
        cls.env.start()
        cls.sec_platform = patch.object(security, "PLATFORM", cls.platform)
        cls.dep_platform = patch.object(deps, "PLATFORM", cls.platform)
        cls.project_get = patch.object(cloud_runtime._RUNTIME.projects, "get", side_effect=cls.projects.get)
        cls.sec_platform.start()
        cls.dep_platform.start()
        cls.project_get.start()
        cls.owner = identity_for("p4.owner@example.net")
        cls.other = identity_for("p4.outside@example.net")
        cls.builder = identity_for("p4.builder@example.net")
        cls.viewer = identity_for("p4.viewer@example.net")
        for ident in (cls.owner, cls.other):
            cls.platform.bootstrap_owner(ident.user_id, ident.email, ident.tenant_id)
        for ident, role in ((cls.builder, "builder"), (cls.viewer, "viewer")):
            _, invitation_token = cls.platform.invite(
                cls.owner.tenant_id, cls.owner.user_id, ident.email, role)
            cls.platform.accept_invitation(
                invitation_token, ident.user_id, ident.email, "p4-test-password-only")
        cls.projects.create("Owner", "p4-owner-project", tenant_id=cls.owner.tenant_id)
        cls.projects.create("Second owner", "p4-owner-project-2", tenant_id=cls.owner.tenant_id)
        cls.projects.create("Other", "p4-other-project", tenant_id=cls.other.tenant_id)
        cls.app = FastAPI()
        cls.app.include_router(open_lovable_p4.router)
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.project_get.stop()
        cls.dep_platform.stop()
        cls.sec_platform.stop()
        cls.env.stop()
        cls.tmp.cleanup()

    @classmethod
    def headers(cls, ident, organization=None):
        token = security.emitir_token(ident.email, organization or ident.tenant_id)
        return {"Authorization": "Bearer " + token}

    def new_request(self, project="p4-owner-project"):
        return {
            "project_id": project,
            "client_request_id": "p4_" + uuid.uuid4().hex,
        }

    def test_real_owner_jwt_reserves_policy_only(self):
        response = self.client.post("/cloud/open-lovable/reservations",
                                    json=self.new_request(), headers=self.headers(self.owner))
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertEqual(result["status"], "RESERVED_POLICY_ONLY")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["sandbox_id"], None)
        self.assertFalse(result["runtime_started"])
        self.assertFalse(result["delivery_available"])

    def test_missing_and_invalid_jwt_are_rejected(self):
        path = "/cloud/open-lovable/reservations"
        req = self.new_request()
        self.assertEqual(self.client.post(path, json=req).status_code, 401)
        self.assertEqual(self.client.post(path, json=req,
            headers={"Authorization":"Bearer forged"}).status_code, 401)

    def test_builder_can_reserve_but_viewer_cannot(self):
        req = self.new_request()
        self.assertEqual(self.client.post("/cloud/open-lovable/reservations", json=req,
            headers=self.headers(self.builder, self.owner.tenant_id)).status_code, 201)
        self.assertEqual(self.client.post("/cloud/open-lovable/reservations", json=self.new_request(),
            headers=self.headers(self.viewer, self.owner.tenant_id)).status_code, 403)

    def test_viewer_can_read_status_but_cannot_execute(self):
        self.assertEqual(self.client.get("/cloud/open-lovable/status",
            headers=self.headers(self.viewer, self.owner.tenant_id)).status_code, 200)
        self.assertEqual(self.client.get("/cloud/open-lovable/status").status_code, 401)

    def test_member_same_tenant_cannot_read_other_members_reservation(self):
        result = self.client.post("/cloud/open-lovable/reservations", json=self.new_request(),
            headers=self.headers(self.owner)).json()
        url = "/cloud/open-lovable/reservations/" + result["reservation_id"]
        own = self.client.get(url, headers=self.headers(self.owner))
        self.assertEqual(own.status_code, 200)
        self.assertEqual(self.client.get(url, headers=self.headers(self.builder,
            self.owner.tenant_id)).status_code, 404)
        self.assertEqual(self.client.post(url+"/block", headers=self.headers(self.builder,
            self.owner.tenant_id)).status_code, 404)

    def test_other_tenant_cannot_read_or_use_project(self):
        result = self.client.post("/cloud/open-lovable/reservations", json=self.new_request(),
            headers=self.headers(self.owner)).json()
        url = "/cloud/open-lovable/reservations/" + result["reservation_id"]
        self.assertEqual(self.client.get(url, headers=self.headers(self.other)).status_code, 404)
        self.assertEqual(self.client.post("/cloud/open-lovable/reservations",
            json=self.new_request("p4-owner-project"),
            headers=self.headers(self.other)).status_code, 404)
        self.assertEqual(self.client.post("/cloud/open-lovable/reservations",
            json=self.new_request("p4-other-project"),
            headers=self.headers(self.owner)).status_code, 404)

    def test_non_member_token_for_another_organization_is_rejected(self):
        self.assertEqual(self.client.post("/cloud/open-lovable/reservations",json=self.new_request(),
            headers=self.headers(self.other, self.owner.tenant_id)).status_code, 401)

    def test_replay_returns_same_reservation(self):
        req = self.new_request()
        url = "/cloud/open-lovable/reservations"
        a = self.client.post(url,json=req,headers=self.headers(self.owner))
        b = self.client.post(url,json=req,headers=self.headers(self.owner))
        self.assertEqual(a.status_code,201)
        self.assertEqual(b.status_code,201)
        self.assertEqual(a.json()["reservation_id"],b.json()["reservation_id"])

    def test_replay_for_different_project_is_rejected(self):
        req = self.new_request()
        url="/cloud/open-lovable/reservations"
        a=self.client.post(url,json=req,headers=self.headers(self.owner))
        self.assertEqual(a.status_code,201)
        req["project_id"]="p4-owner-project-2"
        self.assertEqual(self.client.post(url,json=req,
            headers=self.headers(self.owner)).status_code,409)

    def test_block_is_idempotent_and_inference_never_executes(self):
        a=self.client.post("/cloud/open-lovable/reservations",
            json=self.new_request(),headers=self.headers(self.owner)).json()
        url="/cloud/open-lovable/reservations/"+a["reservation_id"]
        self.assertEqual(self.client.post(url+"/execute",headers=self.headers(self.owner)).status_code,503)
        self.assertEqual(self.client.post(url+"/execute",headers=self.headers(self.other)).status_code,404)
        self.assertEqual(self.client.post(url+"/block",headers=self.headers(self.owner)).json()["status"],"BLOCKED")
        self.assertEqual(self.client.post(url+"/block",headers=self.headers(self.owner)).json()["status"],"BLOCKED")
        self.assertEqual(self.client.post(url+"/execute",headers=self.headers(self.owner)).status_code,503)

    def test_invalid_project_has_same_shape_as_other_tenant(self):
        self.assertEqual(self.client.post("/cloud/open-lovable/reservations",
            json=self.new_request("does-not-exist"), headers=self.headers(self.owner)).status_code, 404)

    def test_lab_feature_disabled_rejects_execution_and_status(self):
        with patch.dict(os.environ, {"OLYMPUS_OPEN_LOVABLE_P4":"0"}):
            self.assertEqual(self.client.get("/cloud/open-lovable/status",
                headers=self.headers(self.owner)).status_code,503)
            self.assertEqual(self.client.post("/cloud/open-lovable/reservations",
                json=self.new_request(),headers=self.headers(self.owner)).status_code,503)

    def test_production_and_postgres_prohibited(self):
        for key,value in (("OLYMPUS_ENV","production"),("OLYMPUS_DB_BACKEND","postgres")):
            with patch.dict(os.environ,{key:value}):
                self.assertEqual(self.client.get("/cloud/open-lovable/status",
                    headers=self.headers(self.owner)).status_code,503)

    def test_store_persists_without_disclosing_other_owner_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"p4.sqlite3"
            one=ReservationStore(path)
            stored=one.create(tenant_id="tnt_a",actor_id="usr_a",
                project_id="project",client_request_id="request-abcd-0123456789")
            second=ReservationStore(path)
            self.assertEqual(stored["reservation_id"],
                second.owner_view(reservation_id=stored["reservation_id"],
                                  tenant_id="tnt_a",actor_id="usr_a")["reservation_id"])
            with self.assertRaises(ReservationMissing):
                second.owner_view(reservation_id=stored["reservation_id"],
                                  tenant_id="tnt_a",actor_id="usr_b")
            with self.assertRaises(ReservationMissing):
                second.owner_view(reservation_id=stored["reservation_id"],
                                  tenant_id="tnt_b",actor_id="usr_a")

    def test_request_validation_and_no_model_routes(self):
        self.assertEqual(self.client.post("/cloud/open-lovable/reservations",
            json={"project_id":"p4-owner-project","client_request_id":"bad!"},
            headers=self.headers(self.owner)).status_code,422)
        paths={getattr(route, 'path', None) for route in self.app.routes}
        self.assertNotIn("/cloud/open-lovable/proxy",paths)
        self.assertNotIn("/cloud/open-lovable/inference",paths)

if __name__ == "__main__":
    unittest.main()
