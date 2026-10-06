"""Real filesystem/leases, controlled Docker boundary; no OS-isolation claim."""
import gc
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from olympus.cloud.preview_container import PreviewContainerExecutor, PreviewLifecycleError, PREVIEW_OWNER
from olympus.agent.container_execution import IsolationUnavailable, ContainerExecutor
from tests import test_preview_container as fixture
CLIENT = fixture.CLIENT


class PreviewRecoveryTests(unittest.TestCase):
    setUp = fixture.PreviewContainerTests.setUp
    force_cleanup = fixture.PreviewContainerTests.force_cleanup
    start = fixture.PreviewContainerTests.start

    def restart(self):
        # Simulate process death: kernel releases the lease, not the snapshot.
        self.executor._journal.release()
        self.call_patch.stop()
        self.executor = PreviewContainerExecutor(journal_root=Path(self.tmp.name)/'journal')
        self.call_patch = patch.object(self.executor, '_call', side_effect=self.docker)
        self.call_patch.start()
        self.addCleanup(self.call_patch.stop)
        self.addCleanup(self.force_cleanup)

    def test_restart_removes_verified_old_execution_and_filtered_snapshot(self):
        (self.root/'.env').write_text('SYNTHETIC_CREDENTIAL')
        handle = self.start()
        workspace = Path(handle.temporary.name)
        self.restart()
        del handle
        gc.collect()
        self.assertTrue(workspace.exists())
        self.executor.recover()
        self.assertIsNone(self.docker.record)
        self.assertFalse(workspace.exists())
        self.assertEqual(self.executor.pending(), ())
        self.assertEqual((self.root/'.env').read_text(), 'SYNTHETIC_CREDENTIAL')
        self.assertEqual((self.root/'package.json').read_text(), '{}')

    def test_registration_is_private_durable_and_precedes_docker_create(self):
        original = self.docker.__call__
        def inspect_registration(client, *args):
            if args[0] == 'create':
                name = args[args.index('--name') + 1]
                path = Path(self.tmp.name)/'journal'/(name+'.json')
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(set(json.loads(path.read_text())), {'name','image_id'})
                self.assertTrue((path.parent/name/'project/package.json').exists())
            return original(client, *args)
        with patch.object(self.executor, '_call', side_effect=inspect_registration):
            self.start()

    def test_foreign_owner_blocks_recovery_and_new_creation(self):
        handle = self.start()
        self.restart()
        self.docker.fail = 'foreign_owner'
        calls = len(self.docker.calls)
        with self.assertRaisesRegex(PreviewLifecycleError, 'cleanup_unconfirmed'):
            self.start()
        self.assertTrue(Path(handle.temporary.name).exists())
        self.assertFalse(any(args[0] in {'rm','create'} for _,args in self.docker.calls[calls:]))
        self.assertEqual(len(self.executor.pending()), 1)

    def test_failed_cleanup_survives_two_restarts_then_retries(self):
        handle = self.start()
        self.docker.fail = 'remove_failure'
        for _ in range(2):
            self.restart()
            with self.assertRaises(PreviewLifecycleError):
                self.executor.recover()
            self.assertTrue(Path(handle.temporary.name).exists())
            self.assertTrue((Path(self.tmp.name)/'journal'/(handle.name+'.json')).exists())
        self.docker.fail = None
        self.executor.recover()
        self.assertFalse(Path(handle.temporary.name).exists())

    def test_concurrent_executor_cannot_remove_active_container(self):
        self.start()
        second = PreviewContainerExecutor(journal_root=Path(self.tmp.name)/'journal')
        with patch.object(second, '_call', side_effect=self.docker):
            calls = len(self.docker.calls)
            with self.assertRaises(OSError):
                second.recover(CLIENT)
            self.assertEqual(len(self.docker.calls), calls)
        self.assertIsNotNone(self.docker.record)
        second.close()

    def test_missing_docker_retains_recovery_registration(self):
        handle = self.start()
        self.restart()
        with patch.object(ContainerExecutor, '_client', side_effect=IsolationUnavailable('Docker unavailable')):
            with self.assertRaises(IsolationUnavailable):
                self.executor.recover()
        self.assertTrue(Path(handle.temporary.name).exists())
        self.assertIsNotNone(self.docker.record)
        self.executor.recover()

    def test_tampered_record_does_not_follow_arbitrary_path(self):
        handle = self.start()
        self.restart()
        path = Path(self.tmp.name)/'journal'/(handle.name+'.json')
        original = path.read_text()
        value = json.loads(original)
        value['workspace'] = str(self.root)
        path.write_text(json.dumps(value))
        calls = len(self.docker.calls)
        with self.assertRaises(IsolationUnavailable):
            self.executor.recover()
        self.assertEqual(len(self.docker.calls), calls)
        self.assertTrue((self.root/'package.json').exists())
        path.write_text(original)
        self.executor.recover()

    def test_symlink_registration_is_not_read_or_removed(self):
        handle = self.start()
        self.restart()
        path = Path(self.tmp.name)/'journal'/(handle.name+'.json')
        original = path.read_text()
        path.unlink()
        path.symlink_to(self.root/'package.json')
        with self.assertRaises(OSError):
            self.executor.recover()
        self.assertEqual((self.root/'package.json').read_text(), '{}')
        path.unlink()
        path.write_text(original)
        path.chmod(0o600)
        self.executor.recover()

    def test_record_without_workspace_recovers_interrupted_allocation(self):
        self.executor.recover(CLIENT)
        name = 'olympus-preview-' + 'c'*32
        path = Path(self.tmp.name)/'journal'/(name+'.json')
        path.write_text(json.dumps({'name':name,'image_id':'sha256:'+'a'*64}))
        path.chmod(0o600)
        self.restart()
        self.executor.recover()
        self.assertFalse(path.exists())

    def test_close_keeps_lease_when_removal_is_unconfirmed(self):
        handle = self.start()
        self.docker.fail = 'remove_failure'
        self.executor.close()
        self.assertIsNotNone(self.executor._journal.lease)
        self.assertFalse(handle.cleanup_confirmed)
        self.docker.fail = None
        self.executor.close()
        self.assertIsNone(self.executor._journal.lease)

    def test_snapshot_cleanup_failure_keeps_record_until_retry(self):
        handle = self.start()
        with patch.object(handle.temporary, 'cleanup', side_effect=OSError('fixture disk failure')):
            self.assertFalse(self.executor.stop(handle))
        self.assertIsNone(self.docker.record)
        self.assertFalse(handle.cleanup_confirmed)
        self.assertTrue((Path(self.tmp.name)/'journal'/(handle.name+'.json')).exists())
        self.assertTrue(self.executor.stop(handle))
        self.assertFalse(Path(handle.temporary.name).exists())

    def test_incomplete_record_blocks_without_docker_mutation(self):
        self.executor.recover(CLIENT)
        path = Path(self.tmp.name)/'journal'/('olympus-preview-'+'d'*32+'.json')
        path.write_text('{')
        path.chmod(0o600)
        self.restart()
        calls = len(self.docker.calls)
        with self.assertRaises(IsolationUnavailable):
            self.executor.recover()
        self.assertEqual(len(self.docker.calls), calls)
        self.assertTrue(path.exists())
        path.unlink()

    def test_registration_write_failure_never_creates_docker_container(self):
        with patch('olympus.cloud.preview_journal.os.fsync', side_effect=OSError('fixture disk failure')):
            with self.assertRaises(PreviewLifecycleError):
                self.start()
        self.assertFalse(any(args[0]=='create' for _,args in self.docker.calls))
        self.assertFalse(self.executor._recovered)
        self.executor.recover()
        self.assertEqual(self.executor._journal.records(), {})

    def test_linked_journal_root_is_refused_without_docker_commands(self):
        link = Path(self.tmp.name)/'linked-journal'
        link.symlink_to(self.root, target_is_directory=True)
        second = PreviewContainerExecutor(journal_root=link)
        with patch.object(second, '_call', side_effect=self.docker):
            calls = len(self.docker.calls)
            with self.assertRaises(IsolationUnavailable):
                second.recover(CLIENT)
            self.assertEqual(len(self.docker.calls), calls)
        self.assertEqual((self.root/'package.json').read_text(), '{}')
        second.close()
