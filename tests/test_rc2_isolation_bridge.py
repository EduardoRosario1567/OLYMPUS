import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from olympus.agent.acceptance import run_tests
from olympus.agent.container_execution import ContainerExecutor, IsolationUnavailable, snapshot_project
from olympus.agent.test_runner import TargetedTestRunner


class RC2IsolationBridgeTests(unittest.TestCase):
    def test_both_paths_block_without_docker_and_do_not_execute_host_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'must-not-exist'
            command = [sys.executable, '-c', 'open(%r,"w").write("executed")' % str(marker)]
            with patch('olympus.agent.container_execution.shutil.which', return_value=None):
                acceptance = run_tests(tmp, command)
                targeted = TargetedTestRunner(tmp).run_unittest(['tests.untrusted'])
            self.assertEqual(acceptance['returncode'], 125)
            self.assertFalse(acceptance['ran'])
            self.assertEqual(targeted.returncode, 125)
            self.assertFalse(targeted.success)
            self.assertFalse(marker.exists())

    def test_targeted_runner_rejects_zero_exit_without_test_evidence(self):
        result = subprocess.CompletedProcess([], 0, '', '')
        with patch.object(ContainerExecutor, 'run', return_value=result):
            outcome = TargetedTestRunner().run_unittest(['tests.fake'])
        self.assertFalse(outcome.success)
        self.assertIn('evidence missing', outcome.stderr)

    def test_targeted_runner_accepts_nonempty_success_evidence(self):
        result = subprocess.CompletedProcess([], 0, '', 'Ran 2 tests in 0.01s\n\nOK\n')
        with patch.object(ContainerExecutor, 'run', return_value=result):
            self.assertTrue(TargetedTestRunner().run_unittest(['tests.fixture']).success)

    def test_missing_test_command_remains_unexecuted(self):
        with patch.object(ContainerExecutor, 'run') as runner:
            self.assertFalse(run_tests('.', None)['ran'])
            runner.assert_not_called()

    def test_snapshot_excludes_credentials_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'; root.mkdir()
            for name in ['.env', 'credentials.json', 'secrets.yaml', 'private.key', 'state.db']:
                (root / name).write_text('SYNTHETIC_SECRET')
            (root / 'main.py').write_text('value = 1')
            staged = Path(tmp) / 'snapshot'
            snapshot_project(root, staged)
            self.assertEqual(sorted(p.name for p in staged.iterdir()), ['main.py'])
            self.assertEqual((root / 'main.py').read_text(), 'value = 1')

    def test_snapshot_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'; root.mkdir()
            (root / 'escape').symlink_to('/tmp')
            with self.assertRaises(IsolationUnavailable):
                snapshot_project(root, Path(tmp) / 'snapshot')

    def test_container_contract_uses_filtered_copy_and_resource_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'; root.mkdir()
            (root / 'main.py').write_text('print(1)')
            client = ('docker', '--host', 'unix:///var/run/docker.sock')
            completed = subprocess.CompletedProcess([], 0, '1', '')
            with patch.object(ContainerExecutor, '_client', return_value=client), patch.object(ContainerExecutor, '_image_id', return_value='sha256:'+'a'*64), patch.object(ContainerExecutor, '_capture', return_value=completed) as capture, patch('olympus.agent.container_execution.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '', '')):
                result = ContainerExecutor().run(root, ['python3', 'main.py'], 10)
            self.assertEqual(result.returncode, 0)
            argv = capture.call_args.args[0]
            for flag in ['--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true', '--memory=512m', '--pids-limit=128']:
                self.assertIn(flag, argv)
            mount = argv[argv.index('--mount')+1]
            self.assertNotIn(str(root), mount)
            self.assertTrue(mount.endswith('dst=/workspace,readonly'))

    def test_unconfirmed_cleanup_blocks_success_in_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ContainerExecutor, '_client', return_value=('docker',)), patch.object(ContainerExecutor, '_image_id', return_value='sha256:'+'a'*64), patch.object(ContainerExecutor, '_capture', return_value=subprocess.CompletedProcess([], 0, '', '')), patch('olympus.agent.container_execution.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'permission denied')):
                result = run_tests(tmp, ['python3', '-c', 'print(1)'])
            self.assertEqual(result['returncode'], 125)
            self.assertIn('execution_cleanup_unconfirmed', result['tail'])


if __name__ == '__main__':
    unittest.main()
