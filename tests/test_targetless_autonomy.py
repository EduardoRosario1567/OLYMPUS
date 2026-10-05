import tempfile
import unittest
from pathlib import Path

from olympus.agent.context_engine import ContextEngine
from olympus.agent.repo_map import build_repo_map


class TestTargetlessAutonomy(unittest.TestCase):
    def test_repo_map_indexes_shell_entrypoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts/olympus_dev.sh").write_text(
                '#!/bin/zsh\nhealth_check() {\n  echo "OmniRoute DEV AGENT"\n}\n',
                encoding="utf-8",
            )
            repo = build_repo_map(str(root))
            self.assertIn("scripts/olympus_dev.sh", repo.files)
            self.assertIn("health_check", repo.files["scripts/olympus_dev.sh"].functions)

    def test_context_can_discover_shell_entrypoint_without_explicit_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "olympus").mkdir()
            (root / "scripts/olympus_dev.sh").write_text(
                '#!/bin/zsh\necho "DEV AGENT"\necho "OmniRoute"\n', encoding="utf-8"
            )
            (root / "olympus/other.py").write_text("VALUE = 1\n", encoding="utf-8")
            repo = build_repo_map(str(root))
            context = ContextEngine(str(root)).resolve(
                "Melhore o OLYMPUS DEV AGENT e mostre o status do OmniRoute",
                repo,
            )
            self.assertIn("scripts/olympus_dev.sh", context.selected_files)

    def test_dev_launcher_no_longer_requires_manual_target(self):
        script = Path("scripts/olympus_dev.sh").read_text(encoding="utf-8")
        self.assertNotIn("Arquivo autorizado para alteração", script)
        self.assertNotIn("resolve_new_target", script)
        self.assertIn("scripts/olympus_task.py", script)
        self.assertIn("DEV AGENT  •  0.4", script)


if __name__ == "__main__":
    unittest.main()
