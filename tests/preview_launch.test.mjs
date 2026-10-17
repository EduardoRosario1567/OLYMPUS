import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { validateArguments } from '../containers/preview-launch.mjs';

test('Rejects unsupported commands and malformed package paths', () => {
  for (const framework of ['node', 'next && curl', '__proto__', 'constructor', 'npm']) {
    assert.throws(() => validateArguments([framework, '.']));
  }
  for (const relative of ['/tmp', '../escape', 'app/../escape', '.env', 'app/.git',
    'app//src', 'app/', 'app/./src', 'app\\src', 'app\0src', '', undefined]) {
    assert.throws(() => validateArguments(['next', relative]));
  }
  for (const args of [[], ['next'], ['next', '.', '--eval=payload']]) {
    assert.throws(() => validateArguments(args));
  }
});

test('Framework executables stay in approved image and working paths stay in private copy', () => {
  for (const framework of ['next', 'vite', 'react']) {
    for (const relative of ['.', 'app', 'frontend/src', 'with spaces']) {
      const specification = validateArguments([framework, relative]);
      assert.ok(specification.command.startsWith('/opt/olympus-preview/node_modules/'));
      assert.ok(specification.cwd.startsWith('/work/project'));
      assert.ok(!specification.args.includes(relative));
    }
  }
});

test('CLI refuses injected framework before accessing a project or spawning a server', () => {
  const result = spawnSync(process.execPath, [fileURLToPath(new URL('../containers/preview-launch.mjs', import.meta.url)),
    'next && echo payload', '.'], { encoding: 'utf8', timeout: 5000 });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Unsupported preview framework/);
  assert.equal(result.stdout, '');
});
