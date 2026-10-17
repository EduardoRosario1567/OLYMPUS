import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('p3guard', ROOT/'p3'/'prepare_upstream.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
FALLBACK = """const streamOptions = {};
  console.log('[generate-ai-code-stream] Groq service unavailable, falling back to GPT-4');
  streamOptions.model = openai('gpt-4-turbo');
  actualModel = 'gpt-4-turbo';
"""

def fixture(root, source=FALLBACK):
    files = {'LICENSE': 'MIT License', 'package.json':'{}',
             'package-lock.json':'{}', 'app/api/generate-ai-code-stream/route.ts':source}
    for path, body in files.items():
        target = root/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body,encoding='utf-8')

class P3SourceQualification(unittest.TestCase):
    def test_overlay_disables_fallback_and_all_orig_apis(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); fixture(root)
            result=guard.apply(root,verify_git=False)
            self.assertEqual(result['status'],'SOURCE_GUARDED')
            self.assertNotIn("openai('gpt-4-turbo')",
              (root/'app/api/generate-ai-code-stream/route.ts').read_text())
            middleware=(root/'middleware.ts').read_text()
            self.assertIn("matcher:['/api/:path*']",middleware)
            self.assertIn("OLYMPUS_P3_NO_API_NO_INFERENCE",middleware)
            self.assertIn('OLYMPUS_INSTANCE_ID',(root/'app/api/olympus-p3-proof/route.ts').read_text())

    def test_changed_source_is_blocked(self):
        for source in ('',FALLBACK+FALLBACK,FALLBACK.replace('gpt-4-turbo','gpt-4o')):
            with self.subTest(source=source[:20]),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);fixture(root,source)
                with self.assertRaises(guard.Blocked):guard.apply(root,verify_git=False)
                self.assertFalse((root/'middleware.ts').exists())

    def test_preexisting_guard_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixture(root)
            (root/'middleware.ts').write_text('conflict')
            with self.assertRaises(guard.Blocked):guard.apply(root,verify_git=False)

    def test_duplicate_overlay_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixture(root)
            guard.apply(root,verify_git=False)
            with self.assertRaises(guard.Blocked):guard.apply(root,verify_git=False)

    def test_symlink_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixture(root)
            file=root/'app/api/generate-ai-code-stream/route.ts'
            file.unlink();file.symlink_to(root/'package.json')
            with self.assertRaises(guard.Blocked):guard.apply(root,verify_git=False)

    def test_unpinned_or_non_git_dir_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixture(root)
            with self.assertRaises(guard.Blocked):guard.apply(root,verify_git=True)

    def test_shell_is_valid_and_sandboxed(self):
        script=ROOT/'p3/smoke_two_containers.sh'
        subprocess.run(['bash','-n',str(script)],check=True)
        source=script.read_text()
        for flag in ('--network=none','--read-only','--cap-drop=ALL','--memory=768m',
                     '--cpus=1','--pids-limit=128','--pull=never'):
            self.assertIn(flag,source)

if __name__=='__main__':unittest.main()
