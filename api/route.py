import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from api._common import (
    RequestError,
    enforce_rate_limit,
    handle_options,
    read_json_body,
    send_error,
    send_json,
    validate_coordinates,
    validate_text,
)
from api._naver_maps import driving_route, geocode_address
from api._centers import center_for_destination

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "services.json"


def get_service(service_id):
    with DATA_PATH.open("r", encoding="utf-8") as file:
        services = json.load(file)["services"]
    return next((item for item in services if item["id"] == service_id), None)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            enforce_rate_limit(self, "route", limit=20)
            body = read_json_body(self)
            origin = body.get("origin") if isinstance(body.get("origin"), dict) else {}
            latitude, longitude = validate_coordinates(origin.get("latitude"), origin.get("longitude"))
            service_id = validate_text(body.get("service_id"), field="서비스 ID", max_length=64)
            service = get_service(service_id) if service_id else None
            query = validate_text(body.get("destination_query"), field="목적지", max_length=120)
            destination = {"name": query, "address": query} if query else (service or {}).get("visit_destination")
            if not destination:
                raise RequestError(422, "제출기관을 선택하거나 목적지를 입력해 주세요.")

            address = validate_text(destination.get("address"), field="목적지", max_length=120, required=True)
            center = center_for_destination(address)
            target = {"latitude": center['lat'], "longitude": center['lng'], "address": center['address']} if center and 'lat' in center else geocode_address(address, reference=(latitude, longitude))
            candidate = driving_route((latitude, longitude), (target["latitude"], target["longitude"]))
            summary = candidate["summary"]
            path = candidate.get("path") or []
            send_json(self, 200, {
                "destination": validate_text(destination.get("name") or address, field="목적지명", max_length=120),
                "address": target.get("address") or address,
                "latitude": target["latitude"],
                "longitude": target["longitude"],
                "distance_m": int(summary.get("distance") or 0),
                "duration_ms": int(summary.get("duration") or 0),
                "path": path,
                "routes": [{
                    "key": "trafast",
                    "label": "빠른 길",
                    "distance_m": int(summary.get("distance") or 0),
                    "duration_ms": int(summary.get("duration") or 0),
                    "path": path,
                }],
                "map_client_id": (os.getenv("NCP_MAPS_CLIENT_ID") or "").strip(),
            })
        except RequestError as error:
            send_error(self, error)
        except Exception:
            send_json(self, 503, {"error": "경로 정보를 불러오지 못했습니다."})

    def do_OPTIONS(self):
        handle_options(self)
