import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        client_id = (os.getenv("NCP_MAPS_CLIENT_ID") or "").strip()
        payload = {"client_id": client_id} if client_id else {"error": "네이버 지도 설정이 완료되지 않았습니다."}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200 if client_id else 503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
