from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendConversationUXTests(unittest.TestCase):
    def test_primary_routes_open_the_conversation(self):
        auth = (ROOT / "frontend/hooks/useAuth.ts").read_text(encoding="utf-8")
        root = (ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")
        dashboard = (ROOT / "frontend/app/dashboard/page.tsx").read_text(encoding="utf-8")
        self.assertIn('router.push("/missao")', auth)
        self.assertIn('autenticado ? "/missao"', root)
        self.assertIn('router.replace("/missao")', dashboard)

    def test_mission_keeps_the_complete_product_flow(self):
        from tests.frontend_contract import check_browser
        check_browser('mission_flow')
        check_browser('project_creation_failure')

    def test_preview_and_version_api_contracts_are_present(self):
        service = (ROOT / "frontend/services/api.ts").read_text(encoding="utf-8")
        for path in ("/versions", "/compare", "/restore", "/preview-session"):
            self.assertIn(path, service)
        self.assertIn("CloudProjectVersion", service)
        self.assertIn("CloudVersionComparison", service)
        self.assertIn("CloudStudioFileContent", service)
        self.assertIn("CloudRuntimeLog", service)
        self.assertIn("CloudGitHubStatus", service)
        self.assertIn("CloudGitHubCommit", service)
        self.assertIn("CloudPublication", service)
        for path in ("/cloud/github/connection", "/repository", "/branches", "/sync", "/commits", "/publish", "/publication"):
            self.assertIn(path, service)
        for path in ("/cloud/railway/connection", "/service", "/secrets", "/deployments", "/rollback"):
            self.assertIn(path, service)

    def test_primary_experience_keeps_friendly_error_and_gates_raw_diagnostic(self):
        page = (ROOT / "frontend/app/missao/page.tsx").read_text(encoding="utf-8")
        self.assertIn("mensagemAmigavel(execution.error)", page)
        self.assertIn("Ver diagnóstico técnico", page)
        self.assertIn("{execution.error}", page)
        self.assertIn("execution.execution_id", page)
        self.assertIn("model_failover", page)
        self.assertIn("Missão interrompida com diagnóstico", page)
        self.assertIn("Retomar após corrigir", page)

    def test_sidebar_prioritizes_only_user_tasks(self):
        from tests.frontend_contract import check_browser
        check_browser('navigation')

    def test_projects_page_uses_the_same_cloud_workspace_as_missions(self):
        page = (ROOT / "frontend/app/projetos/page.tsx").read_text(encoding="utf-8")
        self.assertIn("listarCloudProjetos", page)
        self.assertIn("criarCloudProjeto", page)
        self.assertIn("baixarCloudProjeto", page)
        self.assertIn("/missao?project_id=", page)
        self.assertNotIn("listarProjetos()", page)

    def test_transparent_high_resolution_brand_is_used_in_primary_surfaces(self):
        import struct
        import xml.etree.ElementTree as ET

        mark = (ROOT / "frontend/public/olympus-mark.png").read_bytes()
        self.assertEqual(mark[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", mark[16:24])
        self.assertEqual((width, height), (1024, 1024))
        self.assertIn(mark[25], (4, 6), "the Zeus mark must preserve an alpha channel")
        self.assertNotIn(b"Made with AI", mark)
        ET.parse(ROOT / "frontend/public/olympus-wordmark.svg")
        for relative in ("frontend/components/layout/sidebar.tsx", "frontend/app/missao/page.tsx", "frontend/app/login/page.tsx"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("/olympus-mark.png?v=", source)

    def test_saas_management_stays_out_of_primary_conversation(self):
        settings = (ROOT / "frontend/app/configuracoes/page.tsx").read_text(encoding="utf-8")
        invitation = (ROOT / "frontend/app/convite/page.tsx").read_text(encoding="utf-8")
        mission = (ROOT / "frontend/app/missao/page.tsx").read_text(encoding="utf-8")
        service = (ROOT / "frontend/services/api.ts").read_text(encoding="utf-8")
        for operation in ("obterOrganizacao", "listarMembros", "convidarMembro", "alterarPapelMembro", "removerMembro", "obterUso", "listarAuditoria"):
            self.assertIn(operation, settings)
            self.assertNotIn(operation, mission)
        self.assertIn("aceitarConvite", invitation)
        self.assertIn("/cloud/saas/invitations/accept", service)
        self.assertIn("Link de uso único", settings)
        self.assertIn("Atividade e segurança", settings)

    def test_history_uses_tenant_scoped_cloud_runtime(self):
        history = (ROOT / "frontend/app/execucoes/page.tsx").read_text(encoding="utf-8")
        self.assertIn("listarCloudExecucoes", history)
        self.assertNotIn("listarExecucoes(", history)


if __name__ == "__main__":
    unittest.main()
