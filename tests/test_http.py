import json
import sys
import unittest
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parent))
from browser_support import preview_server

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.server=preview_server();cls.url=cls.server.__enter__()
    @classmethod
    def tearDownClass(cls):cls.server.__exit__(None,None,None)
    def response(self,path,body=None,headers=None):
        req=Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers or {})
        try:return urlopen(req,timeout=5)
        except HTTPError as error:return error
    def test_home_and_security_headers(self):
        with self.response('/index.html') as r:
            self.assertEqual(r.status,200)
            for h in ['Content-Security-Policy','X-Content-Type-Options','Referrer-Policy','Permissions-Policy']:self.assertTrue(r.headers[h])
            self.assertNotIn('unsafe-eval',r.headers['Content-Security-Policy'])
    def test_assets_available(self):
        for path in ['/app.js','/search-core.js','/js/centers.js','/style.css','/css/enhancements.css','/data/services.json','/data/welfare-centers.json']:
            with self.response(path) as r:self.assertEqual(r.status,200,path)
    def test_secrets_and_source_not_served(self):
        for path in ['/.env','/.env.example','/.git/config','/api/common.py','/tests/test_http.py','/README.md','/%2eenv','/../CODEX_TASK_hwaseong_life_navi.md','/data/']:
            with self.response(path) as r:self.assertEqual(r.status,404,path)
    def test_real_api_fallback(self):
        with self.response('/api/guide',{'query':'전입신고'},{'Content-Type':'application/json'}) as r:
            self.assertEqual(r.status,200);self.assertFalse(json.load(r)['used_ai'])
    def test_cross_origin_post_rejected(self):
        with self.response('/api/guide',{'query':'전입신고'},{'Content-Type':'application/json','Origin':'https://untrusted.example'}) as r:self.assertEqual(r.status,403)
    def test_missing_map_key(self):
        with self.response('/api/address',{'address':'발안로 89'},{'Content-Type':'application/json'}) as r:self.assertEqual(r.status,503)

if __name__=='__main__':unittest.main()
