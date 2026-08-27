import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REVERSE_GEOCODE_URL = "https://maps.apigw.ntruss.com/map-reversegeocode/v2/gc"


def send_json(handler, status, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            latitude = float(body.get("latitude"))
            longitude = float(body.get("longitude"))
            client_id = (os.getenv("NCP_MAPS_CLIENT_ID") or "").strip()
            client_secret = (os.getenv("NCP_MAPS_CLIENT_SECRET") or "").strip()
            if not client_id or not client_secret:
                return send_json(self, 503, {"error": "네이버 지도 설정이 완료되지 않았습니다."})
            params = {"coords": f"{longitude},{latitude}", "output": "json", "orders": "admcode,legalcode,roadaddr,addr"}
            request = Request(f"{REVERSE_GEOCODE_URL}?{urlencode(params)}", headers={
                "x-ncp-apigw-api-key-id": client_id,
                "x-ncp-apigw-api-key": client_secret,
                "Accept": "application/json",
            })
            with urlopen(request, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            results = data.get("results", [])
            if not results:
                return send_json(self, 422, {"error": "현재 위치의 주소를 찾지 못했습니다."})
            result = results[-1]
            region = result.get("region", {})
            area = " ".join(filter(None, [region.get("area2", {}).get("name"), region.get("area3", {}).get("name")] ))
            land = result.get("land") or {}
            address = " ".join(filter(None, [
                region.get("area1", {}).get("name"), region.get("area2", {}).get("name"), region.get("area3", {}).get("name"),
                land.get("name"), land.get("number1"), land.get("number2"),
            ]))
            send_json(self, 200, {"address": address, "area": area})
        except ValueError:
            send_json(self, 400, {"error": "현재 위치 정보를 확인할 수 없습니다."})
        except Exception as error:
            send_json(self, 503, {"error": str(error) or "주소를 불러오지 못했습니다."})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
