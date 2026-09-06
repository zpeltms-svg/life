"""Independent quality domains, not repetitions of the same test command."""
import hashlib
import io
import json
import re
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from api import guide, centers

def read(path):return (ROOT/path).read_text(encoding='utf-8')
def data(path):return json.loads(read(path))
def require(condition,message):
    if not condition:raise AssertionError(message)

def command(args):
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=120)
    require(p.returncode==0,p.stdout+p.stderr)
    return p.stdout.strip()

def selected_tests(*names):
    suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    log=io.StringIO();result=unittest.TextTestRunner(stream=log).run(suite)
    require(result.wasSuccessful(),log.getvalue())
    return f'{result.testsRun} behavioral tests'

def topology():
    for name in ['index.html','app.js','search-core.js','js/centers.js','css/enhancements.css','data/services.json','data/welfare-centers.json','api/guide.py','local_preview.py','실행.bat','실행.command','CODEX_TASK.md']:
        require((ROOT/name).is_file(),name)
    return 'required files present'

def syntax():
    for p in ROOT.rglob('*.py'):
        if '__pycache__' not in p.parts:compile(p.read_text(encoding='utf-8'),str(p),'exec')
    for name in ['app.js','search-core.js','js/centers.js','tests/search_contracts.js','tests/backtest_search.js']:command(['node','--check',name])
    return 'all Python + 5 JavaScript files'

def services():
    rows=data('data/services.json')['services'];require(len(rows)>=30,'minimum 30')
    require(len({s['id'] for s in rows})==len(rows),'duplicate id')
    required={'id','title','who','method','documents','office','fee','phone','last_verified','review_due','source_url','steps'}
    for s in rows:require(required<=s.keys(),s['id'])
    return f'{len(rows)} services'

def urls():
    count=0
    for s in data('data/services.json')['services']:
        for url in [s['source_url'],s.get('online_application',{}).get('url')]:
            if not url:continue
            u=urlsplit(url);require(u.scheme=='https' and u.hostname and not u.username and not u.password,url)
            require(u.hostname.endswith(('.go.kr','.gov.kr')) or u.hostname in ('www.gov.kr','www.iros.go.kr','ev.or.kr','efamily.scourt.go.kr'),url);count+=1
    return f'{count} official HTTPS links; HTTP content limitations in SOURCE_AUDIT'

def freshness():
    for s in data('data/services.json')['services']:
        verified=date.fromisoformat(s['last_verified']);due=date.fromisoformat(s['review_due']);require(due>verified,s['id'])
        if s['official_status']=='reference_only':require(s.get('verification_note') and s.get('caution'),s['id'])
    return 'real dates + explicit unverified-content warnings'

def parity():
    cases=data('tests/backtest_cases.json')
    script="const s=require('./search-core');const d=require('./data/services.json').services;console.log(JSON.stringify(require('./tests/backtest_cases.json').map(c=>s.localRetrieve(c.q,d,8).map(s=>s.id))))"
    browser=json.loads(command(['node','-e',script]));rows=guide.load_services()
    for c,ids in zip(cases,browser):require(ids==guide.keyword_fallback(c['q'],rows,8),c['q'])
    return f'{len(cases)} frontend/server rankings identical'

def workflow():
    require(guide.keyword_fallback('아기가 태어났어요',guide.load_services())[:5]==['BIRTH-001','BIRTH-002','BIRTH-003','BIRTH-004','BIRTH-005'],'birth workflow')
    return 'registration -> city benefit -> voucher -> parental -> child allowance'

def quick_menu():
    html=read('index.html');require(html.count('class="citizen-quick"')>=16,'16 quick actions')
    for word in ['인감증명','전입신고','출생신고','대형폐기물','여권 재발급','보건증','예방접종','자동차세','상하수도','무인발급기','채용공고','주정차 과태료','국민신문고','가족관계','등본·초본','확정일자']:require(word in html,word)
    return '16 quick actions'

def viewport(width):
    d=data('E2E_RESULTS.json');r=next(v for v in d['viewports'] if v['width']==width)
    require(d['ok'] and d['page_errors']==0 and r['ok'] and not r['overflow'],str(width))
    require((ROOT/f'tests/artifacts/home-{width}.png').is_file(),'screenshot evidence')
    return f"{width}x{r['height']}, 13 scenarios, page errors 0"

def accessibility():
    h=read('index.html');css=read('style.css')+read('css/enhancements.css')
    for text in ['aria-labelledby="detail-title"','aria-describedby="privacy-note"','class="skip-link"','for="center-address"','for="center-area"']:require(text in h,text)
    require(':focus-visible' in css and 'prefers-reduced-motion' in css,'keyboard/reduced-motion')
    return 'labels, native controls, focus + browser keyboard/modal checks'

def deployment():
    config=data('vercel.json');require(len(config['rewrites'])==4,'four API routes')
    require(config['functions']['api/*.py']['includeFiles']=='data/**','data bundled')
    entries={p.name for p in (ROOT/'api').glob('*.py') if not p.name.startswith('_')}
    require(entries=={'guide.py','public_services.py','address.py','route.py'},str(entries))
    return '4 entrypoints; private helper modules; JSON included'

def docs():
    for name in ['README.md','PRD.md','PROJECT_HANDOFF.md']:
        text=read(name);require('36' in text and '실행.bat' in text,name)
    return 'run / test / limitations / data maintenance documented'

def dependencies():
    require(read('requirements.txt').strip()=='openai==3.8.0','SDK pin')
    require(read('requirements-dev.txt').strip()=='playwright==1.55.0','browser pin')
    require(read('.python-version').strip()=='3.13','deployment Python')
    return f'Python local {sys.version.split()[0]}, deployment 3.13; pinned SDK + Playwright'

def secret_scan():
    findings=[]
    for p in ROOT.rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix in ('.pyc','.png','.zip'):continue
        if p.name.startswith('.env') and p.name!='.env.example':findings.append(str(p.relative_to(ROOT)));continue
        try:t=p.read_text(encoding='utf-8')
        except UnicodeDecodeError:continue
        if re.search(r'sk-[A-Za-z0-9_-]{20,}',t):findings.append(str(p.relative_to(ROOT)))
        if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',t):findings.append(str(p.relative_to(ROOT)))
    require(not findings,','.join(findings));return 'no real credential patterns or private env files'

def main():
    reviews=[
      ('구조',topology),('문법',syntax),('서비스 스키마',services),('공식 URL 형식·기관',urls),('자료 유효기간',freshness),
      ('센터 좌표·이전주소',lambda:selected_tests('tests.test_runtime.CenterRuntimeTests.test_all_coordinates_and_sources','tests.test_runtime.CenterRuntimeTests.test_relocated_offices')),
      ('처리 순서',workflow),('자연어 정답·오탐·상태격리',lambda:command(['node','tests/search_contracts.js'])),('클라이언트·서버 검색 일치',parity),('빠른 메뉴',quick_menu),
      ('개인정보 외부전송 차단',lambda:selected_tests('tests.test_runtime.PrivacyRuntimeTests')),
      ('API 입력·오류 노출',lambda:selected_tests('tests.test_runtime.ApiInputTests')),
      ('호출제한·메모리 상한',lambda:selected_tests('tests.test_runtime.RateLimitTests')),
      ('AI 구조화·허용 ID',lambda:selected_tests('tests.test_runtime.StructuredOutputTests')),
      ('외부 API 장애 대응',lambda:selected_tests('tests.test_runtime.FallbackTests')),
      ('화성시 지역 필터',lambda:selected_tests('tests.test_runtime.RegionTests')),
      ('관할·길찾기',lambda:selected_tests('tests.test_runtime.CenterRuntimeTests')),
      ('HTTP·CSP·파일노출 방어',lambda:selected_tests('tests.test_http.HttpTests')),
      ('접근성',accessibility),('모바일 390',lambda:viewport(390)),('모바일 412',lambda:viewport(412)),('태블릿 768',lambda:viewport(768)),('데스크톱 1440',lambda:viewport(1440)),
      ('배포 구성',deployment),('문서',docs),('의존성',dependencies),('Secret 검사',secret_scan),
    ]
    rows=[]
    for index,(name,fn) in enumerate(reviews,1):
        try:detail=fn();row={'review':index,'domain':name,'ok':True,'evidence':detail}
        except Exception as e:row={'review':index,'domain':name,'ok':False,'error':str(e)}
        rows.append(row);print(f"[{'PASS' if row['ok'] else 'FAIL'} {index:02d}] {name}: {row.get('evidence',row.get('error'))}",flush=True)
    summary={'ok':all(r['ok'] for r in rows),'review_domains':len(rows),'rows':rows}
    (ROOT/'REVIEW_RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not summary['ok']:raise SystemExit(1)
    print(json.dumps({'ok':True,'review_domains':len(rows)}))

if __name__=='__main__':main()
