import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def test_development_csp_allows_hydration_without_weakening_production():
    code = "import config from './frontend/next.config.mjs';console.log(JSON.stringify(await config.headers()));"
    for mode in ('development', 'production'):
        output = subprocess.check_output(['node', '--input-type=module', '-e', code], cwd=ROOT, env=dict(os.environ, NODE_ENV=mode), text=True)
        headers = json.loads(output)[0]['headers']
        csp = next(h['value'] for h in headers if h['key'] == 'Content-Security-Policy')
        assert ("'unsafe-eval'" in csp) == (mode == 'development')
        assert "object-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
