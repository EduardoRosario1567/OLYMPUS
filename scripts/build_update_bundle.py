#!/usr/bin/env python3
"""Build a tracked-source update bundle, excluding local state and credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import os
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.update_macos import IDENTITY, MANIFEST, MAX_BYTES, MAX_FILES, safe_name


def build(source, destination, paths, commit):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    files = {}
    seen = set()
    total = 0
    for relative in sorted(paths):
        safe_name(relative)
        if relative.lower() in seen:
            raise ValueError('Case collision in bundle')
        seen.add(relative.lower())
        path = source/relative
        for parent in [path, *path.parents]:
            if parent == source:
                break
            if parent.is_symlink():
                raise ValueError('Linked source refused')
        if not path.is_file():
            raise ValueError('Source file missing')
        data = path.read_bytes()
        total += len(data)
        if total > MAX_BYTES or relative in files:
            raise ValueError('Bundle size or duplicate path invalid')
        files[relative] = {'sha256':hashlib.sha256(data).hexdigest(),
                           'mode':0o755 if path.stat().st_mode & 0o111 else 0o644}
    if not files or len(files)>MAX_FILES:
        raise ValueError('File count invalid')
    identity = json.loads((source/IDENTITY).read_text())
    manifest = {'format':1,'product':'OLYMPUS','version':identity['version'],
                'build':identity['build'],'commit':commit,'files':files}
    destination.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary_name=tempfile.mkstemp(prefix='.olympus-bundle-',suffix='.zip',dir=destination.parent)
    os.close(descriptor)
    temporary=Path(temporary_name)
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for relative, record in files.items():
            data = (source/relative).read_bytes()
            if hashlib.sha256(data).hexdigest()!=record['sha256']:
                raise ValueError('Source changed during packaging')
            info = zipfile.ZipInfo('OLYMPUS-UPDATE/'+relative,date_time=(2026,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG|record['mode'])<<16
            archive.writestr(info,data)
        info=zipfile.ZipInfo('OLYMPUS-UPDATE/'+MANIFEST,date_time=(2026,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|0o644)<<16
        archive.writestr(info,json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    temporary.replace(destination)
    return manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    source=Path(__file__).resolve().parents[1]
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=source).decode().strip('\x00').split('\x00')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source).decode().strip()
    build(source,args.output,paths,commit)
    print(json.dumps({'status':'PASS','sha256':hashlib.sha256(Path(args.output).read_bytes()).hexdigest(),
                      'commit':commit,'file_count':len(paths)}))


if __name__=='__main__':
    main()
