/**
 * Drop-in endpoint for a dedicated Open Lovable upstream fork.
 * NOT active in vanilla firecrawl/open-lovable or current Railway pilot.
 * Requires private-network routing plus OLYMPUS_BRIDGE_EXPORT_TOKEN.
 * The upstream's global activeSandboxProvider is still single-session only.
 */
import { createHash, timingSafeEqual } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { sandboxManager } from '@/lib/sandbox/sandbox-manager';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MAX_FILES = 80;
const MAX_TOTAL = 3 * 1024 * 1024;
const MAX_ONE = 512 * 1024;
const ALLOWED = /^(?:src|public)\/[A-Za-z0-9_.\-/]+\.(?:jsx?|tsx?|css|json|svg|md|html)$|^(?:index\.html|package(?:-lock)?\.json|vite\.config\.(?:js|ts)|postcss\.config\.(?:js|ts)|tailwind\.config\.(?:js|ts)|tsconfig\.json)$/;
const sha256 = (input: Buffer) => createHash('sha256').update(input).digest('hex');

function deny(status: number, error: string) {
  return NextResponse.json({ success: false, error }, { status });
}
function authenticate(request: NextRequest): boolean {
  const expected = process.env.OLYMPUS_BRIDGE_EXPORT_TOKEN;
  const actual = request.headers.get('x-olympus-bridge-token');
  if (!expected || expected.length < 32 || !actual) return false;
  const a = Buffer.from(actual, 'utf8'), b = Buffer.from(expected, 'utf8');
  return a.length === b.length && timingSafeEqual(a, b);
}
function validPath(path: string): boolean {
  return path.length < 220 && !path.startsWith('/') &&
    !path.includes('\\') && !path.includes(':') &&
    !path.includes('//') && !path.split('/').some(s => !s || s.startsWith('.')) &&
    ALLOWED.test(path);
}

export async function POST(request: NextRequest) {
  if (!process.env.OLYMPUS_BRIDGE_EXPORT_TOKEN) return deny(503, 'bridge_not_configured');
  if (!authenticate(request)) return deny(401, 'unauthorized');
  let body: { sandboxId?: unknown };
  try {
    body = await request.json();
  } catch {
    return deny(400, 'invalid_json');
  }
  const id = body?.sandboxId;
  if (typeof id !== 'string' || !/^[A-Za-z0-9_\-]{3,200}$/.test(id)) {
    return deny(400, 'invalid_sandbox_id');
  }
  const provider = sandboxManager.getActiveProvider() || global.activeSandboxProvider;
  if (!provider || provider.getSandboxInfo()?.sandboxId !== id) {
    return deny(409, 'sandbox_identity_mismatch');
  }
  try {
    const all = await provider.listFiles();
    if (!Array.isArray(all) || all.length === 0) return deny(409, 'sandbox_empty');
    // Never silently return incomplete files. Reject non-text assets until
    // there is a dedicated authenticated binary snapshot protocol.
    const selected: string[] = [];
    for (const candidate of all) {
      if (typeof candidate !== 'string') return deny(422, 'unsafe_path');
      if (!candidate.startsWith('src/') && !candidate.startsWith('public/') &&
          !['index.html','package.json','package-lock.json','tsconfig.json',
            'vite.config.js','vite.config.ts','postcss.config.js','postcss.config.ts',
            'tailwind.config.js','tailwind.config.ts'].includes(candidate)) continue;
      if (!validPath(candidate)) return deny(422, 'unsupported_or_unsafe_asset');
      if (selected.includes(candidate)) return deny(422, 'duplicate_export_path');
      selected.push(candidate);
    }
    if (!selected.length || selected.length > MAX_FILES) return deny(413, 'too_many_files');
    const files: {path: string; content: string; sha256: string}[] = [];
    let total = 0;
    for (const name of selected.sort()) {
      // Canonical path must remain under app. E2B runCommand's outer exitCode
      // is not reliable; parse its embedded realpath result.
      const check = await provider.runCommand('realpath ' + name);
      const lines = String(check.stdout || '').split('\n').map((x: string) => x.trim());
      const absolute = lines.find((x: string) => x.startsWith('/')) || '';
      if (!lines.some((x: string) => x === 'Return code: 0') ||
          !absolute.startsWith('/home/user/app/') ||
          !absolute.endsWith('/' + name)) return deny(422, 'unsafe_or_linked_file');
      // The original E2B readFile uses print(content), adding a newline.
      // Base64 stdout preserves actual source bytes from the compiled sandbox.
      const encoded = await provider.runCommand('base64 ' + name);
      const transcript = String(encoded.stdout || '');
      const match = transcript.match(/STDOUT:\s*([A-Za-z0-9+/=\s]+?)\s*Return code:\s*0\s*$/);
      if (!match) return deny(422, 'file_read_failed');
      const data = Buffer.from(match[1].replace(/\s/g, ''), 'base64');
      const content = data.toString('utf8');
      if (!Buffer.from(content, 'utf8').equals(data)) return deny(422, 'non_utf8_asset');
      if (data.length > MAX_ONE || (total += data.length) > MAX_TOTAL)
        return deny(413, 'export_size_limit');
      files.push({ path: name, content, sha256: sha256(data) });
    }
    if (provider.getSandboxInfo()?.sandboxId !== id ||
        (sandboxManager.getActiveProvider() || global.activeSandboxProvider) !== provider) {
      return deny(409, 'sandbox_changed_during_export');
    }
    const projectHash = createHash('sha256');
    for (const file of files) {
      projectHash.update(Buffer.from(file.path, 'utf8'));
      projectHash.update(Buffer.from([0]));
      projectHash.update(Buffer.from(file.sha256, 'hex'));
    }
    return NextResponse.json({
      success: true, sandboxId: id, files, sha256: projectHash.digest('hex')
    }, { headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return deny(500, 'sandbox_export_failed');
  }
}
