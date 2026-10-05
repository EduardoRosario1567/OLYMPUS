"""Inject installed QA browser at the OS boundary; all rendered checks remain real."""
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest


@pytest.fixture(autouse=True)
def installed_browser_runtime():
    executable = os.environ.get('OLYMPUS_QA_CHROMIUM')
    modules = os.environ.get('OLYMPUS_QA_NODE_MODULES')
    if not executable or not modules:
        yield
        return
    from olympus.agent.browser_delivery import BrowserRuntime, WebDeliveryVerifier
    qa_runtime = BrowserRuntime(modules, executable,
        tuple(json.loads(os.environ.get('OLYMPUS_QA_CHROMIUM_ARGS','[]'))), False)
    evidence = Path(os.environ['OLYMPUS_QA_BROWSER_EVIDENCE'])/'deliveries'
    original = WebDeliveryVerifier.__init__
    def initialize(self, root, runtime=None, evidence_root=None):
        original(self, root, runtime or qa_runtime, evidence_root or evidence)
    with patch.object(WebDeliveryVerifier, '__init__', initialize):
        yield
