import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from api._common import RequestError, validate_coordinates

GEOCODE_URL = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
REVERSE_URL = "https://maps.apigw.ntruss.com/map-reversegeocode/v2/gc"
DIRECTIONS_URL = "https://maps.apigw.ntruss.com/map-direction/v1/driving"


def _credentials():
    client_id = (os.getenv("NCP_MAPS_CLIENT_ID") or "").strip()
    secret = (os.getenv("NCP_MAPS_CLIENT_SECRET") or "").strip()
    if not client_id or not secret:
        raise RequestError(503, "네이버 지도 연동이 설정되지 않았습니다.")
    return client_id, secret


def naver_get(url, params, timeout=8):
    if url not in (GEOCODE_URL, REVERSE_URL, DIRECTIONS_URL):
        raise RequestError(400, "지도 요청 경로를 확인해 주세요.")
    client_id, secret = _credentials()
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={
            "x-ncp-apigw-api-key-id": client_id,
            "x-ncp-apigw-api-key": secret,
            "Accept": "application/json",
            "User-Agent": "hwaseong-life-navi/2.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(2_000_001).decode("utf-8"))
            if not isinstance(payload, dict):
                raise RequestError(503, "지도 응답 형식을 확인할 수 없습니다.")
            return payload
    except HTTPError as error:
        if error.code in (401, 403):
            raise RequestError(503, "네이버 지도 인증 또는 API 권한을 확인해 주세요.")
        if error.code == 429:
            raise RequestError(503, "네이버 지도 호출 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.")
        if 400 <= error.code < 500:
            raise RequestError(422, "주소 또는 위치 정보를 확인해 주세요.")
        raise RequestError(503, "네이버 지도 서버가 응답하지 않습니다.")
    except (URLError, TimeoutError):
        raise RequestError(503, "네이버 지도 서버에 잠시 연결할 수 없습니다.")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RequestError(503, "네이버 지도 응답을 해석할 수 없습니다.")


def _region_names(region):
    names = []
    for key in ("area1", "area2", "area3", "area4"):
        name = str((region.get(key) or {}).get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def reverse_location(latitude, longitude):
    data = naver_get(
        REVERSE_URL,
        {"coords": f"{longitude},{latitude}", "output": "json", "orders": "roadaddr,admcode,legalcode,addr"},
    )
    results = data.get("results") or []
    if not results:
        raise RequestError(422, "해당 위치의 주소를 찾지 못했습니다.")
    road = next((item for item in results if item.get("name") == "roadaddr"), None)
    admin = next((item for item in results if item.get("name") == "admcode"), None)
    display = road or admin or results[0]
    if not admin:
        raise RequestError(422, "행정동을 확인하지 못했습니다. 읍·면·동을 직접 선택해 주세요.")
    display_region = display.get("region") or {}
    admin_region = admin.get("region") or {}
    land = display.get("land") or {}

    admin_names = _region_names(admin_region)
    display_names = _region_names(display_region)
    land_parts = [str(land.get("name") or "").strip(), str(land.get("number1") or "").strip()]
    number2 = str(land.get("number2") or "").strip()
    if number2:
        land_parts[-1] = f"{land_parts[-1]}-{number2}" if land_parts[-1] else number2
    address = " ".join(part for part in [*display_names, *land_parts] if part)
    return {"address": address or " ".join(admin_names), "area": " ".join(admin_names)}


def geocode_address(address, reference=None):
    params = {"query": address}
    if reference:
        lat, lng = reference
        params["coordinate"] = f"{lng},{lat}"
    data = naver_get(GEOCODE_URL, params)
    addresses = data.get("addresses") or []
    if not addresses:
        raise RequestError(422, "주소를 찾지 못했습니다. 도로명 주소로 다시 입력해 주세요.")
    item = addresses[0]
    try:
        latitude, longitude = float(item["y"]), float(item["x"])
    except (KeyError, TypeError, ValueError):
        raise RequestError(503, "지도 좌표 응답을 확인할 수 없습니다.")
    validate_coordinates(latitude, longitude)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "address": str(item.get("roadAddress") or item.get("jibunAddress") or address).strip(),
    }


def driving_route(origin, target):
    lat, lng = origin
    target_lat, target_lng = target
    data = naver_get(
        DIRECTIONS_URL,
        {"start": f"{lng},{lat}", "goal": f"{target_lng},{target_lat}", "option": "trafast"},
    )
    candidates = (data.get("route") or {}).get("trafast") or []
    if not candidates or not candidates[0].get("summary"):
        raise RequestError(422, "현재 위치에서 자동차 경로를 찾지 못했습니다.")
    return candidates[0]
