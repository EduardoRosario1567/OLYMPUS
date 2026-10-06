#!/usr/bin/env python3
"""Transactional local source update. No state migration or broad process kill."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

MANIFEST = 'OLYMPUS-UPDATE-MANIFEST.json'
IDENTITY = 'frontend/public/olympus-version.json'
GENERATED = ('.venv', 'frontend/node_modules', 'frontend/.next')
PRIVATE_PARTS = {'.git', '.olympus', '.venv', 'node_modules', '.next', '__pycache__',
                 'projects', 'data', 'artifacts', 'history', 'credentials', 'secrets'}
PRIVATE_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.pyc', '.pem', '.key'}
MAX_FILES = 3000
MAX_BYTES = 100 * 1024 * 1024


class UpdateError(RuntimeError):
    pass


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or any(ord(char) < 32 for char in name):
        raise UpdateError('Caminho inválido no pacote.')
    relative = PurePosixPath(name)
    if relative.is_absolute() or relative.as_posix() != name or any(x in ('.', '..') for x in relative.parts):
        raise UpdateError('Caminho inválido no pacote.')
    if any(x.lower() in PRIVATE_PARTS for x in relative.parts):
        raise UpdateError('Dados persistentes não podem fazer parte da atualização.')
    if relative.suffix.lower() in PRIVATE_SUFFIXES:
        raise UpdateError('Estado ou segredo não pode fazer parte da atualização.')
    if relative.name.lower().startswith('.env') and relative.name not in ('.env.example', '.env.local.example'):
        raise UpdateError('Credenciais não podem fazer parte da atualização.')
    if name == MANIFEST:
        raise UpdateError('Nome reservado no pacote.')
    return name


def guarded(root, name):
    # Also used for controlled runtime paths that are not permitted in a payload.
    current = root
    for part in PurePosixPath(name).parts:
        if part in ('', '.', '..'):
            raise UpdateError('Caminho de instalação inválido.')
        current = current / part
        if current.is_symlink():
            raise UpdateError('Link no caminho da instalação; nenhuma substituição permitida.')
    return current


def atomic(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.olympus-update-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_payload(source):
    source = Path(source).resolve()
    manifest_path = guarded(source, MANIFEST)
    if manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise UpdateError('Manifesto muito grande.')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('format') != 1 or manifest.get('product') != 'OLYMPUS':
        raise UpdateError('Identidade de pacote inválida.')
    if not re.fullmatch('[a-f0-9]{40}', str(manifest.get('commit', ''))):
        raise UpdateError('Commit do pacote inválido.')
    files = manifest.get('files')
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise UpdateError('Lista de arquivos inválida.')
    result = {}
    case_names = set()
    total = 0
    for name, item in files.items():
        safe_name(name)
        if name.lower() in case_names:
            raise UpdateError('Caminhos colidem em sistema sem distinção de maiúsculas.')
        case_names.add(name.lower())
        if not isinstance(item, dict) or item.get('mode') not in (0o644, 0o755):
            raise UpdateError('Modo de arquivo inválido.')
        path = guarded(source, name)
        if not path.is_file():
            raise UpdateError('Arquivo do pacote ausente.')
        data = path.read_bytes()
        total += len(data)
        if total > MAX_BYTES or hashlib.sha256(data).hexdigest() != item.get('sha256'):
            raise UpdateError('Integridade do pacote inválida.')
        result[name] = (data, item['mode'])
    if IDENTITY not in result or 'start_olympus.command' not in result:
        raise UpdateError('Identidade ou inicializador ausente.')
    identity = json.loads(result[IDENTITY][0])
    if identity.get('product') != 'olympus' or identity.get('version') != manifest.get('version') or identity.get('build') != manifest.get('build'):
        raise UpdateError('Versão do pacote divergente.')
    return manifest, result


def protected_snapshot(root, managed):
    """Hash everything not managed by this source update; never follow links."""
    result = {}
    excluded = {'.git', '.venv', 'node_modules', '.next', '__pycache__', '.pytest_cache'}
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        rel = parent.relative_to(root).as_posix()
        if rel in ('.olympus/backups', '.olympus/runtime'):
            dirs[:] = []
            continue
        for name in list(dirs):
            path = parent / name
            if name in excluded:
                dirs.remove(name)
            elif path.is_symlink():
                result[path.relative_to(root).as_posix()] = ('link', os.readlink(path))
                dirs.remove(name)
        for name in files:
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if relative in managed:
                continue
            if path.is_symlink():
                result[relative] = ('link', os.readlink(path))
            elif path.is_file():
                result[relative] = ('file', digest(path), stat.S_IMODE(path.stat().st_mode))
    return result


def identity(root):
    try:
        value = json.loads(guarded(root, IDENTITY).read_text())
        if value.get('product') == 'olympus' and value.get('version') and value.get('build'):
            return value
    except (OSError, ValueError, UpdateError):
        pass
    raise UpdateError('Instalação OLYMPUS existente não identificada.')


class MacRuntime:
    def environment(self):
        # No provider/JWT/proxy/index credentials go to package installation.
        return {'PATH': os.environ.get('PATH', os.defpath), 'HOME': str(Path.home()),
                'TMPDIR': tempfile.gettempdir(), 'LANG': 'en_US.UTF-8',
                'PIP_CONFIG_FILE': os.devnull, 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
                'npm_config_userconfig': os.devnull, 'npm_config_globalconfig': os.devnull,
                'NEXT_TELEMETRY_DISABLED': '1'}

    def call(self, command, cwd=None, timeout=30):
        result = subprocess.run(command, cwd=cwd, env=self.environment(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, shell=False)
        if result.returncode:
            raise UpdateError('Comando de preparação ou serviço falhou; saída privada não exibida.')
        return result.stdout

    def listeners(self):
        values = []
        for port in (8000, 3000, 3001):
            query = subprocess.run(['lsof', '-nP', '-tiTCP:'+str(port), '-sTCP:LISTEN'],
                                   capture_output=True, text=True, timeout=10, env=self.environment())
            if query.returncode not in (0, 1):
                raise UpdateError('Não foi possível conferir as portas.')
            for raw in set(query.stdout.split()):
                if not raw.isdigit():
                    raise UpdateError('PID de serviço inválido.')
                output = self.call(['lsof', '-a', '-p', raw, '-d', 'cwd', '-Fn']).decode()
                cwd = next((line[1:] for line in output.splitlines() if line.startswith('n')), None)
                if not cwd:
                    raise UpdateError('Identidade do processo indisponível.')
                values.append((port, int(raw), Path(cwd).resolve()))
        return values

    def check_owned(self, target):
        records = self.listeners()
        for port, _, cwd in records:
            allowed = (target, target/'backend') if port == 8000 else (target/'frontend',)
            if cwd not in allowed:
                raise UpdateError('Porta ocupada por outra instalação ou aplicativo; nada será encerrado.')
        return records

    def preflight(self, source, target):
        if sys.platform != 'darwin':
            raise UpdateError('Este atualizador é exclusivo para macOS.')
        for tool in ('python3', 'node', 'npm', 'lsof', 'docker'):
            if not shutil.which(tool):
                raise UpdateError('Componente necessário não instalado: '+tool)
        current = identity(target)
        if current['version'] not in ('3.0.8', '3.0.9'):
            raise UpdateError('Esta atualização exige a base 3.0.8 ou 3.0.9 identificada.')
        if not guarded(target, 'backend/.env').is_file():
            raise UpdateError('Credenciais existentes não localizadas; instalação preservada.')
        python = guarded(target, '.venv')/'bin/python'
        if not python.is_file():
            raise UpdateError('Python da instalação existente não localizado.')
        version = tuple(int(x) for x in self.call(['node', '-p', 'process.versions.node']).decode().strip().split('.')[:3])
        if version < (20, 9, 0):
            raise UpdateError('Node 20.9 ou superior é necessário.')
        self.call([str(python), '-c', 'import yaml,sqlalchemy; import sys; assert sys.version_info >= (3,9)'])
        socket = next((p for p in (Path('/var/run/docker.sock'), Path.home()/'.docker/run/docker.sock')
                       if p.exists() and stat.S_ISSOCK(p.stat().st_mode)), None)
        if socket is None:
            raise UpdateError('Docker local não disponível; nenhum arquivo da instalação foi alterado.')
        self.docker = (shutil.which('docker'), '--host', 'unix://'+str(socket))
        self.call([*self.docker, 'version'])
        self.check_owned(target)

    def provision(self, source, target):
        self.call([str(target/'.venv/bin/python'), str(source/'scripts/verify_preview_lock.py'),
                   str(source/'containers/preview-runtime.package.json'), str(source/'containers/preview-runtime.package-lock.json')])
        roles = (
            ('python-base.txt', 'RUNNER_BASE', 'project-runner.Dockerfile', 'olympus-project-runner:3.0.8-candidate'),
            ('node-base.txt', 'NODE_BASE', 'preview-runner.Dockerfile', 'olympus-preview-runner:3.0.8-candidate'))
        previous = {}
        changed = []
        for _, _, _, tag in roles:
            result = subprocess.run([*self.docker,'image','inspect',tag,'--format','{{.Id}}'],
                capture_output=True,text=True,env=self.environment(),timeout=20)
            value=result.stdout.strip()
            if result.returncode==0 and re.fullmatch('sha256:[a-f0-9]{64}',value):
                previous[tag]=value
            elif result.returncode==1:
                previous[tag]=None
            else:
                raise UpdateError('Identidade da imagem anterior não confirmada.')
        try:
            for name, arg, dockerfile, tag in roles:
                base = (source/'containers'/name).read_text().strip()
                prefix = 'python' if arg=='RUNNER_BASE' else 'node'
                if not re.fullmatch(prefix+r'@sha256:[a-f0-9]{64}', base):
                    raise UpdateError('Base Docker não fixada.')
                self.call([*self.docker, 'pull', base], timeout=600)
                changed.append(tag)
                self.call([*self.docker, 'build', '--pull=false', '--build-arg', arg+'='+base,
                           '-t', tag, '-f', str(source/'containers'/dockerfile), str(source/'containers')], timeout=900)
            for script in ('container_isolation_gate.py', 'preview_isolation_gate.py'):
                output = self.call([str(target/'.venv/bin/python'), str(source/'scripts'/script)], cwd=source, timeout=180)
                report = json.loads(output)
                if report.get('status') != 'PASS':
                    raise UpdateError('As imagens locais não passaram na prova real de isolamento.')
        except BaseException as failure:
            errors=[]
            for tag in reversed(changed):
                try:
                    if previous[tag] is not None:
                        self.call([*self.docker,'tag',previous[tag],tag])
                    else:
                        self.call([*self.docker,'image','rm','--no-prune',tag])
                except Exception:
                    errors.append(tag)
            if errors:
                raise UpdateError('Preparação das imagens falhou; código da instalação preservado, confira as imagens locais.') from failure
            raise UpdateError('Preparação das imagens falhou; identidades anteriores restauradas e código preservado.') from failure

    def stop(self, target):
        records = self.check_owned(target)
        for port, pid, cwd in records:
            # Recheck PID, port and CWD immediately before TERM. Never kill OmniRoute.
            if (port, pid, cwd) not in self.check_owned(target):
                continue
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic()+20
        while self.check_owned(target):
            if time.monotonic() >= deadline:
                raise UpdateError('Serviço não encerrou com segurança; atualização interrompida.')
            time.sleep(.25)

    def install_dependencies(self, target):
        self.call(['python3', '-m', 'venv', str(target/'.venv')], timeout=90)
        self.call([str(target/'.venv/bin/python'), '-m', 'pip', 'install', '-r', str(target/'requirements-core.txt'),
                   '-r', str(target/'backend/requirements.txt')], timeout=600)
        self.call(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=target/'frontend', timeout=600)

    def start(self, target):
        self.check_owned(target)
        self.call(['bash', str(target/'start_olympus.command')], cwd=target, timeout=300)

    def confirm(self, target, expected):
        self.check_owned(target)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for url in ('http://127.0.0.1:8000/health', 'http://127.0.0.1:3000/olympus-version.json'):
            with opener.open(url+'?ts='+str(time.time_ns()), timeout=5) as response:
                value = json.load(response)
            if value.get('version') != expected['version'] or value.get('build') != expected['build']:
                raise UpdateError('Serviço não confirmou a versão e o build exatos.')
        ports={port for port,_,_ in self.check_owned(target)}
        if not {8000,3000}.issubset(ports) or 3001 in ports:
            raise UpdateError('Serviços esperados não ficaram nas portas corretas.')


def discover_target(runtime):
    candidates = set()
    for _, _, cwd in runtime.listeners():
        roots = (cwd, cwd.parent) if cwd.name in ('frontend', 'backend') else (cwd,)
        for root in roots:
            try:
                identity(root)
                candidates.add(root)
            except UpdateError:
                pass
    if len(candidates) == 1:
        return next(iter(candidates))
    if candidates:
        raise UpdateError('Backend e frontend pertencem a instalações diferentes; selecione --target.')
    for parent in (Path.home()/'Documents', Path.home()/'Projects'):
        for path in parent.glob('OLYMPUS*'):
            if path.is_symlink():
                continue
            try:
                identity(path)
                candidates.add(path.resolve())
            except UpdateError:
                pass
    if len(candidates) != 1:
        raise UpdateError('Pasta única não identificada; informe --target sem criar outra instalação.')
    return next(iter(candidates))



def recover_transactions(target, runtime):
    """Recover a hard interruption only when code/data still match the journal."""
    for backup in guarded(target, '.olympus/backups').glob('UPDATE-*'):
        if backup.is_symlink() or not backup.is_dir():
            raise UpdateError('Backup vinculado ou inválido; recuperação bloqueada.')
        transaction = guarded(backup, 'transaction.json')
        result_path = guarded(backup, 'result.json')
        if not transaction.is_file():
            continue
        if result_path.is_file():
            if json.loads(result_path.read_text()).get('status') == 'ROLLBACK_INCOMPLETE':
                raise UpdateError('Atualização anterior interrompida com alteração concorrente; backup preservado: '+str(backup))
            continue
        record = json.loads(transaction.read_text())
        previous = record.get('files')
        wanted = record.get('target_files')
        generated = record.get('generated_existed')
        if not isinstance(previous,dict) or not isinstance(wanted,dict) or not isinstance(generated,dict) or set(previous)!=set(wanted):
            raise UpdateError('Atualização anterior interrompida; diário insuficiente e backup preservado: '+str(backup))
        for name, item in previous.items():
            safe_name(name)
            path=guarded(target,name)
            current=digest(path) if path.is_file() else None
            if current not in (item['sha256'],wanted[name]['sha256']):
                raise UpdateError('Código concorrente após interrupção; backup preservado: '+str(backup))
            if item['existed'] and (not guarded(backup,'code/'+name).is_file() or digest(backup/'code'/name)!=item['sha256']):
                raise UpdateError('Backup de código divergente; recuperação bloqueada.')
        for name in GENERATED:
            guarded(target,name);old=guarded(backup,'dependencies/'+name)
            if generated.get(name) and not old.is_dir() and not guarded(target,name).is_dir():
                raise UpdateError('Dependências anteriores não localizadas; backup preservado.')
        runtime.stop(target)
        hashes=guarded(backup,'protected-hashes.json')
        if hashes.is_file() and json.loads(hashes.read_text())!=json.loads(json.dumps(protected_snapshot(target,set(previous)))):
            raise UpdateError('Dados concorrentes após interrupção; não serão sobrescritos. Backup: '+str(backup))
        for name,item in previous.items():
            path=guarded(target,name)
            if (digest(path) if path.is_file() else None)!=wanted[name]['sha256']:
                continue
            if item['existed']:
                atomic(path,(backup/'code'/name).read_bytes(),item['mode'])
            else:
                path.unlink()
        for name in reversed(GENERATED):
            path=guarded(target,name);old=guarded(backup,'dependencies/'+name)
            if old.is_dir() or not generated.get(name):
                if path.exists():
                    if not path.is_dir():
                        raise UpdateError('Dependência não é diretório; backup preservado.')
                    shutil.rmtree(path)
                if old.is_dir():
                    path.parent.mkdir(parents=True,exist_ok=True);old.rename(path)
        runtime.start(target)
        runtime.confirm(target,record['previous_identity'])
        atomic(result_path,b'{"status":"RECOVERED_AFTER_INTERRUPTION"}\n',0o600)


def apply_update(source, target, runtime):
    source = Path(source).resolve()
    raw_target = Path(target).expanduser()
    if raw_target.is_symlink():
        raise UpdateError('Pasta vinculada não suportada.')
    target = raw_target.resolve()
    if source == target or target in source.parents:
        raise UpdateError('O pacote deve ficar fora da instalação existente.')
    manifest, payload = read_payload(source)
    # Templates can contain local values; preserve an existing template as data.
    payload = {name:value for name,value in payload.items()
               if not (Path(name).name in ('.env.example','.env.local.example')
                       and guarded(target,name).exists())}
    previous_identity = identity(target)
    for name in payload:
        path = guarded(target, name)
        if path.exists() and not path.is_file():
            raise UpdateError('Destino de código não é um arquivo regular.')
    for name in (*GENERATED, '.olympus', '.olympus/backups', '.olympus/runtime'):
        guarded(target, name)
    lock_path = guarded(target, '.olympus/runtime/update.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpdateError('Outra atualização está em andamento.')
        recover_transactions(target, runtime)
        previous_identity = identity(target)
        runtime.preflight(source, target)
        # Image installation and actual isolation proof happen before code mutation.
        runtime.provision(source, target)
        try:
            runtime.stop(target)
            backup = guarded(target, '.olympus/backups') / ('UPDATE-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
            backup.mkdir(parents=True, mode=0o700)
            old = {}
            for name in payload:
                path = guarded(target, name)
                old[name] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) if path.is_file() else (None, payload[name][1])
                if old[name][0] is not None:
                    atomic(backup/'code'/name, *old[name])
            atomic(backup/'transaction.json', (json.dumps({'status':'PREPARED', 'commit':manifest['commit'],
                'previous_identity':previous_identity, 'target_files':{name:manifest['files'][name] for name in payload},
                'generated_existed':{name:guarded(target,name).is_dir() for name in GENERATED}, 'files':{n:{'existed':v[0] is not None,'sha256':hashlib.sha256(v[0]).hexdigest() if v[0] is not None else None,'mode':v[1]} for n,v in old.items()}},indent=2)+'\n').encode(), 0o600)
            protected = protected_snapshot(target, set(payload))
            for name, record in protected.items():
                if record[0] == 'file':
                    path = guarded(target, name)
                    if digest(path) != record[1]:
                        raise UpdateError('Dados mudaram durante o backup; atualização interrompida.')
                    content=path.read_bytes()
                    if hashlib.sha256(content).hexdigest()!=record[1]:
                        raise UpdateError('Dados mudaram durante a cópia de backup.')
                    atomic(backup/'persistent'/name, content, record[2])
            atomic(backup/'protected-hashes.json', (json.dumps(protected,sort_keys=True)+'\n').encode(),0o600)
            if protected_snapshot(target, set(payload)) != protected:
                raise UpdateError('Dados mudaram durante o backup; atualização interrompida.')
        except Exception as failure:
            try:
                runtime.start(target)
                runtime.confirm(target, previous_identity)
            except Exception:
                raise UpdateError('Preparação interrompida; código anterior preservado, serviços não confirmados.') from failure
            raise UpdateError('Preparação interrompida; instalação anterior preservada e reiniciada.') from failure
        moved = []
        prepared = []
        written = []
        try:
            for name in GENERATED:
                path = guarded(target, name)
                if path.exists():
                    if not path.is_dir():
                        raise UpdateError('Dependência existente não é diretório regular.')
                    destination = backup/'dependencies'/name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    path.rename(destination)
                    moved.append(name)
                prepared.append(name)
            for name, (content, mode) in payload.items():
                path = guarded(target, name)
                current = path.read_bytes() if path.is_file() else None
                if current != old[name][0]:
                    raise UpdateError('Código alterado durante a atualização; mudança concorrente preservada.')
                written.append(name)
                atomic(path, content, mode)
            runtime.install_dependencies(target)
            if protected_snapshot(target, set(payload)) != protected:
                raise UpdateError('Dados persistentes divergiram antes do reinício.')
            runtime.start(target)
            runtime.confirm(target, manifest)
            if protected_snapshot(target, set(payload)) != protected:
                raise UpdateError('Dados persistentes divergiram após o reinício.')
            for name, (content, _) in payload.items():
                if guarded(target, name).read_bytes() != content:
                    raise UpdateError('Código aplicado divergiu após reinício.')
            atomic(backup/'result.json', b'{"status":"PASS"}\n', 0o600)
            return {'status':'PASS','version':manifest['version'],'build':manifest['build'],
                    'commit':manifest['commit'],'target':str(target),'backup':str(backup),
                    'protected_files':len(protected),'replaced_files':len(written)}
        except BaseException as failure:
            errors = []
            try:
                runtime.stop(target)
            except Exception:
                errors.append('services')
            if errors:
                atomic(backup/'result.json', b'{"status":"ROLLBACK_INCOMPLETE","errors":["services"]}\n',0o600)
                raise UpdateError('Serviço não pôde ser encerrado; código atual e backup preservados: '+str(backup)) from failure
            # Never overwrite a concurrent code change during rollback.
            for name in reversed(written):
                path = guarded(target, name)
                try:
                    current = path.read_bytes() if path.is_file() else None
                    if current == old[name][0]:
                        if current is not None:
                            os.chmod(path,old[name][1])
                        continue
                    if current != payload[name][0]:
                        raise UpdateError('Código concorrente preservado.')
                    original, mode = old[name]
                    if original is None:
                        path.unlink()
                    else:
                        atomic(path, original, mode)
                except Exception:
                    errors.append(name)
            for name in reversed(prepared):
                try:
                    path = guarded(target, name)
                    if path.exists():
                        if not path.is_dir():
                            raise UpdateError('Dependência não é diretório.')
                        shutil.rmtree(path)
                    if name in moved:
                        (backup/'dependencies'/name).rename(path)
                except Exception:
                    errors.append(name)
            if protected_snapshot(target, set(payload)) != protected:
                errors.append('persistent_data_changed')
            if not errors:
                try:
                    runtime.start(target)
                    runtime.confirm(target, previous_identity)
                except Exception:
                    errors.append('previous_services')
            atomic(backup/'result.json', (json.dumps({'status':'ROLLBACK_INCOMPLETE' if errors else 'ROLLED_BACK','errors':errors})+'\n').encode(), 0o600)
            if errors:
                raise UpdateError('Reversão incompleta; alterações concorrentes preservadas. Backup: '+str(backup)) from failure
            raise UpdateError('Atualização não aprovada; código e dependências anteriores restaurados. Backup: '+str(backup)) from failure


def main():
    parser = argparse.ArgumentParser(description='Atualizar a instalação existente do Olympus com backup e reversão.')
    parser.add_argument('--source', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--target')
    args = parser.parse_args()
    runtime = MacRuntime()
    if sys.platform != 'darwin':
        raise UpdateError('Este atualizador é exclusivo para macOS.')
    target = Path(args.target).expanduser() if args.target else discover_target(runtime)
    print(json.dumps(apply_update(args.source, target, runtime), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except UpdateError as error:
        print('ATUALIZAÇÃO BLOQUEADA: '+str(error), file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError, subprocess.SubprocessError):
        # No chained stderr/environment or private command output is printed.
        print('ATUALIZAÇÃO BLOQUEADA. Preserve a instalação anterior e os backups.', file=sys.stderr)
        raise SystemExit(1)
