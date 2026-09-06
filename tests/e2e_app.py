import json
import re
from pathlib import Path

from browser_support import preview_server, launch
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'index.html').read_text(encoding='utf-8')
CSS = (ROOT / 'style.css').read_text(encoding='utf-8')
SEARCH_JS = (ROOT / 'search-core.js').read_text(encoding='utf-8')
APP_JS = (ROOT / 'app.js').read_text(encoding='utf-8')
SERVICES = json.loads((ROOT / 'data' / 'services.json').read_text(encoding='utf-8'))
CENTERS = json.loads((ROOT / 'data' / 'welfare-centers.json').read_text(encoding='utf-8'))

# Serve real assets over HTTP with production CSP; mock only API and geolocation boundaries.
HTML_BODY = re.sub(r'<link[^>]+href="style\.css"[^>]*>', '', HTML)
HTML_BODY = re.sub(r'<script[^>]+src="(?:search-core|app)\.js"[^>]*></script>', '', HTML_BODY)


def install_mocks(page):
    page.add_init_script(
        """
        (({services, centers}) => {
          window.__apiCounts = {guide:0, public:0, address:0, route:0};
          window.__mockServices = services;
          window.__mockCenters = centers;
          Object.defineProperty(navigator, 'geolocation', {
            configurable: true,
            value: {
              getCurrentPosition(success) {
                success({coords:{latitude:37.17, longitude:127.10, accuracy:10}});
              }
            }
          });
          window.fetch = async (input, options = {}) => {
            const url = String(input);
            const body = (() => { try { return JSON.parse(options.body || '{}'); } catch (_) { return {}; } })();
            const jsonResponse = (payload, status = 200) => new Response(JSON.stringify(payload), {
              status,
              headers: {'Content-Type':'application/json; charset=utf-8'}
            });
            if (url.endsWith('./data/services.json') || url.endsWith('/data/services.json')) {
              return jsonResponse(window.__mockServices);
            }
            if (url.endsWith('./data/welfare-centers.json') || url.endsWith('/data/welfare-centers.json')) {
              return jsonResponse(window.__mockCenters);
            }
            if (url === '/api/guide') {
              window.__apiCounts.guide++;
              const q = String(body.query || '');
              if (q.includes('출생신고')) {
                // Deliberately reverse AI order. UI should keep deterministic local ranking first.
                return jsonResponse({service_ids:['BIRTH-002','BIRTH-001'], note:'mock ai', used_ai:true});
              }
              return jsonResponse({service_ids:[], note:'mock ai', used_ai:false});
            }
            if (url === '/api/public-services') {
              window.__apiCounts.public++;
              const q = String(body.query || '');
              let services = [];
              if (q.includes('장애인 혜택')) {
                services = [{
                  id:'PUBLIC-DEMO', category:'public-data', category_label:'공공서비스',
                  title:'테스트 장애인 공공서비스', priority:50,
                  summary:'동적 공공데이터 테스트 결과', who:'테스트 대상', when:'공식 안내 확인',
                  method:['공식 안내 확인'], documents:['공식 안내 확인'], office:'대한민국',
                  processing_time:'공식 안내 확인', source_name:'정부24', source_url:'https://www.gov.kr/',
                  source_checked:'2026-09-07', review_after_days:90, keywords:['장애인']
                }];
              }
              if (q.includes('XSS검사')) {
                services = [{
                  id:'PUBLIC-XSS', category:'public-data', category_label:'<img src=x onerror=alert(1)>',
                  title:'<img src=x onerror=alert(1)>', priority:50,
                  summary:'<script>window.__xss=1</script>', who:'테스트', when:'테스트',
                  method:['<b>테스트</b>'], documents:['테스트'], office:'테스트',
                  processing_time:'테스트', source_name:'테스트', source_url:'javascript:alert(1)',
                  source_checked:'2020-01-01', review_after_days:30, keywords:['XSS']
                }];
              }
              return jsonResponse({services, configured:true, note:'mock public'});
            }
            if (url === '/api/address') {
              window.__apiCounts.address++;
              if (body.address) {
                return jsonResponse({
                  address:'화성시 만세구 향남읍 발안로 89', area:'경기도 화성시 만세구 향남읍',
                  latitude:37.132, longitude:126.92
                });
              }
              return jsonResponse({
                address:'화성시 동탄구 동탄7동 동탄대로8길 36', area:'경기도 화성시 동탄구 동탄7동',
                latitude:37.17, longitude:127.10
              });
            }
            if (url === '/api/route') {
              window.__apiCounts.route++;
              const destination = String(body.destination_query || '화성시 행정복지센터');
              return jsonResponse({
                destination, address:destination, latitude:37.13, longitude:126.92,
                distance_m:5300, duration_ms:720000, path:[],
                routes:[{key:'trafast',label:'빠른 길',distance_m:5300,duration_ms:720000,path:[]}],
                map_client_id:''
              });
            }
            return jsonResponse({error:'not found'}, 404);
          };
        })(%s);
        """ % json.dumps({'services': SERVICES, 'centers': CENTERS}, ensure_ascii=False)
    )


def boot_page(context, viewport):
    page = context.new_page()
    page.set_viewport_size(viewport)
    errors = []
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    install_mocks(page)
    page.goto(BASE_URL + '/index.html', wait_until='domcontentloaded')
    page.wait_for_function("() => document.documentElement.dataset.appReady === 'true'")
    return page, errors


def search(page, text):
    page.locator('#situation').fill(text)
    page.locator('#guide-form').evaluate('(form) => form.requestSubmit()')
    page.wait_for_function("() => document.querySelector('#submit-btn').disabled === false")
    page.locator('#results').wait_for(state='visible')


def run():
    with sync_playwright() as pw:
        browser = launch(pw)
        context = browser.new_context(viewport={'width':1440, 'height':900})
        page, errors = boot_page(context, {'width':1440, 'height':900})

        # Keyboard interaction on the life-file tile.
        first_file = page.locator('.life-file').first
        first_file.focus()
        first_file.press('Enter')
        assert page.locator('#situation').input_value() == '화성으로 이사 왔어요'

        # Deterministic local order must win over reversed AI order.
        search(page, '출생신고하고 출산지원금도 받고 싶어요')
        ids = page.locator('.service-card .detail-btn').evaluate_all("els => els.map(e => e.dataset.id)")
        assert ids[:2] == ['BIRTH-001', 'BIRTH-002'], ids
        assert page.locator('#result-title').evaluate('el => document.activeElement === el') is True

        # Detail -> typed address -> jurisdiction -> route.
        page.locator('button.detail-btn[data-id="BIRTH-002"]').click()
        page.locator('#detail-dialog').wait_for(state='visible')
        page.locator('.current-address').fill('발안로 89')
        page.locator('.resolve-address-btn').click()
        page.wait_for_function("() => document.querySelector('.welfare-area-select').value === '향남읍'")
        assert '향남읍 관할' in page.locator('.jurisdiction-panel .route-status').inner_text()
        page.locator('.welfare-route-btn').click()
        page.wait_for_function("() => document.querySelector('.jurisdiction-panel .route-status').innerText.includes('자동차 약')")
        assert '5.3km' in page.locator('.jurisdiction-panel .route-status').inner_text()
        page.keyboard.press('Escape')
        page.locator('#detail-dialog').wait_for(state='hidden')

        # Nationwide nearest center from mocked geolocation.
        search(page, '출생신고를 하고 싶어요')
        page.locator('button.detail-btn[data-id="BIRTH-001"]').click()
        page.locator('.nearest-center-btn').click()
        page.wait_for_function("() => document.querySelector('.nearest-area-select').value === '동탄7동'")
        page.wait_for_function("() => document.querySelector('.nearest-center-panel .route-status').innerText.includes('자동차 약')")
        page.locator('#detail-close').click()

        # An address can replace an inaccurate device location and must show distance immediately.
        page.locator('button.detail-btn[data-id="BIRTH-001"]').click()
        page.locator('.nearest-origin-address').fill('발안로 89')
        page.locator('.nearest-address-btn').click()
        page.wait_for_function("() => document.querySelector('.nearest-area-select').value === '향남읍'")
        page.wait_for_function("() => document.querySelector('.nearest-center-panel .route-status').innerText.includes('자동차 약')")
        page.locator('#detail-close').click()

        # Dynamic result must not pollute later search; newly covered passport task remains local.
        search(page, '장애인 혜택')
        assert page.get_by_text('테스트 장애인 공공서비스').count() >= 1
        search(page, '여권 재발급')
        assert page.get_by_text('테스트 장애인 공공서비스').count() == 0
        assert page.locator('button.detail-btn[data-id="PASSPORT-002"]').count() == 1
        assert page.locator('#result-plan').is_visible()

        # Passport supports multiple official visit destinations.
        page.locator('button.detail-btn[data-id="PASSPORT-002"]').click()
        assert page.locator('.destination-choice').count() == 2
        page.locator('.destination-choice').first.click()
        page.wait_for_function("() => document.querySelector('.visit-panel .route-status').innerText.includes('자동차 약')")
        page.locator('#detail-close').click()

        # High-demand quick action submits in one click.
        page.locator('.citizen-quick', has_text='보건증').click()
        page.wait_for_function("() => document.querySelector('#submit-btn').disabled === false && !document.querySelector('#results').hidden")
        assert page.locator('button.detail-btn[data-id="HEALTH-001"]').count() == 1

        # Sensitive query must not call external search endpoints; landline included.
        before = page.evaluate("({...window.__apiCounts})")
        search(page, '031-5189-1234 청년 취업')
        after = page.evaluate("({...window.__apiCounts})")
        assert before['guide'] == after['guide'] and before['public'] == after['public'], (before, after)
        assert '외부 AI·공공데이터 전송 없이' in page.locator('#analysis-note').inner_text()
        before = page.evaluate("({...window.__apiCounts})")
        search(page, '향남로 470 전입신고')
        after = page.evaluate("({...window.__apiCounts})")
        assert before['guide'] == after['guide'] and before['public'] == after['public'], (before, after)

        # True no-result state offers official next steps instead of a dead end.
        search(page, '도서관 회원증 발급')
        assert page.locator('.service-card').count() == 0
        assert page.locator('#no-result .empty-actions a').count() == 3

        # XSS and unsafe URL defense-in-depth + stale data warning.
        search(page, 'XSS검사')
        assert page.locator('.service-card img').count() == 0
        assert page.evaluate('window.__xss') is None
        assert '<img' in page.locator('.service-card h3').inner_text()
        assert '재확인 필요' in page.locator('.service-card').inner_text()
        page.locator('button.detail-btn[data-id="PUBLIC-XSS"]').click()
        assert page.locator('#detail-body a[href^="javascript:"]').count() == 0
        assert '공식 원문 링크 확인 필요' in page.locator('.source-box').inner_text()
        page.locator('#detail-close').click()

        # Reset clears rendered state and leaves the app usable.
        search(page, '소파 버리고 싶어요')
        page.locator('#reset-btn').click()
        assert page.locator('#results').is_hidden()
        assert page.locator('.service-card').count() == 0
        assert page.locator('#submit-btn').is_enabled()

        # Mobile overflow and usable search.
        mobile, mobile_errors = boot_page(context, {'width':390, 'height':844})
        dims = mobile.evaluate('({sw:document.documentElement.scrollWidth, iw:window.innerWidth})')
        assert dims['sw'] <= dims['iw'] + 1, dims
        search(mobile, '소파 버리고 싶어요')
        assert mobile.locator('button.detail-btn[data-id="WASTE-001"]').count() == 1
        assert mobile.locator('#submit-btn').is_visible()
        assert mobile.locator('.citizen-quick').count() >= 10
        mobile.close()

        context.close()
        browser.close()

    all_errors = errors + mobile_errors
    if all_errors:
        raise AssertionError(f'page errors: {all_errors}')
    print(json.dumps({'ok': True, 'actual_http': True, 'page_errors': len(all_errors)}, ensure_ascii=False))


if __name__ == '__main__':
    with preview_server() as BASE_URL:
        run()
