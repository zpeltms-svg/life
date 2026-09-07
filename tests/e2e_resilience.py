import json
from pathlib import Path
from browser_support import preview_server, launch, ROOT
from playwright.sync_api import sync_playwright, expect

VIEWPORTS=[(390,844),(412,915),(768,1024),(1440,900)]

def search(page,text):
    page.locator('#situation').fill(text)
    page.locator('#guide-form').evaluate('(form)=>form.requestSubmit()')
    expect(page.locator('#submit-btn')).to_be_enabled(timeout=15000)
    expect(page.locator('#results')).to_be_visible()

def ready(page,url):
    page.goto(url+'/index.html',wait_until='networkidle')
    page.wait_for_function("()=>document.documentElement.dataset.appReady==='true'")

def run():
    rows=[];errors=[]
    artifacts=ROOT/'tests/artifacts';artifacts.mkdir(exist_ok=True)
    with preview_server() as url,sync_playwright() as pw:
        browser=launch(pw)
        for width,height in VIEWPORTS:
            context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce')
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            ready(page,url)
            assert page.locator('.citizen-quick').count()>=16
            dims=page.evaluate('()=>({width:innerWidth,scroll:document.documentElement.scrollWidth})');assert dims['scroll']<=dims['width'],dims
            page.screenshot(path=str(artifacts/f'home-{width}.png'),full_page=True)
            page.get_by_role('button',name='보건증 건강진단결과서 발급').click()
            expect(page.locator('button[data-id="HEALTH-001"]')).to_be_visible()
            search(page,'아기가 태어났어요')
            ids=page.locator('.service-card .detail-btn').evaluate_all('(els)=>els.map(e=>e.dataset.id)')
            assert ids[:5]==['BIRTH-001','BIRTH-002','BIRTH-003','BIRTH-004','BIRTH-005'],ids
            page.locator('button[data-id="BIRTH-004"]').click()
            box=page.locator('#detail-dialog').bounding_box();assert box and box['x']>=0 and box['y']>=0 and box['x']+box['width']<=width+1 and box['y']+box['height']<=height+1,box
            page.locator('.task-checklist input').first.check();assert page.locator('.task-checklist input').first.is_checked()
            page.keyboard.press('Escape');expect(page.locator('#detail-dialog')).not_to_be_visible()
            page.locator('#center-area').select_option(label='만세구 · 남양읍')
            expect(page.locator('#center-result')).to_contain_text('화성시청역로 36')
            assert page.locator('#center-result a').first.get_attribute('href').startswith('https://map.naver.com/')
            page.locator('#center-address').fill('향남읍');page.locator('#center-find').click()
            expect(page.locator('#center-result')).to_contain_text('향남읍 행정복지센터')
            # User-reported address resolves offline to its verified jurisdiction.
            page.locator('#center-address').fill('상신하길로 274');page.locator('#center-find').click()
            expect(page.locator('#center-result')).to_contain_text('향남읍 행정복지센터')
            expect(page.locator('#center-status')).to_contain_text('검증된 주소 자료')
            page.locator('#center-address').fill('화성시 발안로 89');page.locator('#center-find').click()
            expect(page.locator('#center-status')).to_contain_text('지도 연동이 설정되지 않았습니다')
            # Current-position fallback and selected-center navigation work without Naver API credentials.
            page.evaluate("()=>Object.defineProperty(navigator,'geolocation',{configurable:true,value:{getCurrentPosition:(ok)=>ok({coords:{latitude:37.1324,longitude:126.9203,accuracy:15}}),watchPosition:(ok)=>{ok({coords:{latitude:37.1324,longitude:126.9203,accuracy:15}});return 1;},clearWatch:()=>{}}})")
            page.locator('button[data-id="BIRTH-002"]').click()
            page.locator('.current-address-btn').click()
            expect(page.locator('.welfare-area-select')).to_have_value('향남읍')
            expect(page.locator('.welfare-center-panel .route-status')).to_contain_text('관할 판정은 아닙니다')
            page.locator('.welfare-route-btn').click()
            expect(page.locator('.welfare-center-panel .route-status')).to_contain_text('직선거리')
            expect(page.locator('.welfare-center-panel a[href^="nmap://route/car"]')).to_be_visible()
            expect(page.locator('.welfare-center-panel a[href^="https://map.naver.com/"]')).to_be_visible()
            page.keyboard.press('Escape')
            # Any usable browser position lists the nearest centers with direct route links; low confidence is flagged, not blocked.
            page.evaluate("()=>Object.defineProperty(navigator,'geolocation',{configurable:true,value:{getCurrentPosition:(ok)=>ok({coords:{latitude:37.17,longitude:127.10,accuracy:5000}}),watchPosition:(ok)=>{ok({coords:{latitude:37.17,longitude:127.10,accuracy:5000}});return 1;},clearWatch:()=>{}}})")
            page.locator('#center-nearest').click()
            expect(page.locator('#center-result article')).to_have_count(3, timeout=9000)
            expect(page.locator('#center-status')).to_contain_text('부정확할 수 있으니')
            expect(page.locator('#center-result h3').first).to_contain_text('가장 가까운 센터')
            assert page.locator('#center-result a[href*="map.naver.com/p/directions"]').count() >= 1
            page.evaluate("()=>Object.defineProperty(navigator,'geolocation',{configurable:true,value:{getCurrentPosition:(ok)=>ok({coords:{latitude:37.7,longitude:126.7,accuracy:10}}),watchPosition:(ok)=>{ok({coords:{latitude:37.7,longitude:126.7,accuracy:10}});return 1;},clearWatch:()=>{}}})")
            page.locator('#center-nearest').click()
            expect(page.locator('#center-status')).to_contain_text('관할센터 판정은 아닙니다')
            expect(page.locator('#center-result h3').first).to_contain_text('가장 가까운 센터')
            # Explicitly deny location. No external lookup is needed for nearest centers.
            page.evaluate("()=>Object.defineProperty(navigator,'geolocation',{configurable:true,value:{getCurrentPosition:(ok,fail)=>fail({code:1}),watchPosition:(ok,fail)=>fail({code:1}),clearWatch:()=>{}}})")
            page.locator('#center-nearest').click();expect(page.locator('#center-status')).to_contain_text('거부')
            page.locator('#center-area').select_option('동탄9동');expect(page.locator('#center-result')).to_contain_text('동탄신리천로 9')
            # Safe text handling in input and zero-result official alternatives.
            search(page,'<img src=x onerror=alert(1)>')
            assert page.locator('#result-list img').count()==0
            expect(page.locator('#no-result')).to_be_visible();assert page.locator('#no-result a').count()>=3
            requests=[]
            page.on('request',lambda r:requests.append(r.url) if '/api/' in r.url else None)
            for value in ['4111 1111 1111 1111 전입신고','123-456-789012 전입신고','０１０-１２３４-５６７８ 전입신고']:
                requests.clear();search(page,value);assert not requests,requests;expect(page.locator('#analysis-note')).to_contain_text('외부 AI·공공데이터 전송 없이')
            # Both external endpoints unavailable: real static data still supports search.
            page.route('**/api/guide',lambda r:r.fulfill(status=503,json={'error':'unavailable'}))
            page.route('**/api/public-services',lambda r:r.fulfill(status=503,json={'error':'unavailable'}))
            search(page,'여권이 만료됐어요');expect(page.locator('button[data-id="PASSPORT-002"]')).to_be_visible()
            page.locator('button[data-id="PASSPORT-002"]').click();page.locator('.destination-choice').first.click()
            expect(page.locator('.route-fallback')).to_be_visible();assert page.locator('.route-fallback').get_attribute('href').startswith('https://map.naver.com/')
            page.screenshot(path=str(artifacts/f'detail-{width}.png'))
            page.keyboard.press('Escape')
            dims=page.evaluate('()=>({width:innerWidth,scroll:document.documentElement.scrollWidth})');assert dims['scroll']<=dims['width'],dims
            rows.append({'width':width,'height':height,'ok':True,'overflow':False,'scenarios':18})
            context.close()
        # Initial center data failure must leave local service search usable.
        context=browser.new_context();page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/data/welfare-centers.json',lambda r:r.fulfill(status=503,body='unavailable'))
        ready(page,url);search(page,'전입신고');expect(page.locator('button[data-id="MOVE-001"]')).to_be_visible()
        context.close()
        # Initial core data failure exposes an actionable error and official alternatives.
        context=browser.new_context();page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/data/services.json',lambda r:r.fulfill(status=503,body='unavailable'))
        page.goto(url+'/index.html');page.wait_for_function("()=>document.documentElement.dataset.appReady==='error'")
        expect(page.locator('#service-status')).to_contain_text('불러오지 못했습니다');expect(page.locator('#no-result')).to_be_visible()
        context.close();browser.close()
    assert not errors,errors
    summary={'ok':True,'page_errors':len(errors),'viewports':rows,'data_failure_cases':2,'live_provider_calls':False}
    (ROOT/'E2E_RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':run()
