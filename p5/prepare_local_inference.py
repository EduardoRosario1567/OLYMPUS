#!/usr/bin/env python3
"""Apply a pinned P5 local-only inference overlay to the disposable Open Lovable checkout.

Reuses P3 source verification and paid-fallback blocker. Does not change
OLYMPUS production routes, and is not a multi-tenant production ingress.
"""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from p3.prepare_upstream import apply as apply_p3, Blocked, PIN

MIDDLEWARE = """import { NextRequest, NextResponse } from 'next/server';
// Qualification only. This app has NO published port and lives on an internal Docker network.
export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (path === '/api/olympus-p3-proof' && request.method === 'GET')
    return NextResponse.next();
  if (path === '/api/generate-ai-code-stream' && request.method === 'POST'
    && process.env.OLYMPUS_P5_LOCAL_ONLY === '1'
    && !!process.env.OLYMPUS_P5_GATE_TOKEN
    && request.headers.get('x-olympus-p5-internal') === process.env.OLYMPUS_P5_GATE_TOKEN)
    return NextResponse.next();
  return NextResponse.json({status:'BLOCKED',reason:'OLYMPUS_P5_UNAUTHORIZED_OR_UNSAFE_ROUTE'},
    {status:503,headers:{'Cache-Control':'no-store'}});
}
export const config = {matcher:['/api/:path*']};
"""

def overlay(root: Path, *, git_check=True):
    result = apply_p3(root, verify_git=git_check)
    if result["status"] != "SOURCE_GUARDED":
        raise Blocked("P3_GUARD_NOT_APPLIED")
    root = root.resolve(strict=True)
    source = root / 'app/api/generate-ai-code-stream/route.ts'
    text = source.read_text(encoding='utf-8')
    signature = "const { prompt, model = 'openai/gpt-oss-20b', context, isEdit = false } = await request.json();"
    guard = """
    if (process.env.OLYMPUS_P5_LOCAL_ONLY === '1' &&
        (model !== 'openai/qwen2.5-coder:0.5b' || isEdit ||
         typeof prompt !== 'string' || prompt.length > 4000)) {
      return NextResponse.json({status:'BLOCKED',reason:'OLYMPUS_P5_LOCAL_MODEL_ONLY'}, {status:403});
    }
"""
    if text.count(signature) != 1:
        raise Blocked('P5_EXPECTED_MODEL_SIGNATURE_CHANGED')
    text = text.replace(signature, signature + guard)
    choice = 'model: modelProvider(actualModel),'
    replacement = """model: process.env.OLYMPUS_P5_LOCAL_ONLY === '1'
            ? openai.chat(actualModel) : modelProvider(actualModel),"""
    if text.count(choice) != 1:
        raise Blocked('P5_PROVIDER_ROUTE_SIGNATURE_CHANGED')
    text = text.replace(choice, replacement)
    if text.count("maxTokens: 8192,") != 1:
        raise Blocked('P5_TOKEN_LIMIT_SIGNATURE_CHANGED')
    text = text.replace("maxTokens: 8192,",
         "maxTokens: process.env.OLYMPUS_P5_LOCAL_ONLY === '1' ? 2048 : 8192,")
    if text.count("if (isOpenAI) {") != 1:
        raise Blocked('P5_OPENAI_METADATA_SIGNATURE_CHANGED')
    text = text.replace("if (isOpenAI) {",
        "if (isOpenAI && process.env.OLYMPUS_P5_LOCAL_ONLY !== '1') {")
    source.write_text(text, encoding='utf-8')
    (root/'middleware.ts').write_text(MIDDLEWARE,encoding='utf-8')
    return {"status":"GUARDED_LOCAL_INFERENCE_CANDIDATE","upstream_pin":PIN,
            "model_allowlist":["openai/qwen2.5-coder:0.5b"],
            "original_model_calls":0,"paid_fallback_blocked":True}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('upstream')
    args=parser.parse_args()
    try:
        print(json.dumps(overlay(Path(args.upstream)),sort_keys=True))
        return 0
    except (Blocked,OSError,ValueError) as e:
        print(json.dumps({"status":"BLOCKED","reason":str(e)}))
        return 2

if __name__=='__main__':
    raise SystemExit(main())
