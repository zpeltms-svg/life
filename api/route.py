import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "services.json"
GEOCODE_URL = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
DIRECTIONS_URL = "https://maps.apigw.ntruss.com/map-direction/v1/driving"

def send_json(handler, status, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)

def naver_request(url, params):
    client_id = (os.getenv("NCP_MAPS_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("NCP_MAPS_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("네이버 지도 환경변수가 등록되지 않았습니다.")
    request = Request(f"{url}?{urlencode(params)}", headers={
        "x-ncp-apigw-api-key-id": client_id, "x-ncp-apigw-api-key": client_secret, "Accept": "application/json"
    })
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        messages = {
            400: "출발지 또는 목적지 주소를 확인해 주세요.",
            401: "네이버 지도 인증에 실패했습니다. Vercel의 Client ID와 Client Secret을 확인해 주세요.",
            429: "네이버 Maps의 API 권한 또는 호출 한도를 확인해 주세요."
        }
        raise RuntimeError(messages.get(error.code, f"네이버 지도 요청에 실패했습니다. ({error.code})"))

def get_service(service_id):
    with DATA_PATH.open("r", encoding="utf-8") as file:
        services = json.load(file)["services"]
    return next((item for item in services if item["id"] == service_id), None)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            service = get_service(str(body.get("service_id", "")))
            origin = body.get("origin") or {}
            latitude, longitude = float(origin.get("latitude")), float(origin.get("longitude"))
            query = str(body.get("destination_query") or "").strip()
            destination = {"name": query, "address": query} if query else (service.get("visit_destination") if service else None)
            if not destination:
                return send_json(self, 422, {"error": "제출기관을 선택하거나 주소를 입력해 주세요."})
            if len(destination["address"]) > 120:
                return send_json(self, 400, {"error": "목적지는 120자 이내로 입력해 주세요."})
            geocode = naver_request(GEOCODE_URL, {"query": destination["address"], "coordinate": f"{longitude},{latitude}"})
            addresses = geocode.get("addresses", [])
            if not addresses:
                return send_json(self, 422, {"error": "목적지 주소를 찾지 못했습니다. 도로명 주소로 다시 입력해 주세요."})
            target = addresses[0]
            target_lng, target_lat = float(target["x"]), float(target["y"])
            route = naver_request(DIRECTIONS_URL, {
                "start": f"{longitude},{latitude}", "goal": f"{target_lng},{target_lat}", "option": "trafast"
            })
            candidate = route.get("route", {}).get("trafast", [{}])[0]
            summary = candidate.get("summary")
            if not summary:
                return send_json(self, 422, {"error": "현재 위치에서 자동차 경로를 찾지 못했습니다."})
            path = candidate.get("path", [])
            send_json(self, 200, {
                "destination": destination["name"],
                "address": target.get("roadAddress") or target.get("jibunAddress") or destination["address"],
                "latitude": target_lat, "longitude": target_lng,
                "distance_m": summary["distance"], "duration_ms": summary["duration"], "path": path,
                "routes": [{"key": "trafast", "label": "빠른 길", "distance_m": summary["distance"], "duration_ms": summary["duration"], "path": path}],
                "map_client_id": (os.getenv("NCP_MAPS_CLIENT_ID") or "").strip()
            })
        except (TypeError, ValueError):
            send_json(self, 400, {"error": "현재 위치 또는 목적지 정보를 확인해 주세요."})
        except Exception as error:
            send_json(self, 503, {"error": str(error) or "경로 정보를 불러오지 못했습니다."})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
