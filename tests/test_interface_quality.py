from tests.frontend_contract import check_browser


def test_five_product_pages_have_names_and_fit_mobile_tablet_desktop():
    check_browser("accessible_layout")
