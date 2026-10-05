"""The current tenant-scoped runtime replaces the removed global E2E route."""
import json
from pathlib import Path
import time
from olympus.cloud.runtime import CloudRuntime, _Store


def test_e2e_run_gets_its_own_persisted_execution_id(tmp_path):
    store = _Store(str(tmp_path / 'executions.db'))
    a = store.create('p', 'm', 'first', tenant_id='a')
    b = store.create('p', 'm', 'second', tenant_id='b')
    reopened = _Store(str(tmp_path / 'executions.db'))
    assert a.execution_id != b.execution_id
    assert reopened.get(a.execution_id).task == 'first'
    assert [r.execution_id for r in reopened.list('a')] == [a.execution_id]
    assert reopened.events(a.execution_id)[0]['event'] == 'queued'


def test_e2e_failure_captures_stage_events_artifact_and_traceback(tmp_path):
    class Runner:
        def __init__(self, workspace, telemetry):
            self.workspace, self.telemetry = Path(workspace), telemetry
        def run(self, *args, **kwargs):
            (self.workspace / 'partial.txt').write_text('preserved')
            self.telemetry({'event':'model_selected', 'model':'synthetic-free'})
            raise ValueError('synthetic failure')
    runtime = CloudRuntime(str(tmp_path), Runner, max_worker_retries=0)
    try:
        record = runtime.submit('p', 'create helper')
        deadline = time.monotonic() + 3
        while runtime.get(record.execution_id).status != 'failed' and time.monotonic() < deadline:
            time.sleep(.01)
        failed = runtime.get(record.execution_id)
        assert failed.status == 'failed'
        assert (Path(failed.workspace) / 'partial.txt').read_text() == 'preserved'
        events = runtime.events(record.execution_id)
        assert any(e['event'] == 'model_selected' for e in events)
        failure = next(e for e in events if e['event'] == 'failed')
        assert failure['failure_stage'] == 'execution'
        assert failure['error_type'] == 'ValueError'
        assert 0 < len(failure['traceback']) <= 30
        assert failure['traceback'][-1]['function'] == 'run'
        assert 'synthetic failure' not in json.dumps(failure['traceback'])
        assert _Store(runtime.store.path).events(record.execution_id) == events
    finally:
        runtime.close()


def test_diagnostic_version_falls_back_to_version_file():
    from app.main import app
    from fastapi.testclient import TestClient
    version = json.loads((Path(__file__).resolve().parents[1] / 'frontend/public/olympus-version.json').read_text())
    response = TestClient(app).get('/health')
    assert response.status_code == 200
    assert response.json()['version'] == version['version']
    assert response.json()['build'] == version['build']
