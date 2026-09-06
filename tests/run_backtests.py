#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = [20260907, 314159, 271828, 8675309, 424242, 999983, 13579, 24680, 112358, 161803, 777777, 888888, 123457, 765431, 555551]
ROUNDS_PER_RUN = 15


def main():
    runs=[]
    total_assertions=0
    total_rounds=0
    for index, seed in enumerate(SEEDS, 1):
        proc=subprocess.run(
            ['node','tests/backtest_search.js','--rounds',str(ROUNDS_PER_RUN),'--seed',str(seed)],
            cwd=ROOT,capture_output=True,text=True,timeout=120,
        )
        if proc.returncode:
            print(proc.stdout, file=sys.stderr); print(proc.stderr, file=sys.stderr)
            raise SystemExit(f'backtest run {index} failed (seed={seed})')
        lines=[line for line in proc.stdout.splitlines() if line.strip()]
        result=json.loads(lines[-1])
        if not result.get('ok'):
            raise SystemExit(f'backtest run {index} returned non-ok')
        result['run']=index
        runs.append(result)
        total_assertions += int(result['assertions'])
        total_rounds += int(result['rounds'])
        print(f"[PASS {index:02d}/{len(SEEDS)}] seed={seed} rounds={result['rounds']} cases={result['cases']} assertions={result['assertions']}")

    summary={
        'ok': True,
        'independent_runs': len(runs),
        'rounds_per_run': ROUNDS_PER_RUN,
        'total_rounds': total_rounds,
        'cases_per_round': runs[0]['cases'] if runs else 0,
        'total_assertions': total_assertions,
        'seeds': SEEDS,
        'runs': runs,
    }
    (ROOT/'BACKTEST_RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'},ensure_ascii=False))


if __name__ == '__main__': main()
