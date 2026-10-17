"""Run installer guards with controlled OS/runtime boundaries, never install."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def installer(tmp_path, node_version, existing=False):
    home = tmp_path / 'home'
    home.mkdir()
    if existing:
        marker = home / 'Documents/OLYMPUS-PILOTO-2.6.2/frontend/public/olympus-version.json'
        marker.parent.mkdir(parents=True)
        marker.write_text('{"product":"olympus","version":"2.6.2"}')
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    scripts = {
        'uname': '#!/bin/sh\necho Darwin\n',
        'ditto': '#!/bin/sh\ntouch "$HOME/copied"\n',
        'node': '#!' + sys.executable + '\nimport os,subprocess,sys\nraise SystemExit(subprocess.call([os.environ["REAL_NODE"],"-e", "Object.defineProperty(process.versions, \'node\', {value: "+repr(os.environ["SYNTHETIC_NODE_VERSION"])+"});"+sys.argv[2]]))\n',
    }
    for name, content in scripts.items():
        path = binaries/name
        path.write_text(content)
        path.chmod(0o700)
    env = dict(os.environ, HOME=str(home), PATH=str(binaries) + os.pathsep + os.environ['PATH'],
               REAL_NODE=shutil.which('node'), SYNTHETIC_NODE_VERSION=node_version)
    result = subprocess.run(['bash', str(ROOT/'INSTALAR-OLYMPUS.command')], env=env,
                            input='\n', text=True, capture_output=True, timeout=10)
    return result, home


def test_node18_is_rejected_before_copy(tmp_path):
    result, home = installer(tmp_path, '18.0.0')
    assert result.returncode != 0
    assert not (home/'copied').exists()


def test_supported_node_does_not_create_second_installation(tmp_path):
    result, home = installer(tmp_path, '20.9.0', existing=True)
    assert result.returncode != 0
    assert not (home/'copied').exists()
    assert len(list((home/'Documents').iterdir())) == 1
