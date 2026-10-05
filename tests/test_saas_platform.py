import sqlite3
import tempfile
import unittest
from pathlib import Path

from olympus.saas.billing import BillingEventReceiver, BillingVerificationError
from olympus.saas.platform import AuthorizationError, BillingEvent, SaaSPlatform


class SaaSPlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "platform.sqlite3"
        self.platform = SaaSPlatform(self.db)
        self.owner = self.platform.bootstrap_owner("usr_owner", "owner@example.com", "org_main", "Acme")

    def tearDown(self):
        self.temp.cleanup()

    def test_bootstrap_is_idempotent_and_owner_has_all_permissions(self):
        again = self.platform.bootstrap_owner("usr_owner", "owner@example.com", "org_main", "Changed")
        self.assertEqual(again.organization_id, self.owner.organization_id)
        self.assertEqual(self.platform.member_count("org_main"), 1)
        self.assertEqual(self.platform.authorize("org_main", "usr_owner", "billing.manage"), "owner")

    def test_invitation_is_one_time_and_persists_only_digest(self):
        invitation, token = self.platform.invite("org_main", "usr_owner", "builder@example.com", "builder")
        member = self.platform.accept_invitation(token, "usr_builder", "builder@example.com", "very-safe-password")
        self.assertEqual(member.role, "builder")
        with self.assertRaises(AuthorizationError):
            self.platform.accept_invitation(token, "usr_builder", "builder@example.com", "very-safe-password")
        with sqlite3.connect(self.db) as connection:
            stored = connection.execute("SELECT token_digest FROM invitations WHERE invitation_id=?", (invitation.invitation_id,)).fetchone()[0]
        self.assertNotEqual(stored, token)
        self.assertNotIn(token, self.db.read_bytes().decode("latin1"))

    def test_invitation_rejects_wrong_email_and_expired_token(self):
        _, token = self.platform.invite("org_main", "usr_owner", "viewer@example.com", "viewer")
        with self.assertRaises(AuthorizationError):
            self.platform.accept_invitation(token, "usr_wrong", "wrong@example.com", "very-safe-password")
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE invitations SET expires_at=0")
        with self.assertRaises(AuthorizationError):
            self.platform.accept_invitation(token, "usr_viewer", "viewer@example.com", "very-safe-password")

    def test_role_matrix_blocks_viewer_writes(self):
        _, token = self.platform.invite("org_main", "usr_owner", "viewer@example.com", "viewer")
        self.platform.accept_invitation(token, "usr_viewer", "viewer@example.com", "very-safe-password")
        self.assertEqual(self.platform.authorize("org_main", "usr_viewer", "projects.read"), "viewer")
        with self.assertRaises(AuthorizationError):
            self.platform.authorize("org_main", "usr_viewer", "projects.write")
        with self.assertRaises(AuthorizationError):
            self.platform.authorize("other_org", "usr_viewer", "projects.read")

    def test_owner_cannot_be_demoted_or_removed(self):
        with self.assertRaises(AuthorizationError):
            self.platform.update_member_role("org_main", "usr_owner", "usr_owner", "viewer")
        with self.assertRaises(AuthorizationError):
            self.platform.remove_member("org_main", "usr_owner", "usr_owner")

    def test_member_can_authenticate_and_switch_between_organizations(self):
        _, token = self.platform.invite("org_main", "usr_owner", "admin@example.com", "admin")
        self.platform.accept_invitation(token, "usr_admin", "admin@example.com", "very-safe-password")
        self.platform.create_organization("usr_admin", "admin@example.com", "Second")
        account = self.platform.authenticate("admin@example.com", "very-safe-password")
        self.assertEqual(account, ("usr_admin", "org_main"))
        self.assertEqual(len(self.platform.organizations_for("usr_admin")), 2)

    def test_usage_is_transactional_and_scoped_by_period(self):
        self.assertEqual(self.platform.consume("org_main", "usr_owner", "missions_month", 2, "2026-09"), 2)
        self.assertEqual(self.platform.consume("org_main", "usr_owner", "missions_month", 3, "2026-09"), 5)
        self.assertEqual(self.platform.usage("org_main", "usr_owner", "2026-09")["usage"]["missions_month"], 5)
        self.assertEqual(self.platform.usage("org_main", "usr_owner", "2026-10")["usage"], {})
        self.assertEqual(self.platform.refund("org_main", "usr_owner", "missions_month", 2, "2026-09"), 3)

    def test_audit_and_members_are_isolated_between_organizations(self):
        other = self.platform.create_organization("usr_other", "other@example.com", "Other")
        with self.assertRaises(AuthorizationError):
            self.platform.list_members(other.organization_id, "usr_owner")
        with self.assertRaises(AuthorizationError):
            self.platform.audit(other.organization_id, "usr_owner")

    def test_raw_database_contains_neither_password_nor_invitation_token(self):
        _, token = self.platform.invite("org_main", "usr_owner", "safe@example.com", "builder")
        password = "a-password-that-must-not-leak"
        self.platform.accept_invitation(token, "usr_safe", "safe@example.com", password)
        raw = self.db.read_bytes().decode("latin1")
        self.assertNotIn(token, raw)
        self.assertNotIn(password, raw)

    def test_billing_event_is_idempotent_and_updates_entitlements(self):
        event = BillingEvent("testpay", "evt_1", "org_main", "professional", "active", "cus_1", "sub_1")
        self.assertTrue(self.platform.apply_verified_billing_event(event))
        self.assertFalse(self.platform.apply_verified_billing_event(event))
        self.assertEqual(self.platform.entitlements("org_main")["plan_id"], "professional")

    def test_starter_member_limit_is_enforced_before_invitation(self):
        self.platform.apply_verified_billing_event(BillingEvent("testpay", "evt_starter", "org_main", "starter", "active"))
        with self.assertRaisesRegex(RuntimeError, "plan limit"):
            self.platform.invite("org_main", "usr_owner", "second@example.com", "viewer")

    def test_invalid_billing_organization_rolls_back_event(self):
        with self.assertRaises(KeyError):
            self.platform.apply_verified_billing_event(BillingEvent("testpay", "evt_missing", "org_missing", "professional", "active"))
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM billing_events WHERE event_id='evt_missing'").fetchone()[0], 0)

    def test_blank_organization_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.platform.create_organization("usr_owner", "owner@example.com", "   ")

    def test_audit_chain_detects_tampering(self):
        self.platform.invite("org_main", "usr_owner", "viewer@example.com", "viewer")
        self.assertTrue(self.platform.verify_audit_chain("org_main"))
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE audit_events SET details_json='{}' WHERE action='member.invited'")
        self.assertFalse(self.platform.verify_audit_chain("org_main"))


class _Provider:
    name = "testpay"

    def verify_and_parse(self, body, headers):
        if headers.get("signature") != "valid":
            raise BillingVerificationError("invalid signature")
        return BillingEvent("testpay", body.decode(), "org_main", "business", "active")


class BillingBoundaryTests(unittest.TestCase):
    def test_receiver_requires_configured_provider_and_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            platform = SaaSPlatform(Path(temp) / "saas.sqlite3")
            platform.bootstrap_owner("usr_owner", "owner@example.com", "org_main")
            receiver = BillingEventReceiver(platform, (_Provider(),))
            with self.assertRaises(BillingVerificationError):
                receiver.receive("missing", b"evt_1", {})
            with self.assertRaises(BillingVerificationError):
                receiver.receive("testpay", b"evt_1", {"signature": "wrong"})
            self.assertTrue(receiver.receive("testpay", b"evt_1", {"signature": "valid"}))
            self.assertFalse(receiver.receive("testpay", b"evt_1", {"signature": "valid"}))


if __name__ == "__main__":
    unittest.main()
