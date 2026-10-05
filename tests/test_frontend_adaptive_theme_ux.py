from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendAdaptiveThemeUXTests(unittest.TestCase):
    def test_theme_is_selected_before_paint_and_refreshed_from_local_time(self):
        layout = (ROOT / "frontend/app/layout.tsx").read_text(encoding="utf-8")
        controller = (ROOT / "frontend/components/theme-controller.tsx").read_text(encoding="utf-8")

        self.assertIn("h>=6&&h<18?'light':'dark'", layout)
        self.assertIn("<ThemeController />", layout)
        self.assertIn('hour >= 6 && hour < 18 ? "light" : "dark"', controller)
        self.assertIn("window.setInterval(applyAutomaticTheme, 60_000)", controller)
        self.assertIn('window.addEventListener("focus", refresh)', controller)

    def test_current_project_and_primary_commands_stay_visible(self):
        mission = (ROOT / "frontend/app/missao/page.tsx").read_text(encoding="utf-8")

        self.assertIn("project-bar sticky top-16", mission)
        self.assertIn("Projeto atual", mission)
        self.assertIn("selectedProject?.name", mission)
        for label in ("Visualizar", "Arquivos", "Versões", "Publicar"):
            self.assertIn(f">{label}<", mission)

    def test_sidebar_brand_is_larger_and_light_theme_has_contrast(self):
        from tests.frontend_contract import check_browser
        check_browser('brand')
        check_browser('contrast')


if __name__ == "__main__":
    unittest.main()
