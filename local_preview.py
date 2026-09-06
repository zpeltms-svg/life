#!/usr/bin/env python3
import json
import os
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent


def load_local_environment():
    """Load uncommitted local settings without overriding process variables."""
    loaded = []
    for filename in ('.env.local', '.env'):
        path = ROOT / filename
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding='utf-8-sig').splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            if not key.replace('_', '').isalnum() or key[:1].isdigit():
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('\"', "'"):
                value = value[1:-1]
            if key not in os.environ:
                os.environ[key] = value
        loaded.append(filename)
    return loaded


LOADED_ENV_FILES = load_local_environment()
from api import guide, public_services, address, route
from api._common import RequestError, send_error

HOST = "127.0.0.1"
API_HANDLERS = {'/api/guide': guide.handler, '/api/public-services': public_services.handler, '/api/address': address.handler, '/api/route': route.handler}
STATIC_FILES = {'/', '/index.html', '/app.js', '/search-core.js', '/style.css', '/css/enhancements.css', '/js/centers.js', '/data/services.json', '/data/welfare-centers.json'}
SECURITY_HEADERS = json.loads((ROOT/'vercel.json').read_text(encoding='utf-8'))['headers'][0]['headers']


def preview_port():
    raw = (os.getenv("LIFE_NAVI_PORT") or "5500").strip()
    try:
        port = int(raw)
    except ValueError:
        raise SystemExit("LIFE_NAVI_PORT는 1~65535 사이의 숫자여야 합니다.")
    if not 1 <= port <= 65535:
        raise SystemExit("LIFE_NAVI_PORT는 1~65535 사이여야 합니다.")
    return port


class PreviewHandler(SimpleHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        # Query strings, addresses and request bodies must never enter logs.
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        for item in SECURITY_HEADERS:
            if item['key'] != 'Strict-Transport-Security':
                self.send_header(item['key'], item['value'])
        super().end_headers()

    def do_GET(self):
        if unquote(urlparse(self.path).path) not in STATIC_FILES:
            return self._json(404, {'error':'요청한 경로를 찾을 수 없습니다.'})
        return super().do_GET()

    def do_HEAD(self):
        if unquote(urlparse(self.path).path) not in STATIC_FILES:
            self.send_response(404); self.end_headers(); return
        return super().do_HEAD()

    def _json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = urlparse(self.path).path
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://{host}', f'https://{host}'):
            return self._json(403, {'error':'같은 사이트에서만 요청할 수 있습니다.'})
        if path in API_HANDLERS:
            return API_HANDLERS[path].do_POST(self)
        return self._json(404, {"error": "요청한 경로를 찾을 수 없습니다."})

    def do_OPTIONS(self):
        if urlparse(self.path).path.startswith("/api/"):
            self.send_response(204)
            self.send_header("Allow", "POST, OPTIONS")
            self.end_headers()
            return
        self.send_error(404)


def main():
    port = preview_port()
    try:
        server = ThreadingHTTPServer((HOST, port), PreviewHandler)
    except OSError:
        print("미리보기 서버를 시작하지 못했습니다.")
        print(f"{HOST}:{port} 포트를 다른 프로그램이 사용 중인지 확인해 주세요.")
        return 1

    url = f"http://{HOST}:{port}/index.html"
    print("화성생활 내비 로컬 미리보기")
    print(f"브라우저 주소: {url}")
    if LOADED_ENV_FILES:
        print("로컬 연동 설정을 불러왔습니다: " + ", ".join(LOADED_ENV_FILES))
    if not (os.getenv('PUBLIC_DATA_SERVICE_KEY') or '').strip():
        print("공공데이터 확장 검색: 꺼짐 (.env.local에 PUBLIC_DATA_SERVICE_KEY를 설정하면 켜집니다)")
    print("종료하려면 이 창에서 Ctrl+C를 누르세요.")
    if (os.getenv("LIFE_NAVI_NO_BROWSER") or "").strip() != "1":
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n미리보기를 종료합니다.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
