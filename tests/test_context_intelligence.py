import tempfile
import unittest
from pathlib import Path

from olympus.agent.context_engine import ContextEngine
from olympus.agent.repo_map import build_repo_map


class TestContextIntelligence(unittest.TestCase):
    def test_dependency_graph_expands_from_primary_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "olympus").mkdir()
            (root / "tests").mkdir()
            (root / "olympus/service.py").write_text(
                "from olympus.helper import format_value\n\ndef render(value):\n    return format_value(value)\n",
                encoding="utf-8",
            )
            (root / "olympus/helper.py").write_text("def format_value(value):\n    return str(value)\n", encoding="utf-8")
            (root / "tests/test_service.py").write_text("from olympus.service import render\n", encoding="utf-8")
            repo = build_repo_map(tmp)
            related = repo.find_related_files("olympus/service.py")
            self.assertIn("olympus/helper.py", related)
            self.assertIn("tests/test_service.py", related)

    def test_symbol_reference_gets_strong_ranking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "olympus").mkdir()
            (root / "olympus/router.py").write_text("class AgentControlPlane:\n    pass\n", encoding="utf-8")
            (root / "olympus/noise.py").write_text("# Agent control plane words only\n", encoding="utf-8")
            repo = build_repo_map(tmp)
            ranked = repo.rank_relevant("Improve AgentControlPlane failover", limit=2)
            self.assertEqual(ranked[0].path, "olympus/router.py")
            self.assertTrue(any("symbol_match" in reason for reason in ranked[0].reasons))

    def test_context_uses_focused_lines_not_only_file_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "olympus").mkdir()
            lines = ["HEADER_%d = %d" % (i, i) for i in range(80)]
            lines += ["def critical_recovery():", "    return 'important'", "TAIL = True"]
            (root / "olympus/large.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
            repo = build_repo_map(tmp)
            context = ContextEngine(tmp, max_files=1, max_chars=1200, max_lines=20).resolve(
                "Fix critical_recovery behavior", repo
            )
            snippet = context.snippets["olympus/large.py"]
            self.assertIn("critical_recovery", snippet)
            self.assertIn("lines omitted", snippet)
            self.assertLessEqual(context.budget_usage["lines"], 20)

    def test_context_explains_selection_and_includes_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "olympus").mkdir()
            (root / "tests").mkdir()
            (root / "olympus/payment.py").write_text("def calculate_total():\n    return 1\n", encoding="utf-8")
            (root / "tests/test_payment.py").write_text("from olympus.payment import calculate_total\n", encoding="utf-8")
            repo = build_repo_map(tmp)
            context = ContextEngine(tmp, max_files=3).resolve("Change calculate_total payment", repo)
            self.assertIn("olympus/payment.py", context.selected_files)
            self.assertIn("tests/test_payment.py", context.selected_files)
            self.assertTrue(context.selection_reasons["olympus/payment.py"].startswith("ranked:"))

    def test_frontend_sources_are_mapped_and_available_as_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app").mkdir()
            (root / "app/index.html").write_text(
                "<main><input aria-label='Pesquisar'></main>", encoding="utf-8"
            )
            (root / "app/styles.css").write_text(
                "main { display: grid; }", encoding="utf-8"
            )

            repo = build_repo_map(tmp)
            context = ContextEngine(tmp).resolve(
                "Melhore app/index.html e o campo Pesquisar", repo
            )

            self.assertIn("app/index.html", repo.files)
            self.assertIn("app/styles.css", repo.files)
            self.assertIn("app/index.html", context.selected_files)


if __name__ == "__main__":
    unittest.main()
