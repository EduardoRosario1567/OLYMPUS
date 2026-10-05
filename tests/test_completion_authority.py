"""A provider interruption and a runner claim must not bypass delivery checks."""
from dataclasses import dataclass
from pathlib import Path
import time

from olympus.agent.actions import ActionType, AgentAction
from olympus.agent.loop import AgentLoop
from olympus.cloud.runtime import CloudRuntime


class InterruptedPlanner:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def next_action(self, *args):
        self.calls += 1
        if self.calls == 1:
            return AgentAction(ActionType.CREATE_FILE, "index.html", self.content)
        raise RuntimeError("provider timeout: timed out")


def test_provider_timeout_cannot_complete_a_placeholder_site(tmp_path):
    result = AgentLoop(str(tmp_path), InterruptedPlanner(
        "<html><body><h1>Welcome</h1></body></html>"
    )).run("Crie uma landing page profissional para Rosales Café.")
    assert result.state.status.value == "blocked"
    assert result.failure_kind == "technical"
    assert any("deliverable quality" in error for error in result.state.errors)


@dataclass
class ClaimedDelivery:
    status: str = "completed"
    success: bool = True
    files_modified: tuple = ("teste.txt",)
    error: str = None


def test_publication_rejects_wrong_content_despite_runner_success(tmp_path):
    class Runner:
        def __init__(self, workspace, telemetry):
            self.workspace = workspace

        def run(self, task, **kwargs):
            Path(self.workspace, "teste.txt").write_text("OLYMPIUS_OK\n", encoding="utf-8")
            return ClaimedDelivery()

    runtime = CloudRuntime(str(tmp_path), Runner, max_workers=1)
    try:
        rec = runtime.submit("exact", "Crie um arquivo chamado teste.txt contendo apenas: OLYMPUS_OK")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = runtime.get(rec.execution_id)
            if current.status in {"completed", "failed", "blocked"}:
                break
            time.sleep(0.01)
        assert current.status == "failed"
        events = runtime.events(rec.execution_id)
        assert any(item["event"] == "completion_rejected" for item in events)
        assert not any(item["event"] == "result_published" for item in events)
    finally:
        runtime.close()
