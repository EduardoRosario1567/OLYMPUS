from tests.frontend_contract import browser_results

def test_current_ui_behaviour():
    results = browser_results()
    assert all(v is True for v in results["checks"].values()), results
