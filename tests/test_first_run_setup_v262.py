import os
import stat
import tempfile
import unittest
from pathlib import Path

from scripts.first_run_setup import (
    render_environment,
    validate_email,
    validate_password,
    write_private,
)


class FirstRunSetupV262Tests(unittest.TestCase):
    def test_validates_identity_without_default_password(self):
        self.assertEqual(validate_email(" Pessoa@Example.com "), "pessoa@example.com")
        self.assertEqual(validate_password("uma-senha-local-forte"), "uma-senha-local-forte")
        with self.assertRaises(ValueError):
            validate_email("invalido")
        with self.assertRaises(ValueError):
            validate_password("troque-isto")

    def test_renders_all_private_values(self):
        template = "OLYMPUS_ADMIN_EMAIL=\nOLYMPUS_ADMIN_SENHA=\nOLYMPUS_JWT_SECRET=\nX=1\n"
        rendered = render_environment(template, "a@b.com", "senha-forte-123", "jwt-secreto")
        self.assertIn("OLYMPUS_ADMIN_EMAIL=a@b.com", rendered)
        self.assertIn("OLYMPUS_ADMIN_SENHA=senha-forte-123", rendered)
        self.assertIn("OLYMPUS_JWT_SECRET=jwt-secreto", rendered)

    def test_writes_private_file_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, ".env")
            write_private(target, "SEGREDO=valor\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "SEGREDO=valor\n")
            self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
