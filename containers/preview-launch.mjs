// Reviewed image entrypoint contract. Never invoke package.json scripts.
import { cpSync, existsSync, mkdirSync, symlinkSync } from 'node:fs';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const binaries = {
  next: ['next/dist/bin/next', 'dev', '--webpack', '--hostname', '127.0.0.1', '--port', '3000'],
  vite: ['vite/bin/vite.js', '--host', '127.0.0.1', '--port', '3000', '--strictPort'],
  react: ['react-scripts/scripts/start.js'],
};

export function validateArguments(args) {
  if (args.length !== 2 || !Object.hasOwn(binaries, args[0])) throw new Error('Unsupported preview framework');
  const relative = args[1];
  if (typeof relative !== 'string' || !relative || relative.includes('\\') || relative.includes('\0') ||
      path.posix.isAbsolute(relative) || (relative !== '.' && (
        relative.split('/').some(part => !part || part.startsWith('.')) || path.posix.normalize(relative) !== relative))) {
    throw new Error('Invalid preview package path');
  }
  return {
    cwd: path.posix.join('/work/project', relative),
    command: '/opt/olympus-preview/node_modules/' + binaries[args[0]][0],
    args: binaries[args[0]].slice(1),
  };
}

export function launch(args) {
  const specification = validateArguments(args);
  if (!existsSync(specification.command)) throw new Error('Approved framework dependency is absent');
  mkdirSync('/work/project', { mode: 0o700 });
  cpSync('/snapshot', '/work/project', { recursive: true, force: false, errorOnExist: true });
  if (!existsSync(path.join(specification.cwd, 'package.json'))) throw new Error('Project package is absent');
  symlinkSync('/opt/olympus-preview/node_modules', path.join(specification.cwd, 'node_modules'), 'dir');
  const child = spawn(process.execPath, [specification.command, ...specification.args], {
    cwd: specification.cwd, shell: false, stdio: ['ignore', 'inherit', 'inherit'],
    env: { PATH: '/usr/local/bin:/usr/bin:/bin', HOME: '/tmp', TMPDIR: '/tmp',
      HOST: '127.0.0.1', PORT: '3000', NODE_ENV: 'development', NO_COLOR: '1',
      NEXT_TELEMETRY_DISABLED: '1', BROWSER: 'none' },
  });
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => child.kill(signal));
  child.on('error', () => { console.error('Preview process failed to start'); process.exitCode = 1; });
  child.on('exit', code => { process.exitCode = Number.isInteger(code) ? code : 1; });
  return child;
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try { launch(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
