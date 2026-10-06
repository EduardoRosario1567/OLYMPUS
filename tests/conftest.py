"""Inject installed QA browser at the OS boundary; all rendered checks remain real."""
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest


@pytest.fixture(autouse=True)
def isolated_capacity_history(tmp_path):
    """Keep simulated provider results out of the app and later tests.

    Respect tests that explicitly select their own capacity store, including
    while they temporarily clear the process environment.
    """
    from olympus.routing import capacity_fabric
    original = capacity_fabric._state_path
    def state_path():
        if os.environ.get('OLYMPUS_CAPACITY_STATE_PATH', '').strip():
            return original()
        return tmp_path/'capacity-fabric.json'
    with patch.object(capacity_fabric, '_state_path', state_path):
        yield


@pytest.fixture(autouse=True)
def trusted_repository_test_processes(request):
    """QA ONLY: execute the reviewed repository fixtures with scrubbed env.

    This is an explicit substitution of the container boundary, never a
    production setting or evidence of real OS isolation. Container-contract
    tests do not use it. The real container gate never loads this fixture.
    """
    if (os.environ.get('OLYMPUS_QA_TRUSTED_TESTS') != '1'
            or request.module.__name__.endswith(('test_container_execution', 'test_rc2_isolation_bridge'))):
        yield
        return
    import subprocess
    import tempfile
    from olympus.agent.acceptance import _scrubbed_env
    from olympus.agent.container_execution import ContainerExecutor
    def run(self, root, command, timeout):
        with tempfile.TemporaryDirectory(prefix='olympus-reviewed-qa-') as home:
            return subprocess.run(list(command), cwd=str(root),
                env=_scrubbed_env(Path(root), home), capture_output=True,
                text=True, timeout=timeout, shell=False)
    with patch.object(ContainerExecutor, 'run', run):
        yield


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
