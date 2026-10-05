from tests.launcher_contract import launch

def test_reused_pid_is_never_killed_after_ownership_changes():
    result = launch(reused=True)
    assert result['code'] != 0
    assert 'kill 99999' in result['trace']
    assert 'kill -KILL 99999' not in result['trace']
