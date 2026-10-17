#!/usr/bin/env python3
"""Fail-closed P3 overlay for pinned original firecrawl/open-lovable, in a disposable checkout.
No secrets, no provider calls, no original API route execution. Not production authentication.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import stat
import subprocess

PIN = "806b8072f28afea11fa2b028cac1449eff74c511"
PATTERN = re.compile(
    r"(?P<indent>^[ \t]*)console\.log\('\[generate-ai-code-stream\] Groq service unavailable, falling back to GPT-4'\);[ \t]*\n"
    r"[ \t]*streamOptions\.model = openai\('gpt-4-turbo'\);[ \t]*\n"
    r"[ \t]*actualModel = 'gpt-4-turbo';", re.M)
MIDDLEWARE = """// Qualification overlay only: deny ALL upstream APIs except local health proof.
import { NextRequest, NextResponse } from 'next/server';
export function middleware(request: NextRequest) {
  if (request.method === 'GET' && request.nextUrl.pathname === '/api/olympus-p3-proof')
    return NextResponse.next();
  return NextResponse.json({status:'BLOCKED', reason:'OLYMPUS_P3_NO_API_NO_INFERENCE'},
    {status:503, headers:{'Cache-Control':'no-store'}});
}
export const config = {matcher:['/api/:path*']};
"""
PROOF = """import { NextResponse } from 'next/server';
export const dynamic = 'force-dynamic';
export async function GET() {
  const id = process.env.OLYMPUS_INSTANCE_ID;
  if (!id || !/^[a-z0-9-]{8,64}$/.test(id))
    return NextResponse.json({status:'BLOCKED'}, {status:503});
  return NextResponse.json({status:'ISOLATED_SMOKE',instanceId:id},
    {headers:{'Cache-Control':'no-store'}});
}
"""
DOCKERIGNORE = """.git
.next
node_modules
.env
.env.*
*.pem
*.key
*.p12
*.pfx
*.sqlite*
*.db
coverage
"""
class Blocked(RuntimeError):
    pass

def regular(root: Path, rel: str, limit=10*1024*1024) -> Path:
    node = root
    for part in Path(rel).parts:
        node = node / part
        if node.is_symlink():
            raise Blocked("SYMLINK_BLOCKED:" + rel)
    if not node.is_file() or not stat.S_ISREG(node.stat().st_mode) or node.stat().st_size > limit:
        raise Blocked("SOURCE_INVALID:" + rel)
    return node

def apply(root: Path, verify_git=True):
    root = root.resolve(strict=True)
    if verify_git:
        try:
            head = subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],
                check=True,capture_output=True,text=True,timeout=8).stdout.strip()
            dirty = subprocess.run(['git','-C',str(root),'status','--porcelain'],
                check=True,capture_output=True,text=True,timeout=8).stdout
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise Blocked('GIT_PROOF_UNAVAILABLE') from e
        if head != PIN or dirty.strip():
            raise Blocked('UPSTREAM_PIN_OR_CLEANLINESS_MISMATCH')
    for rel in ('LICENSE','package.json','package-lock.json'):
        regular(root, rel)
    source = regular(root,'app/api/generate-ai-code-stream/route.ts', 1024*1024)
    original = source.read_text(encoding='utf-8')
    matches = list(PATTERN.finditer(original))
    if len(matches) != 1:
        raise Blocked('PAID_FALLBACK_SOURCE_CHANGED')
    if 'OLYMPUS_P3_PAID_FALLBACK_BLOCKED' in original:
        raise Blocked('ALREADY_PATCHED')
    for path in (root/'middleware.ts',root/'src'/'middleware.ts',
                 root/'app'/'api'/'olympus-p3-proof',root/'.dockerignore'):
        if path.exists() or path.is_symlink():
            raise Blocked('UNREVIEWED_GUARD_CONFLICT:' + str(path))
    # Only modify the disposable checkout after all preflight checks pass.
    source.write_text(PATTERN.sub(lambda match:
        match.group('indent') + "// OLYMPUS P3: reject potential paid fallback.\n"
        + match.group('indent') + "throw new Error('OLYMPUS_P3_PAID_FALLBACK_BLOCKED');",
        original),encoding='utf-8')
    (root/'middleware.ts').write_text(MIDDLEWARE,encoding='utf-8')
    proof = root/'app'/'api'/'olympus-p3-proof'
    proof.mkdir(parents=True)
    (proof/'route.ts').write_text(PROOF,encoding='utf-8')
    (root/'.dockerignore').write_text(DOCKERIGNORE,encoding='utf-8')
    if "openai('gpt-4-turbo')" in source.read_text(encoding='utf-8'):
        raise Blocked('FALLBACK_STILL_PRESENT')
    return {'status':'SOURCE_GUARDED','pin':PIN,'model_calls':0,'scope':'NO_INFERENCE'}

def main():
    arg = argparse.ArgumentParser()
    arg.add_argument('checkout')
    try:
        data = apply(Path(arg.parse_args().checkout))
        print(json.dumps(data))
        return 0
    except (Blocked, OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)}))
        return 2
if __name__ == '__main__':
    raise SystemExit(main())
