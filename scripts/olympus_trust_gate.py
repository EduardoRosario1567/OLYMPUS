#!/usr/bin/env python3
import json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = []

def run(name, cmd):
    started=time.time()
    p=subprocess.run(cmd, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    checks.append({"name":name,"pass":p.returncode==0,"seconds":round(time.time()-started,3),"output":p.stdout[-4000:]})
    return p.returncode==0

ok=True
ok &= run("security_regression", [sys.executable,"-W","error::ResourceWarning","-m","unittest","tests.test_trust_boundary_v1","-q"])
ok &= run("full_regression", [sys.executable,"-W","error::ResourceWarning","-m","unittest","discover","-s","tests","-q"])
report={"schema":"olympus.trust-report.v1","status":"VERIFIED" if ok else "BLOCKED","critical_failures":sum(1 for c in checks if not c["pass"]),"checks":checks}
out=ROOT/"docs"/"trust"/"latest-trust-report.json"
out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print("OLYMPUS TRUST GATE")
for c in checks: print(f"{c['name']:<24} {'PASS' if c['pass'] else 'FAIL'}")
print(f"CRITICAL FAILURES         {report['critical_failures']}")
print(f"STATUS                    {report['status']}")
sys.exit(0 if ok else 1)
