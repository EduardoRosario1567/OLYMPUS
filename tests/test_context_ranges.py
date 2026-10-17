import json

from olympus.agent.actions import AgentAction, ActionType
from olympus.agent.executor import ActionExecutor
from olympus.agent.loop import AgentLoop
from olympus.agent.state import AgentState


def test_requested_tail_survives_read_and_planner_summary(tmp_path):
    source = tmp_path / "docs" / "requisitos.md"
    source.parent.mkdir()
    source.write_text("Introdução\n" * 95 + "Aceitação: mostrar o cardápio ao clicar.\n", encoding="utf-8")
    observation = ActionExecutor(str(tmp_path)).execute(AgentAction(
        ActionType.READ_FILE, "docs/requisitos.md", {"start_line": 91, "max_lines": 6},
    ))
    assert observation.success
    assert "mostrar o cardápio" in observation.output
    summary = json.loads(AgentLoop._state_summary(AgentState(
        task="Atualize o café", observations=(observation,),
    )))
    assert "mostrar o cardápio" in summary["recent_actions"][0]["output"]
    assert summary["recent_actions"][0]["read_range"]["start_line"] == 91


def test_read_range_rejects_invalid_offsets(tmp_path):
    (tmp_path / "index.html").write_text("hello", encoding="utf-8")
    for payload in ({"start_line": 0}, {"max_lines": 0}, {"start_line": "bad"}):
        result = ActionExecutor(str(tmp_path)).execute(AgentAction(ActionType.READ_FILE, "index.html", payload))
        assert not result.success
