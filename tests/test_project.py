import io
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import common, guide, public_services  # noqa: E402

SERVICES_PAYLOAD = json.loads((ROOT / 'data/services.json').read_text(encoding='utf-8'))
SERVICES = SERVICES_PAYLOAD['services']
CENTERS_PAYLOAD = json.loads((ROOT / 'data/welfare-centers.json').read_text(encoding='utf-8'))
CENTERS = CENTERS_PAYLOAD['centers']
APP = (ROOT / 'app.js').read_text(encoding='utf-8')
SEARCH = (ROOT / 'search-core.js').read_text(encoding='utf-8')
INDEX = (ROOT / 'index.html').read_text(encoding='utf-8')
STYLE = (ROOT / 'style.css').read_text(encoding='utf-8')
VERCEL = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))


class FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeHandler:
    def __init__(self, payload=b'{}', ip='127.0.0.1', forwarded=None):
        self.rfile = io.BytesIO(payload)
        self.headers = FakeHeaders({'Content-Length': str(len(payload))})
        if forwarded is not None:
            self.headers['X-Forwarded-For'] = forwarded
        self.client_address = (ip, 12345)


def service(service_id):
    return next(item for item in SERVICES if item['id'] == service_id)


class DataIntegrityTests(unittest.TestCase):
    def test_service_count(self): self.assertGreaterEqual(len(SERVICES), 32)
    def test_service_ids_unique(self): self.assertEqual(len({s['id'] for s in SERVICES}), len(SERVICES))
    def test_service_required_fields(self):
        required = {'id','category','category_label','title','summary','who','when','method','documents','office','source_name','source_url','source_checked','keywords','official_status','review_after_days'}
        for item in SERVICES: self.assertTrue(required <= set(item), item['id'])
    def test_service_urls_https(self):
        for item in SERVICES: self.assertTrue(item['source_url'].startswith('https://'), item['id'])
    def test_online_urls_https(self):
        for item in SERVICES:
            if item.get('online_application'): self.assertTrue(item['online_application']['url'].startswith('https://'), item['id'])
    def test_source_dates_current(self):
        self.assertEqual(SERVICES_PAYLOAD['meta']['last_verified'], '2026-09-07')
        for item in SERVICES: self.assertEqual(item['source_checked'], '2026-09-07')
    def test_freshness_policy_declared(self): self.assertIn('review_after_days', SERVICES_PAYLOAD['meta']['freshness_policy'])
    def test_review_windows_sane(self):
        for item in SERVICES: self.assertGreaterEqual(item['review_after_days'], 7); self.assertLessEqual(item['review_after_days'], 365)
    def test_official_status(self):
        for item in SERVICES:
            self.assertIn(item.get('official_status'), ('verified','reference_only'))
            if item['official_status']=='reference_only': self.assertTrue(item.get('verification_note'))
    def test_keywords_nonempty_unique(self):
        for item in SERVICES:
            self.assertTrue(item['keywords'], item['id'])
            compact = [re.sub(r'\s+', '', str(k).strip()) for k in item['keywords']]
            self.assertEqual(len(compact), len(set(compact)), item['id'])
    def test_no_overbroad_precision_keywords(self):
        forbidden = {
            'MOVE-001': {'주소', '이사'},
            'BIRTH-001': {'아기', '아이'},
            'BIRTH-002': {'아기', '아이', '출산'},
            'YOUTH-001': {'청년', '취업'},
            'YOUTH-002': {'청년', '창업'},
            'WASTE-001': {'쓰레기', '수거'},
            'PET-001': {'반려동물', '강아지', '고양이'},
        }
        for item in SERVICES: self.assertFalse(set(item['keywords']) & forbidden.get(item['id'], set()), item['id'])
    def test_birth_support_documents_regression(self):
        self.assertEqual(service('BIRTH-002')['documents'], ['신청서','신청인 신분증','통장사본'])
    def test_birth_support_residency_rule_present(self): self.assertIn('180일', service('BIRTH-002')['who'])
    def test_birth_support_deadline_present(self): self.assertIn('1년 이내', service('BIRTH-002')['when'])
    def test_move_deadline_present(self): self.assertIn('14일 이내', service('MOVE-001')['when'])
    def test_center_count(self): self.assertEqual(len(CENTERS), 29)
    def test_center_areas_unique(self): self.assertEqual(len({c['area'] for c in CENTERS}), 29)
    def test_center_names_unique(self): self.assertEqual(len({c['name'] for c in CENTERS}), 29)
    def test_center_addresses_unique(self): self.assertEqual(len({c['address'] for c in CENTERS}), 29)
    def test_center_source_date(self): self.assertEqual(CENTERS_PAYLOAD['source_checked'], '2026-09-07')
    def test_center_districts(self): self.assertEqual({c['district'] for c in CENTERS}, {'만세구','효행구','병점구','동탄구'})
    def test_center_addresses_include_district(self):
        for center in CENTERS: self.assertIn(center['district'], center['address'], center['area'])
    def test_manse_district_count(self): self.assertEqual(sum(c['district']=='만세구' for c in CENTERS), 10)
    def test_hyohaeng_district_count(self): self.assertEqual(sum(c['district']=='효행구' for c in CENTERS), 5)
    def test_byeongjeom_district_count(self): self.assertEqual(sum(c['district']=='병점구' for c in CENTERS), 5)
    def test_dongtan_district_count(self): self.assertEqual(sum(c['district']=='동탄구' for c in CENTERS), 9)
    def test_all_areas_covered_in_frontend(self):
        for center in CENTERS: self.assertIn(repr(center['area']).replace('"', "'"), APP)


class SearchAndFrontendTests(unittest.TestCase):
    def test_search_core_loaded_before_app(self): self.assertLess(INDEX.index('search-core.js'), INDEX.index('app.js'))
    def test_privacy_disclosure(self):
        self.assertIn('외부 API로 전송될 수 있으니', INDEX); self.assertIn('개인정보는 입력하지 마세요', INDEX)
    def test_privacy_note_bound_to_textarea(self): self.assertIn('aria-describedby="privacy-note"', INDEX); self.assertIn('id="privacy-note"', INDEX)
    def test_textarea_autocomplete_off(self): self.assertIn('autocomplete="off"', INDEX)
    def test_skip_link(self): self.assertIn('class="skip-link"', INDEX); self.assertIn('<main id="home" tabindex="-1">', INDEX)
    def test_noscript_notice(self): self.assertIn('<noscript>', INDEX)
    def test_dialog_label(self): self.assertIn('aria-labelledby="detail-title"', INDEX)
    def test_result_heading_focus_target(self): self.assertIn('id="result-title" tabindex="-1"', INDEX)
    def test_no_mvp_label(self): self.assertNotIn('체험판(MVP)', INDEX)
    def test_no_google_font_import(self): self.assertNotIn('fonts.googleapis.com', STYLE); self.assertNotIn('@import url(', STYLE)
    def test_reduced_motion_css(self): self.assertRegex(STYLE, r'prefers-reduced-motion\s*:\s*reduce')
    def test_focus_visible_css(self): self.assertIn(':focus-visible', STYLE)
    def test_base_services_immutable(self): self.assertIn('Object.freeze', APP)
    def test_no_service_data_push(self): self.assertNotRegex(APP, r'baseServices\s*\.\s*push')
    def test_dynamic_services_not_mutated_into_base(self): self.assertIn('mergeUniqueServices(localFound, publicFound)', APP)
    def test_local_order_precedes_ai(self): self.assertIn('mergeUniqueServices(localRetrieve(query), aiResult?.services || [])', APP)
    def test_stale_search_guard(self): self.assertGreaterEqual(APP.count('searchSequence'), 4)
    def test_reset_invalidates_inflight_search(self): self.assertRegex(APP, r"resetBtn\.addEventListener[\s\S]{0,120}searchSequence \+= 1")
    def test_sensitive_client_guard(self): self.assertIn('containsSensitiveInfo(query)', APP)
    def test_sensitive_message_explains_local_only(self): self.assertIn('외부 AI·공공데이터 전송 없이', APP)
    def test_manual_address_api(self): self.assertIn("body: JSON.stringify({ address })", APP)
    def test_coordinate_address_api(self): self.assertIn("body: JSON.stringify({ latitude: coords.latitude, longitude: coords.longitude })", APP)
    def test_jurisdiction_button_exists(self): self.assertIn('resolve-address-btn', APP)
    def test_nearest_center_manual_select(self): self.assertIn('nearest-area-select', APP)
    def test_no_browser_geocoder_dependency(self): self.assertNotIn('naver.maps.Service.geocode', APP)
    def test_escape_dynamic_title(self): self.assertIn('escapeHtml(service.title)', APP)
    def test_safe_source_url_before_render(self): self.assertIn('const sourceUrl = safeHttpsUrl(service.source_url)', APP); self.assertIn('escapeHtml(sourceUrl)', APP)
    def test_safe_online_url_before_render(self): self.assertIn('safeHttpsUrl(online.url)', APP)
    def test_external_links_noopener(self): self.assertIn('noopener noreferrer', APP)
    def test_timeout_fetch(self): self.assertGreaterEqual(APP.count('AbortController'), 2)
    def test_static_fetch_no_store(self): self.assertIn("cache: 'no-store'", APP)
    def test_source_staleness_ui(self): self.assertIn('review_after_days', APP); self.assertIn('재확인 필요', APP)
    def test_app_readiness_signal(self): self.assertIn("dataset.appReady = 'true'", APP); self.assertIn("dataset.appReady = 'error'", APP)
    def test_search_core_pii_resident_and_foreigner(self): self.assertRegex(SEARCH, r'\[1-8\]')
    def test_search_core_pii_landline(self): self.assertIn('국내 유선·인터넷·안심전화', SEARCH)
    def test_category_not_used_as_broad_search_score(self): self.assertNotIn('score += 6', SEARCH)
    def test_safe_https_helper_exported(self): self.assertIn('safeHttpsUrl,', SEARCH)
    def test_source_age_helper_exported(self): self.assertIn('sourceAgeDays,', SEARCH)
    def test_specific_area_sorting(self): self.assertIn('bySpecificity', SEARCH)
    def test_life_tile_pet_intent_is_specific(self): self.assertIn('취약계층 반려동물 진료 지원이 필요해요', INDEX)


class ServerCommonTests(unittest.TestCase):
    def setUp(self):
        common._RATE_BUCKETS.clear()

    def test_max_body(self): self.assertEqual(common.MAX_BODY_BYTES, 4096)
    def test_read_json_valid(self): self.assertEqual(common.read_json_body(FakeHandler(b'{"x":1}')), {'x':1})
    def test_read_json_non_object_rejected(self):
        with self.assertRaises(common.RequestError): common.read_json_body(FakeHandler(b'[]'))
    def test_read_json_too_large(self):
        h=FakeHandler(b'{}'); h.headers['Content-Length']='5000'
        with self.assertRaises(common.RequestError) as ctx: common.read_json_body(h)
        self.assertEqual(ctx.exception.status, 413)
    def test_read_json_missing_length(self):
        h=FakeHandler(); h.headers.pop('Content-Length')
        with self.assertRaises(common.RequestError) as ctx: common.read_json_body(h)
        self.assertEqual(ctx.exception.status, 411)
    def test_read_json_invalid_json(self):
        with self.assertRaises(common.RequestError) as ctx: common.read_json_body(FakeHandler(b'{'))
        self.assertEqual(ctx.exception.status, 400)
    def test_validate_text_required(self):
        with self.assertRaises(common.RequestError): common.validate_text('', required=True)
    def test_validate_text_length(self):
        with self.assertRaises(common.RequestError): common.validate_text('가'*301, max_length=300)
    def test_coordinate_korea_valid(self): self.assertEqual(common.validate_coordinates(37.2,127.1),(37.2,127.1))
    def test_coordinate_foreign_rejected(self):
        with self.assertRaises(common.RequestError): common.validate_coordinates(48.8,2.3)
    def test_coordinate_nonnumeric_rejected(self):
        with self.assertRaises(common.RequestError): common.validate_coordinates('north','east')
    def test_sensitive_phone(self): self.assertTrue(common.contains_sensitive_info('010-1234-5678'))
    def test_sensitive_landline(self): self.assertTrue(common.contains_sensitive_info('031-123-4567'))
    def test_sensitive_email(self): self.assertTrue(common.contains_sensitive_info('a@example.com'))
    def test_sensitive_rrn(self): self.assertTrue(common.contains_sensitive_info('900101-1234567'))
    def test_sensitive_foreigner_number_shape(self): self.assertTrue(common.contains_sensitive_info('900101-5234567'))
    def test_sensitive_business_number(self): self.assertTrue(common.contains_sensitive_info('123-45-67890'))
    def test_safe_query_not_sensitive(self): self.assertFalse(common.contains_sensitive_info('화성에서 청년 창업 지원'))
    def test_client_key_valid_forwarded(self):
        with mock.patch.dict(os.environ, {'VERCEL':'1'}):
            self.assertEqual(common.client_key(FakeHandler(forwarded='203.0.113.7, 10.0.0.1')), '203.0.113.7')
    def test_client_key_invalid_forwarded_falls_back(self): self.assertEqual(common.client_key(FakeHandler(ip='127.0.0.1', forwarded='evil')), '127.0.0.1')
    def test_client_key_ipv6(self): self.assertEqual(common.client_key(FakeHandler(ip='::1')), '::1')
    def test_rate_limit_enforced(self):
        h=FakeHandler(ip='192.0.2.50')
        common.enforce_rate_limit(h, 'unit', limit=2, window_seconds=60)
        common.enforce_rate_limit(h, 'unit', limit=2, window_seconds=60)
        with self.assertRaises(common.RequestError) as ctx: common.enforce_rate_limit(h, 'unit', limit=2, window_seconds=60)
        self.assertEqual(ctx.exception.status, 429)


class GuideAndPublicServiceTests(unittest.TestCase):
    def test_guide_structured_output(self):
        source=(ROOT/'api/guide.py').read_text(encoding='utf-8')
        self.assertIn('"type": "json_schema"', source); self.assertIn('"strict": True', source)
    def test_guide_store_false(self): self.assertIn('store=False', (ROOT/'api/guide.py').read_text(encoding='utf-8'))
    def test_guide_timeout_and_retry(self):
        source=(ROOT/'api/guide.py').read_text(encoding='utf-8'); self.assertIn('timeout=8.0', source); self.assertIn('max_retries=0', source)
    def test_guide_model_default(self): self.assertIn('gpt-5-mini', (ROOT/'api/guide.py').read_text(encoding='utf-8'))
    def test_guide_no_category_broad_score(self): self.assertNotIn('category in normalized', (ROOT/'api/guide.py').read_text(encoding='utf-8'))
    def test_no_error_detail_leak(self):
        for path in (ROOT/'api').glob('*.py'): self.assertNotIn('"detail"', path.read_text(encoding='utf-8'), path.name)
    def test_no_wildcard_cors(self):
        for path in (ROOT/'api').glob('*.py'): self.assertNotIn('Access-Control-Allow-Origin', path.read_text(encoding='utf-8'), path.name)
    def test_rate_limits_present(self):
        for name in ('guide.py','public_services.py','route.py','address.py'):
            self.assertIn('enforce_rate_limit', (ROOT/'api'/name).read_text(encoding='utf-8'), name)
    def test_options_no_cors(self): self.assertNotIn('Access-Control-Allow-Origin', (ROOT/'api/_common.py').read_text(encoding='utf-8'))
    def test_public_other_city_rejected(self): self.assertFalse(public_services.is_hwaseong_or_national({'소관기관명':'수원시청','소관기관유형':'지방자치단체'}))
    def test_public_unlisted_cityhall_rejected(self): self.assertFalse(public_services.is_hwaseong_or_national({'소관기관명':'춘천시청'}))
    def test_public_unlisted_city_department_rejected(self): self.assertFalse(public_services.is_hwaseong_or_national({'소관기관명':'강릉시 복지과'}))
    def test_public_hwaseong_allowed(self): self.assertTrue(public_services.is_hwaseong_or_national({'소관기관명':'화성특례시','소관기관유형':'지방자치단체'}))
    def test_public_gyeonggi_allowed(self): self.assertTrue(public_services.is_hwaseong_or_national({'소관기관명':'경기도','소관기관유형':'광역자치단체'}))
    def test_public_gyeonggi_office_allowed(self): self.assertTrue(public_services.is_hwaseong_or_national({'소관기관명':'경기도청','소관기관유형':'광역자치단체'}))
    def test_public_central_allowed(self): self.assertTrue(public_services.is_hwaseong_or_national({'소관기관명':'보건복지부','소관기관유형':'중앙행정기관'}))
    def test_public_publicagency_allowed(self): self.assertTrue(public_services.is_hwaseong_or_national({'소관기관명':'국민건강보험공단','소관기관유형':'공공기관'}))
    def test_safe_url_blocks_javascript(self): self.assertTrue(public_services.safe_url('javascript:alert(1)').startswith('https://www.gov.kr/'))
    def test_safe_url_blocks_http(self): self.assertTrue(public_services.safe_url('http://example.org').startswith('https://www.gov.kr/'))
    def test_safe_url_blocks_credentials(self): self.assertTrue(public_services.safe_url('https://u:p@example.org/x').startswith('https://www.gov.kr/'))
    def test_safe_url_keeps_https(self): self.assertEqual(public_services.safe_url('https://www.gov.kr/x'),'https://www.gov.kr/x')
    def test_clean_text_removes_control(self): self.assertEqual(public_services.clean_text('A\x00B\n C', 10), 'AB C')
    def test_clean_text_limits_length(self): self.assertEqual(len(public_services.clean_text('가'*500, 120)), 120)
    def test_relevance_threshold_defined(self): self.assertGreaterEqual(public_services.MIN_RELEVANCE_SCORE, 3)
    def test_relevance_unrelated_zero(self): self.assertEqual(public_services.relevance_score({'서비스명':'보육료'}, '자동차 등록', '자동차'), 0)
    def test_normalize_service_escapes_by_data_not_html(self):
        result=public_services.normalize_service({'서비스ID':'x','서비스명':'<script>alert(1)</script>','상세조회URL':'javascript:alert(1)'}, '지원')
        self.assertIn('<script>', result['title'])
        self.assertTrue(result['source_url'].startswith('https://www.gov.kr/'))
    def test_partial_public_fetch_failure_keeps_success(self):
        item={'서비스ID':'A1','서비스명':'출산 지원금','지원대상':'출산 가정','서비스목적요약':'출산 지원','소관기관명':'보건복지부','소관기관유형':'중앙행정기관','상세조회URL':'https://www.gov.kr/x'}
        def fake_fetch(_key, _condition, term):
            if term == '출산': return [item]
            raise URLError('simulated')
        with mock.patch.object(public_services, 'fetch_page', side_effect=fake_fetch):
            found=public_services.search_public_services('출산 지원금', 'dummy')
        self.assertTrue(any(x['id']=='PUBLIC-A1' for x in found))


class RetrievalTests(unittest.TestCase):
    def test_move_fallback(self): self.assertIn('MOVE-001', guide.keyword_fallback('화성으로 이사 왔어요', SERVICES))
    def test_birth_fallback(self): self.assertIn('BIRTH-001', guide.keyword_fallback('출생신고', SERVICES))
    def test_birth_both_for_new_baby(self):
        ids=guide.keyword_fallback('아기가 태어났어요', SERVICES); self.assertIn('BIRTH-001', ids); self.assertIn('BIRTH-002', ids)
    def test_birth_report_top_precedence(self): self.assertEqual(guide.keyword_fallback('태어났어요 신고해야 해요', SERVICES)[0], 'BIRTH-001')
    def test_youth_fallback(self): self.assertIn('YOUTH-001', guide.keyword_fallback('화성에서 취업을 준비해요', SERVICES))
    def test_youth_startup_fallback(self): self.assertIn('YOUTH-002', guide.keyword_fallback('청년 창업 임차료 지원', SERVICES))
    def test_waste_fallback(self): self.assertIn('WASTE-001', guide.keyword_fallback('소파 버리고 싶어요', SERVICES))
    def test_pet_fallback(self): self.assertIn('PET-001', guide.keyword_fallback('강아지 진료', SERVICES))
    def test_passport_reissue_fallback(self): self.assertEqual(guide.keyword_fallback('여권 재발급', SERVICES)[0], 'PASSPORT-002')
    def test_no_false_positive_pet_insurance(self): self.assertEqual(guide.keyword_fallback('반려동물 보험 가입', SERVICES), [])
    def test_no_false_positive_youth_basic_income(self): self.assertEqual(guide.keyword_fallback('청년 기본소득 신청', SERVICES), [])
    def test_no_false_positive_address_search(self): self.assertEqual(guide.keyword_fallback('도로명주소 찾기', SERVICES), [])
    def test_no_false_positive_furniture_purchase(self): self.assertEqual(guide.keyword_fallback('소파 구매 추천', SERVICES), [])
    def test_no_false_positive_recycling(self): self.assertEqual(guide.keyword_fallback('재활용품 분리수거 요일', SERVICES), [])
    def test_order_invariant_when_services_reversed(self):
        queries=['아기가 태어났어요','전입신고하고 출산지원금도 확인','청년 취업과 창업 지원을 같이 보고 싶어요']
        for q in queries: self.assertEqual(guide.keyword_fallback(q, SERVICES), guide.keyword_fallback(q, list(reversed(SERVICES))))


class ExpandedCitizenNeedsTests(unittest.TestCase):
    def test_action_labels_present(self):
        for item in SERVICES: self.assertTrue(item.get('action_group') and item.get('action_label'), item['id'])
    def test_high_demand_service_ids(self):
        required={'DOC-001','DOC-002','PASSPORT-002','HOUSING-002','TAX-002','HEALTH-001','HEALTH-002','UTILITY-001','CIVIL-001','CIVIL-003','JOB-001','PARKING-001'}
        self.assertTrue(required <= {s['id'] for s in SERVICES})
    def test_popular_needs_ui(self):
        for label in ('보건증','예방접종','여권 재발급','등본·초본','확정일자','자동차세','무인발급기','채용공고','주정차 과태료','국민신문고'):
            self.assertIn(label, INDEX)
    def test_result_action_plan(self): self.assertIn('id="result-plan"', INDEX); self.assertIn('renderActionPlan', APP)
    def test_no_result_official_fallbacks(self):
        for host in ('www.gov.kr','www.hscity.go.kr','www.epeople.go.kr'): self.assertIn(host, INDEX)
    def test_multiple_visit_destinations_supported(self): self.assertIn('visit_destinations', APP); self.assertIn('destination-choice', APP)
    def test_passport_has_two_hwasong_destinations(self):
        for sid in ('PASSPORT-001','PASSPORT-002'): self.assertEqual(len(service(sid).get('visit_destinations',[])),2)
    def test_sensitive_070(self): self.assertTrue(common.contains_sensitive_info('070-1234-5678 민원'))
    def test_sensitive_050(self): self.assertTrue(common.contains_sensitive_info('0505-123-4567 민원'))
    def test_sensitive_road_address(self): self.assertTrue(common.contains_sensitive_info('향남로 470 전입신고'))
    def test_sensitive_lot_address(self): self.assertTrue(common.contains_sensitive_info('향남읍 123-4 전입신고'))
    def test_generic_area_not_sensitive(self): self.assertFalse(common.contains_sensitive_info('향남읍 전입신고'))
    def test_negative_keyword_parity(self): self.assertEqual(guide.keyword_fallback('여권 케이스 추천', SERVICES), [])
    def test_job_search(self): self.assertEqual(guide.keyword_fallback('화성시 채용공고', SERVICES)[0], 'JOB-001')
    def test_parking_fine_search(self): self.assertEqual(guide.keyword_fallback('주정차 과태료 조회', SERVICES)[0], 'PARKING-001')


class DeploymentTests(unittest.TestCase):
    def test_rewrite_count(self): self.assertEqual(len(VERCEL['rewrites']), 4)
    def test_no_map_config_rewrite(self): self.assertNotIn('map-config', json.dumps(VERCEL))
    def test_security_headers_core(self):
        blob=json.dumps(VERCEL,ensure_ascii=False)
        for header in ('X-Content-Type-Options','X-Frame-Options','Referrer-Policy','Permissions-Policy'): self.assertIn(header, blob)
    def test_hsts_header(self): self.assertIn('Strict-Transport-Security', json.dumps(VERCEL))
    def test_csp_header(self): self.assertIn('Content-Security-Policy', json.dumps(VERCEL))
    def test_csp_disallows_objects(self): self.assertIn("object-src 'none'", json.dumps(VERCEL))
    def test_csp_blocks_framing(self): self.assertIn("frame-ancestors 'none'", json.dumps(VERCEL))
    def test_coop_header(self): self.assertIn('Cross-Origin-Opener-Policy', json.dumps(VERCEL))
    def test_openai_pinned(self): self.assertEqual((ROOT/'requirements.txt').read_text().strip(),'openai==3.8.0')
    def test_python_version_pinned(self): self.assertEqual((ROOT/'.python-version').read_text().strip(),'3.13')
    def test_env_no_real_secret(self):
        env=(ROOT/'.env.example').read_text(encoding='utf-8'); self.assertNotRegex(env, r'sk-[A-Za-z0-9]{20,}')
    def test_no_map_config_file(self): self.assertFalse((ROOT/'api/map_config.py').exists())
    def test_windows_one_click_launcher(self): self.assertTrue((ROOT/'실행.bat').exists()); self.assertIn('local_preview.py', (ROOT/'실행.bat').read_text(encoding='utf-8'))
    def test_posix_one_click_launcher(self): self.assertTrue((ROOT/'실행.command').exists()); self.assertIn('local_preview.py', (ROOT/'실행.command').read_text(encoding='utf-8'))
    def test_local_preview_compiles(self):
        result=subprocess.run([sys.executable,'-m','py_compile','local_preview.py'],cwd=ROOT,capture_output=True,text=True); self.assertEqual(result.returncode,0,result.stderr)
    def test_docs_mention_one_click_preview(self):
        readme=(ROOT/'README.md').read_text(encoding='utf-8'); self.assertIn('실행.bat', readme); self.assertIn('실행.command', readme)


if __name__ == '__main__':
    unittest.main(verbosity=2)
