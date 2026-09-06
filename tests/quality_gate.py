"""Fail closed. Every release runs the complete gate before ZIP creation."""
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GENERATED={'QUALITY_GATE_RESULTS.json','QUALITY_REPORT.md','BACKTEST_RESULTS.json','REVIEW_RESULTS.json','E2E_RESULTS.json','PACKAGE_RESULTS.json'}

def fingerprint(root=ROOT):
    digest=hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.name in GENERATED or p.suffix in ('.pyc','.png','.zip','.sha256') or p.name.startswith('REVIEW_RESULTS_'):continue
        digest.update(p.relative_to(root).as_posix().encode());digest.update(p.read_bytes())
    return digest.hexdigest()

def main():
    os.environ['PYTHONUTF8']='1';os.environ['PYTHONDONTWRITEBYTECODE']='1'
    stages=[
      ('regression',[sys.executable,'-X','utf8','-m','unittest','discover','-s','tests','-q']),
      ('search_contracts',['node','tests/search_contracts.js']),
      ('sdk_contract',[sys.executable,'-X','utf8','tests/sdk_contract.py']),
      ('browser_workflows',[sys.executable,'-X','utf8','tests/e2e_app.py']),
      ('browser_resilience',[sys.executable,'-X','utf8','tests/e2e_resilience.py']),
      ('backtests',[sys.executable,'-X','utf8','tests/run_backtests.py']),
      ('reviews',[sys.executable,'-X','utf8','tests/run_reviews.py']),
    ]
    rows=[]
    for name,args in stages:
        print(f'[RUN] {name}',flush=True)
        try:
            p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=240)
            output=(p.stdout+'\n'+p.stderr).strip()
            row={'stage':name,'ok':p.returncode==0,'output':output}
        except Exception as e:row={'stage':name,'ok':False,'output':type(e).__name__}
        rows.append(row)
        print(f"[{'PASS' if row['ok'] else 'FAIL'}] {name}",flush=True)
        if not row['ok']:
            print(row['output']);break
    summary={'ok':len(rows)==len(stages) and all(r['ok'] for r in rows),'checked_at':datetime.now(timezone.utc).isoformat(),'fingerprint':fingerprint(),'stages':rows}
    (ROOT/'QUALITY_GATE_RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not summary['ok']:raise SystemExit(1)
    print(json.dumps({'ok':True,'stages':len(rows),'fingerprint':summary['fingerprint']}))

if __name__=='__main__':main()
