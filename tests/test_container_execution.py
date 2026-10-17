"""Container contracts with a controlled Docker boundary, not an OS proof."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import pytest
from olympus.agent.container_execution import ContainerExecutor, IsolationUnavailable, snapshot_project
from olympus.agent.acceptance import run_tests
from olympus.agent.test_runner import TargetedTestRunner

IMAGE_ID = 'sha256:' + 'a' * 64


def test_no_docker_fails_closed_in_both_test_paths(tmp_path):
    marker = tmp_path/'host-executed'
    command = [sys.executable, '-c', 'open(%r,"w").write("unsafe")' % str(marker)]
    with patch('olympus.agent.container_execution.shutil.which', return_value=None):
        direct = ContainerExecutor().run(tmp_path, command, 10)
        acceptance = run_tests(tmp_path, command)
        targeted = TargetedTestRunner(str(tmp_path)).run_unittest(['tests.test_example'])
    assert direct.returncode == acceptance['returncode'] == targeted.returncode == 125
    assert not acceptance['ran'] and not targeted.success
    assert 'execution_isolation_unavailable' in direct.stderr
    assert not marker.exists()


def test_snapshot_omits_credentials_state_and_does_not_mount_real_root(tmp_path):
    root = tmp_path/'project'; root.mkdir()
    for name in ['.env', '.env.local', 'credentials.json', 'secrets.yaml', 'server.key', 'db.sqlite3']:
        (root/name).write_text('SYNTHETIC_SECRET')
    (root/'.olympus').mkdir(); (root/'.olympus/token.txt').write_text('SYNTHETIC_SECRET')
    (root/'tests').mkdir(); (root/'tests/test_good.py').write_text('assert True')
    staged = tmp_path/'snapshot'
    assert snapshot_project(root, staged)['files'] == 1
    assert [p.relative_to(staged).as_posix() for p in staged.rglob('*') if p.is_file()] == ['tests/test_good.py']


@pytest.mark.parametrize('directory', [False, True])
def test_symlinks_are_refused_before_container_start(tmp_path, directory):
    root = tmp_path/'project'; root.mkdir()
    outside = tmp_path/'private'
    if directory: outside.mkdir()
    else: outside.write_text('private marker')
    (root/'linked').symlink_to(outside, target_is_directory=directory)
    with pytest.raises(IsolationUnavailable):
        snapshot_project(root, tmp_path/'snapshot')


def test_container_has_limits_no_network_readonly_snapshot_and_no_inherited_keys(tmp_path):
    (tmp_path/'test.py').write_text('assert True')
    commands = []
    def capture(self, argv, timeout):
        commands.append(list(argv))
        mount = argv[argv.index('--mount') + 1]
        source = Path(mount.split('src=',1)[1].split(',dst=',1)[0])
        assert source != tmp_path and (source/'test.py').is_file()
        assert not (source/'.env').exists()
        assert timeout == 8
        return subprocess.CompletedProcess(argv, 0, 'result', '')
    (tmp_path/'.env').write_text('SYNTHETIC_SECRET')
    with patch.object(ContainerExecutor, '_client', return_value=('docker', '--host', 'unix:///local.sock')), \
            patch.object(ContainerExecutor, '_image_id', return_value=IMAGE_ID), \
            patch.object(ContainerExecutor, '_capture', capture), \
            patch('olympus.agent.container_execution.subprocess.run', return_value=subprocess.CompletedProcess([],0,'','')) as cleanup, \
            patch.dict(os.environ, PROVIDER_KEY='SYNTHETIC_SECRET', DOCKER_HOST='tcp://remote:2375'):
        result = ContainerExecutor().run(tmp_path, [sys.executable, '-c', 'print(1)'], 8)
    assert result.returncode == 0
    argv = commands[0]
    for required in ['--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
            '--user=65534:65534', '--pids-limit=128', '--memory=512m', '--memory-swap=512m',
            '--cpus=1', '--pull=never', '--log-driver=none']:
        assert required in argv
    assert argv[argv.index('--mount')+1].endswith(',dst=/workspace,readonly')
    assert argv[argv.index('--entrypoint')+1] == 'python3'
    assert IMAGE_ID in argv
    assert all('SYNTHETIC_SECRET' not in arg and 'tcp://remote' not in arg for arg in argv)
    assert cleanup.call_args.args[0][-3:-1] == ['rm', '--force']
    assert 'PROVIDER_KEY' not in cleanup.call_args.kwargs['env']


def test_timeout_removes_only_the_owned_container_and_never_runs_on_host(tmp_path):
    with patch.object(ContainerExecutor, '_client', return_value=('docker',)), \
            patch.object(ContainerExecutor, '_image_id', return_value=IMAGE_ID), \
            patch.object(ContainerExecutor, '_capture', side_effect=subprocess.TimeoutExpired('docker', 1)), \
            patch('olympus.agent.container_execution.subprocess.run', return_value=subprocess.CompletedProcess([],0,'','')) as cleanup:
        result = ContainerExecutor().run(tmp_path, [sys.executable, '-c', 'pass'], 1)
    assert result.returncode == 124
    assert cleanup.call_args.args[0][:3] == ['docker', 'rm', '--force']
    assert cleanup.call_args.args[0][3].startswith('olympus-test-')
    assert len(cleanup.call_args.args[0]) == 4


@pytest.mark.parametrize('record', [[], [{'Id':'tag'}], [{'Id':IMAGE_ID,'Config':{'Labels':{}}}]])
def test_missing_or_unapproved_image_never_launches_code(tmp_path, record):
    with patch.object(ContainerExecutor, '_client', return_value=('docker',)), \
            patch.object(ContainerExecutor, '_capture') as capture, \
            patch('olympus.agent.container_execution.subprocess.run',
                return_value=subprocess.CompletedProcess([],0,json.dumps(record),'')) as inspect:
        result = ContainerExecutor().run(tmp_path, [sys.executable, '-c','pass'],1)
    assert result.returncode == 125 and not capture.called
    assert inspect.call_count == 1
    assert inspect.call_args.args[0][:3] == ['docker','image','inspect']


def test_real_host_cli_streams_are_drained_with_bounded_memory():
    # Reviewed synthetic CLI only, not a project and not a container OS claim.
    result = ContainerExecutor()._capture([sys.executable, '-c',
        'import sys;sys.stdout.write("a"*100000);sys.stderr.write("b"*100000)'], 5)
    assert result.returncode == 0
    assert len(result.stdout.encode()) <= 16000 and len(result.stderr.encode()) <= 16000


def test_real_host_cli_deadline_is_enforced():
    with pytest.raises(subprocess.TimeoutExpired):
        ContainerExecutor()._capture([sys.executable, '-c','import time;time.sleep(5)'], .1)


def test_snapshot_rejects_oversized_file(tmp_path):
    from olympus.agent import container_execution
    root = tmp_path/'project'; root.mkdir()
    (root/'large').write_text('x'*20)
    with patch.object(container_execution,'MAX_FILE',10), pytest.raises(IsolationUnavailable, match='snapshot exceeds limit'):
        snapshot_project(root, tmp_path/'snapshot')


def test_image_inspection_timeout_reports_unavailability_without_launching_code(tmp_path):
    with patch.object(ContainerExecutor, '_client', return_value=('docker',)), \
            patch.object(ContainerExecutor, '_capture') as capture, \
            patch('olympus.agent.container_execution.subprocess.run', side_effect=subprocess.TimeoutExpired('docker',10)) as inspection:
        result = ContainerExecutor().run(tmp_path,[sys.executable,'-c','pass'],10)
    assert result.returncode == 125
    assert 'image inspection exceeded deadline' in result.stderr
    assert not capture.called and inspection.call_count == 1


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('docker',10), OSError('daemon unavailable'),
    subprocess.CompletedProcess([],1,'','Cannot connect to Docker daemon'),
    subprocess.CompletedProcess([],1,'','No such container: somebody-else')])
def test_unconfirmed_cleanup_rejects_success_but_records_that_tests_ran(tmp_path, failure):
    def cleanup(*args,**kwargs):
        if isinstance(failure, BaseException): raise failure
        return failure
    with patch.object(ContainerExecutor, '_client', return_value=('docker',)), \
            patch.object(ContainerExecutor, '_image_id', return_value=IMAGE_ID), \
            patch.object(ContainerExecutor, '_capture', return_value=subprocess.CompletedProcess([],0,'passed','')), \
            patch('olympus.agent.container_execution.subprocess.run',side_effect=cleanup):
        result = run_tests(tmp_path,[sys.executable,'-c','pass'])
    assert result['returncode'] == 125 and result['ran'] is True
    assert 'execution_cleanup_unconfirmed: olympus-test-' in result['tail']


def test_cleanup_after_deadline_keeps_both_failure_diagnostics(tmp_path):
    with patch.object(ContainerExecutor, '_client', return_value=('docker',)), \
            patch.object(ContainerExecutor, '_image_id', return_value=IMAGE_ID), \
            patch.object(ContainerExecutor, '_capture', side_effect=subprocess.TimeoutExpired('docker',1)), \
            patch('olympus.agent.container_execution.subprocess.run',side_effect=OSError('daemon unavailable')):
        result = ContainerExecutor().run(tmp_path,[sys.executable,'-c','pass'],1)
    assert result.returncode == 124
    assert 'isolated test exceeded deadline' in result.stderr
    assert 'execution_cleanup_unconfirmed' in result.stderr


def test_auto_removed_owned_container_does_not_turn_success_into_failure(tmp_path):
    def cleanup(argv,**kwargs):
        return subprocess.CompletedProcess(argv,1,'','Error response from daemon: No such container: '+argv[-1])
    with patch.object(ContainerExecutor, '_client', return_value=('docker',)), \
            patch.object(ContainerExecutor, '_image_id', return_value=IMAGE_ID), \
            patch.object(ContainerExecutor, '_capture', return_value=subprocess.CompletedProcess([],0,'passed','')), \
            patch('olympus.agent.container_execution.subprocess.run',side_effect=cleanup):
        result = ContainerExecutor().run(tmp_path,[sys.executable,'-c','pass'],1)
    assert result.returncode == 0
    assert 'execution_cleanup_unconfirmed' not in result.stderr
