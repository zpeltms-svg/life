import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "services.json"
GEOCODE_URL = "https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode"
DIRECTIONS_URL = "https://naveropenapi.apigw.ntruss.com/map-direction/v1/driving"


def send_json(handler, status, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def naver_request(url, params):
    client_id = os.getenv("NCP_MAPS_CLIENT_ID")
    client_secret = os.getenv("NCP_MAPS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("네이버 지도 설정이 아직 완료되지 않았습니다.")
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={
            "x-ncp-apigw-api-key-id": client_id,
            "x-ncp-apigw-api-key": client_secret,
        },
    )
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


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
            latitude = float(origin.get("latitude"))
            longitude = float(origin.get("longitude"))
            destination = service.get("visit_destination") if service else None
            if not destination:
                return send_json(self, 422, {"error": "이 서비스는 관할 기관 확인이 먼저 필요합니다."})

            geocode = naver_request(GEOCODE_URL, {"query": destination["address"]})
            addresses = geocode.get("addresses", [])
            if not addresses:
                return send_json(self, 422, {"error": "제출기관의 좌표를 찾지 못했습니다."})
            target = addresses[0]
            target_longitude, target_latitude = float(target["x"]), float(target["y"])
            route = naver_request(DIRECTIONS_URL, {
                "start": f"{longitude},{latitude}",
                "goal": f"{target_longitude},{target_latitude}",
                "option": "trafast",
            })
            summary = route.get("route", {}).get("trafast", [{}])[0].get("summary")
            if not summary:
                return send_json(self, 422, {"error": "현재 경로를 찾지 못했습니다."})
            send_json(self, 200, {
                "destination": destination["name"],
                "address": target.get("roadAddress") or destination["address"],
                "latitude": target_latitude,
                "longitude": target_longitude,
                "distance_m": summary["distance"],
                "duration_ms": summary["duration"],
            })
        except ValueError:
            send_json(self, 400, {"error": "현재 위치 정보를 확인할 수 없습니다."})
        except Exception as error:
            message = str(error)
            send_json(self, 503, {"error": message if message else "경로 정보를 불러오지 못했습니다."})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
