"""Private browser gate for static landing pages; remote errors fail closed."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_BYTES = 6 * 1024 * 1024


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact_command() -> str:
    """Fixed reader executed inside E2B; no generated code is run here."""
    script = r"""const fs=require('fs'),p=require('path'),c=require('crypto');
const root=fs.realpathSync('dist'),files=[];let total=0;
function walk(dir){for(const n of fs.readdirSync(dir).sort()){
 const file=p.join(dir,n),s=fs.lstatSync(file);
 if(s.isSymbolicLink())throw Error('symlink');
 if(s.isDirectory()){walk(file);continue;}
 const name=p.relative(root,file).split(p.sep).join('/');
 if(!s.isFile()||! /^[A-Za-z0-9_./-]+$/.test(name)||name.split('/').some(x=>!x||x.startsWith('.')))throw Error('path');
 if(!/\.(html|js|css|svg|png|jpe?g|webp|gif|ico|woff2?)$/.test(name))throw Error('unsupported_asset');
 const b=fs.readFileSync(file);total+=b.length;
 if(b.length>524288||total>4194304||files.length>=80)throw Error('size');
 files.push({path:name,content_base64:b.toString('base64'),sha256:c.createHash('sha256').update(b).digest('hex')});
}}
walk(root);console.log('OLYMPUS_DIST:'+JSON.stringify(files));"""
    return "node -e eval(Buffer.from('" + base64.b64encode(script.encode()).decode() + "','base64').toString('utf8'))"


class BrowserVerifier:
    def __init__(self, url: str, token: str):
        u = urlsplit(url)
        if (u.scheme != 'http' or not u.hostname or
                not (u.hostname.endswith('.railway.internal') or u.hostname in ('127.0.0.1', 'localhost')) or
                u.username or u.password or u.path not in ('', '/') or u.query or u.fragment):
            raise ValueError('Browser verifier must use a private origin')
        if len(token) < 24:
            raise ValueError('Browser verifier token required')
        self.url, self.token = url.rstrip('/'), token

    @classmethod
    def configured(cls):
        url = os.getenv('OLYMPUS_BROWSER_VERIFIER_URL')
        return cls(url, os.getenv('OLYMPUS_BROWSER_VERIFIER_TOKEN', '')) if url else None

    def verify(self, files: list, source_sha: str) -> dict:
        digest = hashlib.sha256()
        for f in sorted(files, key=lambda x: x['path']):
            digest.update(f['path'].encode() + b'\0')
            digest.update(bytes.fromhex(f['sha256']))
        nonce = secrets.token_hex(16)
        identity = dict(nonce=nonce, source_manifest_sha256=source_sha,
                        artifact_sha256=digest.hexdigest())
        data = json.dumps(dict(files=files, **identity)).encode()
        if len(data) > MAX_BYTES:
            raise ValueError('Browser input too large')
        req = Request(self.url + '/verify', data=data, headers={
            'Content-Type': 'application/json', 'X-Olympus-Browser-Token': self.token})
        with urlopen(req, timeout=120) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Browser response too large')
        result = json.loads(raw)
        if any(result.get(k) != v for k, v in identity.items()):
            raise ValueError('Browser evidence identity mismatch')
        validate_result(result)
        return result


def validate_result(result: dict) -> None:
    if result.get('schema') != 'olympus.browser.v1' or result.get('passed') is not True:
        raise ValueError('Independent browser verification did not pass')
    html = result.get('html')
    if not isinstance(html, str) or not html or _sha(html.encode()) != result.get('html_sha256'):
        raise ValueError('Verified HTML checksum mismatch')
    views = result.get('viewports')
    if not isinstance(views, list) or len(views) != 2:
        raise ValueError('Both browser viewports required')
    expected = [{'width': 1440, 'height': 900}, {'width': 390, 'height': 844}]
    if ([v.get('viewport') for v in views] != expected or
            any(v.get('passed') is not True or v.get('errors') != [] for v in views)):
        raise ValueError('Browser viewport checks failed')


def validate_receipt(root: Path, review: dict) -> bool:
    """Runtime binds the trusted runner receipt to the exact published bytes.

    This is an internal runner boundary, not cryptographic remote attestation.
    Model exports cannot create docs/ or the root published artifact in this mode.
    """
    try:
        receipt_path = root / 'docs/browser-verification.json'
        html_path = root / 'index.html'
        if receipt_path.is_symlink() or receipt_path.parent.is_symlink() or html_path.is_symlink():
            return False
        raw = receipt_path.read_bytes()
        if len(raw) > MAX_BYTES or _sha(raw) != review.get('receipt_sha256'):
            return False
        receipt = json.loads(raw)
        html = html_path.read_text(encoding='utf-8')
        validate_result(dict(receipt, html=html))
        digest = hashlib.sha256()
        source = root / 'source'
        if source.is_symlink() or not source.is_dir():
            return False
        for path in sorted(source.rglob('*'), key=lambda p: p.relative_to(source).as_posix()):
            if path.is_symlink():
                return False
            if not path.is_file():
                continue
            digest.update(path.relative_to(source).as_posix().encode() + b'\0')
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        if digest.hexdigest() != receipt.get('source_manifest_sha256'):
            return False
        return (review.get('browser') == 'passed_independent'
                and receipt.get('source_manifest_sha256') == review.get('export_sha256')
                and receipt.get('html_sha256') == review.get('published_html_sha256'))
    except (OSError, ValueError, TypeError, KeyError):
        return False
