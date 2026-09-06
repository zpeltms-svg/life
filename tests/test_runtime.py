import io
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api import common, guide, public_services, address, route, naver_maps, centers

class Request:
    def __init__(self, body=None, raw=None, headers=None):
        raw = raw if raw is not None else json.dumps(body or {},ensure_ascii=False).encode()
        self.headers={'Content-Length':str(len(raw)),'Content-Type':'application/json',**(headers or {})}
        self.rfile=io.BytesIO(raw);self.wfile=io.BytesIO();self.client_address=('127.0.0.1',1234);self.response_headers={};self.status=None
    def send_response(self,status):self.status=status
    def send_header(self,k,v):self.response_headers[k]=v
    def end_headers(self):pass
    def json(self):return json.loads(self.wfile.getvalue())

class RuntimeCase(unittest.TestCase):
    def setUp(self):
        common._RATE_BUCKETS.clear()
        self.env=mock.patch.dict(os.environ,{'OPENAI_API_KEY':'','PUBLIC_DATA_SERVICE_KEY':'','NCP_MAPS_CLIENT_ID':'','NCP_MAPS_CLIENT_SECRET':'','VERCEL':''})
        self.env.start();self.addCleanup(self.env.stop)
    def call(self, module, body=None, raw=None, headers=None):
        req=Request(body,raw,headers);module.handler.do_POST(req);return req

class PrivacyRuntimeTests(RuntimeCase):
    def test_server_blocks_external_for_all_sensitive_categories(self):
        values=['900101-1234567','900101-5234567','010-1234-5678','031-123-4567','070-1234-5678','0505-123-4567','a@example.com','123-45-67890','향남로 470','향남읍 123-4','4111 1111 1111 1111','123-456-789012','１２３４５６７８９０１２３４５６','010\u200b-1234-5678']
        for value in values:
            with self.subTest(value=value), mock.patch.object(guide,'ai_select') as ai, mock.patch.object(public_services,'search_public_services') as external:
                common._RATE_BUCKETS.clear()
                r=self.call(guide,{'query':value+' 전입신고'}); p=self.call(public_services,{'query':value+' 전입신고'})
                self.assertEqual(r.status,200);self.assertFalse(r.json()['used_ai']);self.assertEqual(p.json()['services'],[])
                ai.assert_not_called();external.assert_not_called()
    def test_sensitive_repeated_calls_stable(self):
        self.assertTrue(all(common.contains_sensitive_info('4111-1111-1111-1111') for _ in range(5)))
    def test_safe_date_and_area(self):
        for value in ['2026-09-07 출산지원','향남읍 전입신고','동탄7동','12,090원']:
            self.assertFalse(common.contains_sensitive_info(value),value)

class ApiInputTests(RuntimeCase):
    def test_all_endpoints_size_limit(self):
        for module in [guide,public_services,address,route]:
            r=self.call(module,raw=b'x'*4097);self.assertEqual(r.status,413)
    def test_all_endpoints_malformed(self):
        for module in [guide,public_services,address,route]:
            for raw in [b'{',b'[]',b'null',b'\xff']:
                r=self.call(module,raw=raw);self.assertEqual(r.status,400)
    def test_input_types(self):
        for value in [[],{},42,True]:
            self.assertEqual(self.call(guide,{'query':value}).status,400)
    def test_long_queries(self):
        for module in [guide,public_services]: self.assertEqual(self.call(module,{'query':'가'*301}).status,400)
    def test_invalid_coordinates(self):
        for lat,lng in [(None,None),('NaN',127),(float('inf'),127),(True,127),(90,127),(37,0)]:
            self.assertEqual(self.call(address,{'latitude':lat,'longitude':lng}).status,400)
    def test_wrong_content_type(self):self.assertEqual(self.call(guide,{'query':'전입신고'},headers={'Content-Type':'text/plain'}).status,415)
    def test_transfer_encoding(self):self.assertEqual(self.call(guide,{'query':'전입신고'},headers={'Transfer-Encoding':'chunked'}).status,400)
    def test_short_body(self):self.assertEqual(self.call(guide,raw=b'{}',headers={'Content-Length':'8'}).status,400)
    def test_missing_length(self):
        r=Request();r.headers.pop('Content-Length');guide.handler.do_POST(r);self.assertEqual(r.status,411)
    def test_no_internal_exception_leak(self):
        with mock.patch.object(guide,'load_services',side_effect=RuntimeError('PRIVATE INTERNAL SENTINEL')):
            r=self.call(guide,{'query':'전입신고'});self.assertEqual(r.status,500);self.assertNotIn('SENTINEL',str(r.json()))

class RateLimitTests(RuntimeCase):
    def test_all_endpoints_rate_limit(self):
        for module,limit,body in [(guide,24,{'query':'전입신고'}),(public_services,18,{'query':'복지'}),(address,30,{'address':'화성시'}),(route,20,{'origin':{'latitude':37,'longitude':127},'destination_query':'향남읍'})]:
            common._RATE_BUCKETS.clear()
            for _ in range(limit):self.call(module,body)
            r=self.call(module,body);self.assertEqual(r.status,429);self.assertEqual(r.response_headers['Retry-After'],'60')
    def test_local_forwarded_spoof_ignored(self):
        a=Request(headers={'X-Forwarded-For':'198.51.100.1'});self.assertEqual(common.client_key(a),'127.0.0.1')
    def test_bucket_memory_bound(self):
        for i in range(2048):
            r=Request();r.client_address=(f'10.{i//256}.{i%256}.1',1);common.enforce_rate_limit(r,'memory')
        r=Request();r.client_address=('192.0.2.1',1)
        with self.assertRaises(common.RequestError):common.enforce_rate_limit(r,'memory')
        self.assertEqual(len(common._RATE_BUCKETS),2048)

class FallbackTests(RuntimeCase):
    def test_missing_ai_key_local_results(self):
        r=self.call(guide,{'query':'아기가 태어났어요'});self.assertEqual(r.status,200);self.assertFalse(r.json()['used_ai']);self.assertEqual(r.json()['service_ids'][:5],['BIRTH-001','BIRTH-002','BIRTH-003','BIRTH-004','BIRTH-005'])
    def test_ai_timeout_malformed_rate_error_fallback(self):
        for error in [TimeoutError(),ValueError('bad json'),RuntimeError('rate limit')]:
            with mock.patch.object(guide,'ai_select',side_effect=error):
                r=self.call(guide,{'query':'전입신고'});self.assertEqual(r.status,200);self.assertEqual(r.json()['service_ids'][0],'MOVE-001');self.assertFalse(r.json()['used_ai'])
    def test_public_missing_key(self):
        r=self.call(public_services,{'query':'청년 지원'});payload=r.json();self.assertEqual(r.status,200);self.assertFalse(payload['configured']);self.assertFalse(payload['available']);self.assertEqual(payload['status'],'not_configured');self.assertIn('정상 검색',payload['note'])
    def test_public_failure_local_safe(self):
        with mock.patch.dict(os.environ,{'PUBLIC_DATA_SERVICE_KEY':'test-only'}),mock.patch.object(public_services,'search_public_services',side_effect=TimeoutError()):
            r=self.call(public_services,{'query':'청년 지원'});payload=r.json();self.assertEqual(r.status,200);self.assertEqual(payload['services'],[]);self.assertEqual(payload['status'],'unavailable');self.assertFalse(payload['available'])
    def test_public_success_with_zero_matches_is_still_available(self):
        with mock.patch.dict(os.environ,{'PUBLIC_DATA_SERVICE_KEY':'test-only'}),mock.patch.object(public_services,'search_public_services',return_value=[]):
            payload=self.call(public_services,{'query':'없는 지원'}).json();self.assertEqual(payload['status'],'ready');self.assertTrue(payload['available'])
    def test_public_auth_error_is_distinct(self):
        error=HTTPError('https://api.odcloud.kr',403,'forbidden',{},None)
        with mock.patch.dict(os.environ,{'PUBLIC_DATA_SERVICE_KEY':'test-only'}),mock.patch.object(public_services,'search_public_services',side_effect=error):
            payload=self.call(public_services,{'query':'청년 지원'}).json();self.assertEqual(payload['status'],'auth_error');self.assertFalse(payload['available']);self.assertNotIn('test-only',str(payload))
    def test_map_missing_key(self):self.assertEqual(self.call(address,{'address':'화성시 발안로 89'}).status,503)
    def test_geocode_failure(self):
        with mock.patch.object(address,'geocode_address',side_effect=TimeoutError('INTERNAL')):
            r=self.call(address,{'address':'화성시 발안로 89'});self.assertEqual(r.status,503);self.assertNotIn('INTERNAL',str(r.json()))
    def test_reverse_failure(self):
        with mock.patch.object(address,'reverse_location',side_effect=TimeoutError()):self.assertEqual(self.call(address,{'latitude':37.1,'longitude':127}).status,503)
    def test_route_failure(self):
        with mock.patch.object(route,'driving_route',side_effect=TimeoutError()):self.assertEqual(self.call(route,{'origin':{'latitude':37.1,'longitude':127},'destination_query':'향남읍'}).status,503)

class StructuredOutputTests(RuntimeCase):
    def ai(self,output,query='전입신고'):
        client=mock.Mock();client.responses.create.return_value=types.SimpleNamespace(output_text=output)
        module=types.SimpleNamespace(OpenAI=mock.Mock(return_value=client))
        with mock.patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'}),mock.patch.dict(sys.modules,{'openai':module}):result=guide.ai_select(query,guide.load_services())
        return result,client,module
    def test_schema_only_registered_ids_and_no_fact_generation(self):
        result,client,module=self.ai('{"service_ids":["MOVE-001","MOVE-001","unknown",{},2],"note":"invented fact"}')
        self.assertEqual(result['service_ids'],['MOVE-001']);self.assertNotIn('invented',result['note'])
        args=client.responses.create.call_args.kwargs;schema=args['text']['format']['schema']
        self.assertEqual(set(schema['properties']),{'service_ids'});self.assertTrue(args['text']['format']['strict']);self.assertFalse(args['store'])
        self.assertEqual(module.OpenAI.call_args.kwargs['max_retries'],0)
    def test_malformed_shape(self):
        for value in ['[]','null','{"service_ids":12}']:
            result,_,_=self.ai(value);self.assertIsNone(result)
    def test_exclusion_also_applies_to_ai(self):
        result,_,_=self.ai('{"service_ids":["PASSPORT-002"]}','여권 케이스 추천');self.assertEqual(result['service_ids'],[])

class RegionTests(RuntimeCase):
    def test_other_localities_and_uncertain_region_rejected(self):
        for item in [{'소관기관명':'경기도 수원시','소관기관유형':'지방자치단체'}, {'소관기관명':'보건복지부','소관기관유형':'중앙부처','지원대상':'용인시 거주자'}, {'소관기관명':'알 수 없는 기관'}, {}, None]:self.assertFalse(public_services.is_hwaseong_or_national(item),item)
    def test_allow_explicit_regions(self):
        for agency in ['경기도','화성시','화성특례시','보건복지부','국민연금공단']:self.assertTrue(public_services.is_hwaseong_or_national({'소관기관명':agency}),agency)
    def test_hwaseong_bonus_not_relevance(self):self.assertEqual(public_services.relevance_score({'소관기관명':'화성시','서비스명':'자동차 검사'},'출산','출산'),0)
    def test_remote_retrieval_is_not_verification(self):
        s=public_services.normalize_service({'서비스ID':'1'},'출산');self.assertFalse(s['source_checked']);self.assertTrue(s['retrieved_at'])

class CenterRuntimeTests(RuntimeCase):
    def test_all_coordinates_and_sources(self):
        for c in centers.load_centers():
            self.assertTrue(36.8<c['lat']<37.5);self.assertTrue(126.5<c['lng']<127.4);self.assertIn('q_deptCode=',c['source_url']);self.assertTrue(c['coordinate_source'].startswith('https://'))
    def test_relocated_offices(self):
        self.assertIn('화성시청역로 36',centers.center_for_destination('남양읍')['address']);self.assertIn('동탄신리천로 9',centers.center_for_destination('동탄9동')['address'])
    def test_other_city_same_town_rejected(self):self.assertIsNone(centers.administrative_center('충청남도 논산시 반월동'))
    def test_address_success(self):
        with mock.patch.object(address,'geocode_address',return_value={'latitude':37.13,'longitude':126.92,'address':'화성시 발안로 89'}),mock.patch.object(address,'reverse_location',return_value={'area':'경기도 화성시 만세구 향남읍'}):
            r=self.call(address,{'address':'발안로 89'});self.assertEqual(r.status,200);self.assertEqual(r.json()['center']['area'],'향남읍')
    def test_center_route_never_geocodes_center(self):
        with mock.patch.object(route,'geocode_address') as geocode,mock.patch.object(route,'driving_route',return_value={'summary':{'duration':600000,'distance':5000},'path':[]}) as driving:
            r=self.call(route,{'origin':{'latitude':37.1,'longitude':127},'destination_query':'향남읍'});self.assertEqual(r.status,200);geocode.assert_not_called();driving.assert_called_once()
    def test_reverse_requires_administrative_not_legal_region(self):
        with mock.patch.object(naver_maps,'naver_get',return_value={'results':[{'name':'legalcode','region':{'area3':{'name':'반송동'}}}]}):
            with self.assertRaises(common.RequestError):naver_maps.reverse_location(37,127)
    def test_map_arbitrary_url_blocked(self):
        with self.assertRaises(common.RequestError):naver_maps.naver_get('https://example.com',{})
    def test_geocode_invalid_response_coordinates(self):
        with mock.patch.object(naver_maps,'naver_get',return_value={'addresses':[{'x':'NaN','y':'NaN'}]}):
            with self.assertRaises(common.RequestError):naver_maps.geocode_address('test')

if __name__=='__main__':unittest.main()
