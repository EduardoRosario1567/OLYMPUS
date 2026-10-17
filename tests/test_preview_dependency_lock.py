"""Packaging must reject registry substitution and dependency-lock tampering."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.verify_preview_lock import verify

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'containers/preview-runtime.package.json'
LOCK = ROOT / 'containers/preview-runtime.package-lock.json'


class PreviewDependencyLockTests(unittest.TestCase):
    def test_reviewed_lock_is_complete(self):
        result = verify(PACKAGE, LOCK)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['direct_dependencies']['next'], '16.3.8')
        self.assertEqual(result['direct_dependencies']['vite'], '8.2.4')

    def test_tampered_dependencies_are_rejected(self):
        original = json.loads(LOCK.read_text())
        cases = ('foreign_registry', 'missing_integrity', 'bad_direct_version',
                 'linked_package', 'path_escape', 'vite_outside_range', 'root_mismatch')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                bad = copy.deepcopy(original)
                record = bad['packages']['node_modules/next']
                if case == 'foreign_registry':
                    record['resolved'] = 'https://attacker.invalid/next.tgz'
                elif case == 'missing_integrity':
                    record.pop('integrity')
                elif case == 'bad_direct_version':
                    record['version'] = '1.0.0'
                elif case == 'linked_package':
                    record['link'] = True
                elif case == 'path_escape':
                    bad['packages']['node_modules/../escape'] = record
                elif case == 'vite_outside_range':
                    bad['packages']['node_modules/vite']['version'] = '9.0.0'
                else:
                    bad['packages']['']['dependencies']['next'] = '1.0.0'
                path = Path(directory) / 'package-lock.json'
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    verify(PACKAGE, path)
