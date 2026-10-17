"""Import credited Commons candidates as local assets without arbitrary URLs."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct

from olympus.agent.delivery_sources import DeliverySources


def import_asset(root, target, payload):
    if not isinstance(payload, dict):
        raise ValueError('import_asset requires a Commons File: title')
    title = str(payload.get('title') or '')
    if not title.startswith('File:') or not 6 <= len(title) <= 220 or any(c in title for c in '\r\n|'):
        raise ValueError('invalid Commons file title')
    if not re.fullmatch(r'assets/[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp)', str(target)):
        raise ValueError('import_asset target must be a flat assets/ image path')
    root = Path(root).resolve()
    directory = root / 'assets'
    if directory.is_symlink():
        raise ValueError('linked asset directory refused')
    path = root / target
    credit_path = root / (target + '.source.json')
    if path.exists() or path.is_symlink() or credit_path.exists() or credit_path.is_symlink():
        raise ValueError('asset target already exists; choose a new filename')
    sources = DeliverySources()
    try:
        results = sources.search('images', {'query': title, 'language': 'en'})['results']
        candidate = next(item for item in results if item['title'] == title)
        mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}[path.suffix]
        body = sources._image_bytes(candidate['image_url'], mime)
    except Exception:
        raise ValueError('licensed image unavailable; use supplied assets or an honest text composition') from None
    if not body or len(body) > 8 * 1024 * 1024:
        raise ValueError('empty or oversized image')
    valid = False
    if mime == 'image/png' and len(body) >= 45:
        valid = body.startswith(b'\x89PNG\r\n\x1a\n') and body[12:16] == b'IHDR' and body[-12:-8] == b'\x00\x00\x00\x00' and body[-8:-4] == b'IEND'
        width, height = struct.unpack('>II', body[16:24])
        valid = valid and 0 < width <= 8000 and 0 < height <= 8000 and width * height <= 16_000_000
    elif mime == 'image/jpeg':
        valid = body.startswith(b'\xff\xd8\xff') and body.endswith(b'\xff\xd9')
    elif mime == 'image/webp' and len(body) >= 20:
        valid = body[:4] == b'RIFF' and body[8:12] == b'WEBP' and struct.unpack('<I', body[4:8])[0] + 8 == len(body)
    if not valid:
        raise ValueError('image signature or dimensions rejected')
    credit = dict(candidate, local_path=target, sha256=hashlib.sha256(body).hexdigest(),
                  signature_checked=True, decoded_in_browser=False, visual_reviewed=False)
    directory.mkdir(exist_ok=True)
    created = []
    try:
        for destination, content in ((path, body), (credit_path, (json.dumps(credit, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))):
            with os.fdopen(os.open(str(destination), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                created.append(destination)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except Exception:
        for destination in created:
            destination.unlink(missing_ok=True)
        raise
    return credit
