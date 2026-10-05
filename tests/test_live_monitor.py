import unittest
from pathlib import Path


class TestLiveMonitor(unittest.TestCase):
    def setUp(self):
        self.script = Path("scripts/olympus_dev.sh").read_text(encoding="utf-8")

    def test_progress_function_exists(self):
        self.assertIn("run_with_progress()", self.script)

    def test_progress_has_elapsed_time(self):
        self.assertIn("elapsed=$((now - started))", self.script)

    def test_progress_is_single_fixed_line(self):
        self.assertIn("printf '\\r\\033[2K● OLYMPUS trabalhando...", self.script)
        self.assertIn(">&2", self.script)
        self.assertNotIn("for phase in", self.script)

    def test_progress_does_not_emit_phase_lines(self):
        for phase in (
            "preparando contexto",
            "analisando repositório",
            "selecionando contexto",
            "planejando próxima ação",
            "aguardando modelo",
            "executando ação",
            "validando resultado",
        ):
            self.assertNotIn(phase, self.script)

    def test_app_entrypoint_still_uses_canonical_project_root(self):
        self.assertIn('ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"', self.script)
        self.assertIn('export PYTHONPATH="$ROOT"', self.script)


if __name__ == "__main__":
    unittest.main()
