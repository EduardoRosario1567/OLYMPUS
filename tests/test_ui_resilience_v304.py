from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")

def test_version_is_visible_and_consistent():
    from tests.frontend_contract import check_browser
    check_browser('version')

def test_startup_clears_transient_omniroute_override_and_restarts_backend():
    start = read("start_olympus.command")
    assert "env -u OLYMPUS_OMNIROUTE_URL" in start
    assert "instância da mesma versão iniciada com variáveis transitórias" in start
    assert "if ! backend_current; then" not in start

def test_connections_refresh_is_no_cache_and_visible():
    api = read("frontend/services/api.ts")
    page = read("frontend/app/conexoes/page.tsx")
    assert 'cache: "no-store"' in api
    assert "Date.now()" in api
    assert "Atualizando…" in page
    assert "expandedProvider" in page
    assert "Configurar agora" in page

def test_projects_live_in_sidebar_not_composer():
    sidebar = read("frontend/components/layout/sidebar.tsx")
    mission = read("frontend/app/missao/page.tsx")
    assert "listarCloudProjetos" in sidebar
    assert "criarCloudProjeto" in sidebar
    assert "project_id=" in sidebar
    assert 'select value={projectId}' not in mission
    assert ">Novo projeto<" not in mission


def test_sidebar_exports_mobile_nav_expected_by_panel_shell():
    sidebar = read("frontend/components/layout/sidebar.tsx")
    assert "export function MobileNav" in sidebar
    assert "export function Sidebar" in sidebar

def test_sidebar_preserves_legacy_brand_export():
    sidebar = read("frontend/components/layout/sidebar.tsx")
    assert "export function Brand" in sidebar
    assert "export function MobileNav" in sidebar
    assert "export function Sidebar" in sidebar

def test_provider_catalog_refresh_avoids_custom_cache_control_header():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    api = (root / "frontend/services/api.ts").read_text()
    start = api.index("listarConexoes:")
    snippet = api[start:start+260]
    assert 'cache: "no-store"' in snippet
    assert 'Cache-Control' not in snippet
    assert '/providers/catalog?ts=${Date.now()}' in snippet
