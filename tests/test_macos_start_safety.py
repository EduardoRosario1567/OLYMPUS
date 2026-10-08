"""Exercise launcher decisions with fake processes; never signal real listeners."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MacStartSafetyTests(unittest.TestCase):
    def run_shell(self, scenario):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'frontend/public').mkdir(parents=True)
            (root / 'frontend/public/olympus-version.json').write_text(json.dumps({'version': '3.0.8'}))
            prefix = (ROOT / 'start_olympus.command').read_text().split('echo "Iniciando OLYMPUS')[0]
            script = root / 'probe.command'
            script.write_text(prefix + '\nPYTHON_BIN=python3\nkill(){ echo "SIGNAL $*"; }\nsleep(){ :; }\n' + scenario)
            return subprocess.run(['bash', str(script)], text=True, capture_output=True)

    def test_foreign_listener_is_never_signalled(self):
        result = self.run_shell('''
listener_pids(){ echo 123; }
listener_alive(){ return 0; }
listener_cwd(){ echo /another/application; }
safe_stop_port 8000 "$ROOT" backend
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('SIGNAL', result.stdout)

    def test_vanished_listener_is_never_signalled(self):
        result = self.run_shell('''
listener_pids(){ echo 123; }
listener_alive(){ return 1; }
listener_cwd(){ echo "$ROOT"; }
safe_stop_port 8000 "$ROOT" backend
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('SIGNAL', result.stdout)

    def test_identity_is_rechecked_before_term(self):
        result = self.run_shell('''
listener_pids(){ echo 123; }
listener_alive(){ return 0; }
listener_cwd(){
 if [ -f "$ROOT/seen" ]; then echo /another/application;
 else touch "$ROOT/seen"; echo "$ROOT"; fi
}
safe_stop_port 8000 "$ROOT" backend
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('SIGNAL', result.stdout)

    def test_identity_is_rechecked_before_force_kill(self):
        result = self.run_shell('''
listener_pids(){ echo 123; }
listener_alive(){ return 0; }
listener_cwd(){
 if [ -f "$ROOT/terminated" ]; then echo /another/application;
 else echo "$ROOT"; fi
}
kill(){ echo "SIGNAL $*"; touch "$ROOT/terminated"; }
safe_stop_port 8000 "$ROOT" backend
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SIGNAL 123', result.stdout)
        self.assertNotIn('SIGNAL -KILL', result.stdout)

    def test_health_rejects_previous_version_and_wrong_product(self):
        for body, command in [
            ('{"version":"3.0.7"}', 'backend_is_current'),
            ('{"version":"3x0x8"}', 'backend_is_current'),
            ('{"version":"3 .0.8"}', 'backend_is_current'),
            ('not-json', 'backend_is_current'),
            ('{"version":"3.0.8","product":"other"}', 'frontend_is_current'),
            ('{"version":"3.0.7","product":"olympus"}', 'frontend_is_current'),
        ]:
            with self.subTest(body=body):
                result = self.run_shell("backend_body(){ printf '%s' '" + body + "'; }\nfrontend_body(){ backend_body; }\n" + command)
                self.assertNotEqual(result.returncode, 0)

    def test_health_accepts_expected_product_and_version(self):
        result = self.run_shell('''
backend_body(){ echo '{"version":"3.0.8"}'; }
frontend_body(){ echo '{"version":"3.0.8","product":"olympus"}'; }
backend_is_current && frontend_is_current
''')
        self.assertEqual(result.returncode, 0, result.stderr)
