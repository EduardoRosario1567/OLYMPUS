"""Independent rendered checks. A model statement never supplies browser evidence."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

APP_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class BrowserRuntime:
    modules: str
    executable: str = ''
    args: tuple = ()
    chromium_sandbox: bool = True

    @classmethod
    def default(cls):
        executable = os.environ.get('OLYMPUS_BROWSER_EXECUTABLE', '')
        chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        if not executable and sys.platform == 'darwin' and chrome.is_file():
            executable = str(chrome)
        return cls(str(APP_ROOT/'frontend/node_modules'), executable)


class WebDeliveryVerifier:
    def __init__(self, root, runtime=None, evidence_root=None):
        self.root = Path(root).resolve()
        self.runtime = runtime or BrowserRuntime.default()
        self.evidence_root = Path(evidence_root or APP_ROOT/'.olympus/delivery-reviews')
        self._cache = {}
        self._evidence_cache = {}

    def evidence_images(self, content_sha256):
        """Only privately captured, unchanged rasters may enter a vision request."""
        directory, artifacts = self._evidence_cache[content_sha256]
        images = []
        for artifact in artifacts:
            path = directory/ artifact['name']
            if path.is_symlink() or directory.is_symlink():
                raise ValueError('linked screenshot refused')
            with path.open('rb') as stream:
                data = stream.read(4*1024*1024+1)
            if len(data)>4*1024*1024 or hashlib.sha256(data).hexdigest() != artifact['sha256']:
                raise ValueError('screenshot evidence changed or exceeds limit')
            images.append('data:image/png;base64,'+base64.b64encode(data).decode('ascii'))
        return tuple(images)

    def content_matches(self, entrypoint, content_sha256):
        return self._digest(entrypoint) == content_sha256

    def _digest(self, entrypoint):
        digest = hashlib.sha256(entrypoint.encode())
        count = 0
        for path in sorted(self.root.rglob('*')):
            relative = path.relative_to(self.root)
            if any(part.startswith('.') or part in {'node_modules','venv','__pycache__','attachments','imports'} for part in relative.parts):
                continue
            if path.is_symlink():
                raise ValueError('linked delivery resource refused')
            if not path.is_file():
                continue
            if path.stat().st_size > 8*1024*1024:
                raise ValueError('delivery resource exceeds 8 MiB')
            count += 1
            if count > 1000:
                raise ValueError('delivery resource count exceeds limit')
            digest.update(relative.as_posix().encode()+b'\0'+path.read_bytes())
        return digest.hexdigest()

    def verify(self, entrypoint):
        baseline = {'profile':'web-v1','scope':'rendered_browser_checks','browser':'failed',
                    'layout':'not_assessed','visual':'not_assessed','viewports':[]}
        try:
            digest = self._digest(entrypoint)
            if digest in self._cache:
                return self._cache[digest]
            node = shutil.which('node')
            if not node or not (Path(self.runtime.modules)/'playwright/index.mjs').is_file():
                raise ValueError('browser_runtime_unavailable: existing Node/Playwright runtime required')
            if not self.evidence_root.is_absolute():
                self.evidence_root = self.evidence_root.resolve()
            for parent in (self.evidence_root, *self.evidence_root.parents):
                if parent.is_symlink():
                    raise ValueError('linked evidence directory refused')
            self.evidence_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            evidence = self.evidence_root/uuid.uuid4().hex
            evidence.mkdir(mode=0o700)
            config = {'root':str(self.root),'entrypoint':entrypoint,'modules':self.runtime.modules,
                      'executable':self.runtime.executable,'args':list(self.runtime.args),
                      'chromium_sandbox':self.runtime.chromium_sandbox,'evidence':str(evidence)}
            cache = os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or str(Path.home()/('Library/Caches/ms-playwright' if sys.platform=='darwin' else '.cache/ms-playwright'))
            with tempfile.TemporaryDirectory(prefix='olympus-browser-home-') as home:
                env = {'PATH':os.defpath,'HOME':home,'TMPDIR':home,'LANG':'C.UTF-8',
                       'PLAYWRIGHT_BROWSERS_PATH':cache}
                for name in ('LD_LIBRARY_PATH','FONTCONFIG_PATH','SYSTEMROOT'):
                    if name in os.environ: env[name] = os.environ[name]
                process = subprocess.run([node,str(Path(__file__).with_suffix('.mjs'))],
                    input=json.dumps(config),cwd=APP_ROOT,text=True,capture_output=True,
                    timeout=45,env=env,shell=False)
            if process.returncode:
                raise ValueError('browser_runtime_unavailable: browser could not start or complete the inspection')
            result = json.loads(process.stdout)
            if not isinstance(result,dict) or not isinstance(result.get('errors'),list) or len(result.get('viewports',[])) != 3:
                raise ValueError('browser returned invalid evidence')
            errors = tuple('browser delivery: '+str(item)[:350] for item in result['errors'][:20])
            review = dict(baseline,browser='failed' if errors else 'passed',layout='failed' if errors else 'passed',
                          content_sha256=digest,viewports=result['viewports'],interactions=result.get('interactions',[]),
                          browser_version=result.get('browser_version'),
                          browser_process_sandbox=self.runtime.chromium_sandbox)
            artifacts = []
            for path in sorted(evidence.glob('*.png')):
                artifacts.append({'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            review['artifacts'] = artifacts
            self._evidence_cache[digest] = evidence, tuple(dict(item) for item in artifacts)
            (evidence/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2))
            self._cache[digest] = errors,review
            return errors,review
        except (OSError,ValueError,TypeError,subprocess.TimeoutExpired):
            return ('browser_runtime_unavailable: rendered delivery could not be verified; do not publish',),baseline
