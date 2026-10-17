#!/usr/bin/env python3
"""Verify bounded ZIP paths, modes and all update hashes; execute no archive code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.update_macos import MANIFEST, MAX_FILES, MAX_BYTES, UpdateError, safe_name, read_payload


def verify(archive_path):
    with zipfile.ZipFile(archive_path) as archive, tempfile.TemporaryDirectory(prefix='olympus-bundle-check-') as directory:
        root=Path(directory)/'OLYMPUS-UPDATE';root.mkdir()
        names=set();total=0
        entries=archive.infolist()
        if not 1<=len(entries)<=MAX_FILES+1:
            raise UpdateError('Quantidade de arquivos do ZIP inválida.')
        for entry in entries:
            raw=entry.filename
            if not raw.startswith('OLYMPUS-UPDATE/') or entry.is_dir():
                raise UpdateError('Raiz do ZIP inválida.')
            name=raw[len('OLYMPUS-UPDATE/'):]
            if name!=MANIFEST:safe_name(name)
            if name.lower() in names:
                raise UpdateError('Entrada repetida ou colisão no ZIP.')
            names.add(name.lower())
            mode=entry.external_attr>>16
            if not stat.S_ISREG(mode) or stat.S_IMODE(mode) not in (0o644,0o755):
                raise UpdateError('Tipo ou permissão de entrada do ZIP inválidos.')
            total+=entry.file_size
            if total>MAX_BYTES+2*1024*1024:
                raise UpdateError('ZIP excede limite de tamanho.')
            target=root.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.read(entry))
            target.chmod(stat.S_IMODE(mode))
        manifest,payload=read_payload(root)
        if names!={n.lower() for n in payload}|{MANIFEST.lower()}:
            raise UpdateError('ZIP contém arquivos fora do manifesto.')
        for name,(_,mode) in payload.items():
            if stat.S_IMODE((root/name).stat().st_mode)!=mode:
                raise UpdateError('Modo da entrada difere do manifesto.')
        return {'status':'PASS','commit':manifest['commit'],'version':manifest['version'],
                'build':manifest['build'],'file_count':len(payload),
                'archive_sha256':hashlib.sha256(Path(archive_path).read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('archive');args=parser.parse_args()
    print(json.dumps(verify(args.archive),sort_keys=True))


if __name__=='__main__':main()
