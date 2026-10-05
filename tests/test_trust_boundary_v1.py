import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.trust import TrustBoundary, TrustDecision, is_protected_core, production_secret_is_safe


class TestTrustBoundaryV1(unittest.TestCase):
    def test_blocks_path_escape_and_absolute_path(self):
        with tempfile.TemporaryDirectory() as root:
            b = TrustBoundary()
            self.assertEqual(b.authorize_file_action(root, "../outside.txt").decision, TrustDecision.BLOCK)
            self.assertEqual(b.authorize_file_action(root, "/etc/passwd").decision, TrustDecision.BLOCK)

    def test_blocks_symlink_escape(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            Path(root, "link").symlink_to(outside, target_is_directory=True)
            result = TrustBoundary().authorize_file_action(root, "link/secret.txt")
            self.assertEqual(result.decision, TrustDecision.BLOCK)

    def test_blocks_secret_material(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(TrustBoundary().authorize_file_action(root, ".env").decision, TrustDecision.BLOCK)
            self.assertEqual(TrustBoundary().authorize_file_action(root, "config/api_key.txt").decision, TrustDecision.BLOCK)

    def test_protected_core_requires_human_for_write(self):
        with tempfile.TemporaryDirectory() as root:
            result = TrustBoundary().authorize_file_action(root, "backend/app/core/security.py", write=True)
            self.assertEqual(result.decision, TrustDecision.REQUIRE_USER)
            self.assertTrue(is_protected_core("olympus/agent/verification_engine.py"))

    def test_production_rejects_default_or_short_jwt_secret(self):
        with patch.dict(os.environ, {"OLYMPUS_ENV":"production", "OLYMPUS_JWT_SECRET":"short"}, clear=False):
            self.assertFalse(production_secret_is_safe())
        with patch.dict(os.environ, {"OLYMPUS_ENV":"production", "OLYMPUS_JWT_SECRET":"x"*48}, clear=False):
            self.assertTrue(production_secret_is_safe())
