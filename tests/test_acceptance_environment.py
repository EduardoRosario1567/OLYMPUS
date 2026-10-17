import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

from olympus.agent.acceptance import run_tests


def test_acceptance_test_process_cannot_inherit_user_home_or_proxy(tmp_path):
    home = tmp_path/'private-user-home'
    home.mkdir()
    code = 'import os,json;print(json.dumps({"home":os.environ.get("HOME"),"proxy":os.environ.get("HTTPS_PROXY")}))'
    with patch.dict(os.environ, HOME=str(home), HTTPS_PROXY='http://synthetic-proxy.example'):
        result = run_tests(tmp_path, [sys.executable, '-c', code])
    assert result['returncode'] == 0
    output = json.loads(result['tail'])
    assert output['home'] != str(home)
    assert output['proxy'] is None
    assert not Path(output['home']).exists()
