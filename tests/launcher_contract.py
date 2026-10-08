"""Run the real launcher with controlled OS process/dependency boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def launch(*, foreign=False, reused=False, timeout=None):
    with tempfile.TemporaryDirectory(prefix='olympus-launcher-') as directory:
        root = Path(directory)
        for rel in ['backend', 'frontend/public', 'frontend/node_modules/.bin', '.venv/bin', 'bin']:
            (root / rel).mkdir(parents=True, exist_ok=True)
        (root / 'start_olympus.command').write_bytes((ROOT / 'start_olympus.command').read_bytes())
        version = json.loads((ROOT / 'frontend/public/olympus-version.json').read_text())
        (root / 'frontend/public/olympus-version.json').write_text(json.dumps(version))
        (root / 'backend/.env').write_text('SYNTHETIC_SECRET=preserved\n')
        (root / 'frontend/.next').mkdir()
        (root / 'frontend/.next/stale.js').write_text('old')
        trace = root / 'trace'
        state = root / 'state'
        state.write_text('owned')
        scripts = {
            '.venv/bin/python': '#!/bin/bash\nexit 0\n',
            'frontend/node_modules/.bin/next': '#!/bin/bash\nexit 0\n',
            'bin/curl': '#!/bin/bash\ncase "$*" in *20128*) exit 7;; *8000*) echo '+repr(json.dumps({'version':version['version'],'build':version['build']}))+';; *3000*) echo '+repr(json.dumps(version))+';; esac\n',
            'bin/ps': '#!/bin/bash\nif [ \"$1\" = \"-p\" ] && [ \"$2\" = \"99999\" ]; then echo 99999; exit 0; fi\nexit 1\n',
            'bin/node': '#!/bin/bash\necho v24.0.0\n',
            'bin/npm': '#!/bin/bash\necho "npm $*" >> "$QA_TRACE"\nexit 0\n',
            'bin/nohup': '#!/bin/bash\necho "nohup $* timeout=$OLYMPUS_MODEL_TIMEOUT" >> "$QA_TRACE"\nexit 0\n',
            'bin/sleep': '#!/bin/bash\nexit 0\n',
            'bin/open': '#!/bin/bash\nexit 0\n',
            'bin/lsof': '''#!/bin/bash
if [ "$QA_SCENARIO" = "none" ]; then exit 1; fi
if [ "$1" = "-a" ]; then
  if [ "$QA_SCENARIO" = "foreign" ] || [ "$(cat "$QA_STATE")" = "reused" ]; then echo n/foreign/application; else echo "n$QA_ROOT"; fi
else echo 99999; fi
''',
        }
        for rel, text in scripts.items():
            path = root / rel; path.write_text(text); path.chmod(0o700)
        bash_env = root / 'bash-env'
        bash_env.write_text('kill(){ echo "kill $*" >> "$QA_TRACE"; if [ "$QA_SCENARIO" = "reused" ]; then echo reused > "$QA_STATE"; fi; }\n')
        env = dict(os.environ, PATH=str(root / 'bin')+os.pathsep+os.environ['PATH'], BASH_ENV=str(bash_env), QA_ROOT=str(root), QA_TRACE=str(trace), QA_STATE=str(state), QA_SCENARIO='foreign' if foreign else 'reused' if reused else 'none')
        env["OLYMPUS_PYTHON"] = sys.executable
        env.pop('OLYMPUS_MODEL_TIMEOUT', None)
        if timeout: env['OLYMPUS_MODEL_TIMEOUT'] = str(timeout)
        result = subprocess.run(['bash', str(root / 'start_olympus.command')], env=env, text=True, capture_output=True, timeout=10)
        return {'code':result.returncode, 'output':result.stdout+result.stderr, 'trace':trace.read_text() if trace.exists() else '', 'env':(root / 'backend/.env').read_text(), 'stale_cache_exists':(root / 'frontend/.next/stale.js').exists()}
