from http.server import BaseHTTPRequestHandler

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
from api._naver_maps import geocode_address, reverse_location
from api._centers import administrative_center


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            enforce_rate_limit(self, "address", limit=30)
            body = read_json_body(self)
            typed = validate_text(body.get("address"), field="주소", max_length=120, required=False)
            if typed:
                point = geocode_address(typed)
                reverse = reverse_location(point["latitude"], point["longitude"])
                return send_json(self, 200, {
                    "address": point.get("address") or reverse.get("address") or typed,
                    "area": reverse.get("area") or "",
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                    "center": administrative_center(reverse.get('area', '')),
                })

            latitude, longitude = validate_coordinates(body.get("latitude"), body.get("longitude"))
            reverse = reverse_location(latitude, longitude)
            send_json(self, 200, {**reverse, "latitude": latitude, "longitude": longitude, "center": administrative_center(reverse.get('area', ''))})
        except RequestError as error:
            send_error(self, error)
        except Exception:
            send_json(self, 503, {"error": "주소를 불러오지 못했습니다."})

    def do_OPTIONS(self):
        handle_options(self)
