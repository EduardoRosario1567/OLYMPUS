"""Real browser checks of the independent shell and provider workflows."""
import unittest
from tests.frontend_contract import check_browser

class ProfessionalShellTests(unittest.TestCase):
    def test_sidebar_and_content_scroll_independently(self):
        check_browser("independent_scroll")

    def test_search_filters_and_refresh_error_preserve_catalog(self):
        check_browser("provider_filters_refresh")

    def test_secret_draft_preservation_and_read_only_permissions(self):
        check_browser("provider_credentials_permissions")

    def test_mobile_navigation_focus_and_scroll(self):
        check_browser("mobile_navigation_scroll")
