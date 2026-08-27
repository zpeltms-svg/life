import json
import os
import re
from datetime import date
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.odcloud.kr/api/gov24/v3/serviceList"
MAX_RESULTS = 6

AUDIENCE_ALIASES = {
    "장애": "장애인",
    "장애인": "장애인",
    "임산부": "임산부",
    "출산": "출산",
    "한부모": "한부모",
    "다문화": "다문화",
    "청년": "청년",
    "노인": "노인",
    "어르신": "노인",
    "구직": "구직자",
    "실업": "구직자",
    "농업": "농업인",
}

STOPWORDS = {
    "지원", "서비스", "혜택", "신청", "정보", "필요", "관련", "받고", "싶어요",
    "있나요", "알려줘", "알려주세요", "도와줘", "도움", "대한", "어떤",
}


def read_json_body(request_handler):
    length = int(request_handler.headers.get("Content-Length", 0))
    return json.loads(request_handler.rfile.read(length) or b"{}")


def search_terms(query):
    normalized = re.sub(r"\s+", " ", query.strip())
    audience = []
    for needle, value in AUDIENCE_ALIASES.items():
        if needle in normalized and value not in audience:
            audience.append(value)

    words = re.findall(r"[가-힣A-Za-z0-9]{2,}", normalized)
    names = []
    for word in words:
        if word in STOPWORDS or word in audience or word in names:
            continue
        names.append(word)
    return audience[:2], names[:3]


def fetch_page(service_key, condition_name, term):
    params = {
        "page": 1,
        "perPage": 50,
        "returnType": "JSON",
        "serviceKey": service_key,
        f"cond[{condition_name}::LIKE]": term,
    }
    request = Request(
        f"{API_URL}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "hwaseong-life-navi/1.0"},
    )
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8")).get("data", [])


def safe_url(value):
    value = str(value or "").strip()
    return value if value.startswith("https://") else "https://www.gov.kr/portal/rcvfvrSvc/main"


def list_value(value, fallback):
    value = str(value or "").strip()
    if not value:
        return [fallback]
    parts = [part.strip(" -•") for part in re.split(r"[\n•]", value) if part.strip(" -•")]
    return parts[:5] or [fallback]


def normalize_service(item, matched_term):
    service_id = str(item.get("서비스ID") or "").strip()
    office = str(item.get("접수기관") or item.get("소관기관명") or "공식 상세 안내 확인").strip()
    nationwide = "전국" in office and any(word in office for word in ("읍면동", "주민센터", "행정복지센터"))
    result = {
        "id": f"PUBLIC-{service_id}",
        "category": "public-data",
        "category_label": "공공서비스",
        "title": str(item.get("서비스명") or "공공서비스").strip(),
        "priority": 50,
        "summary": str(item.get("서비스목적요약") or item.get("지원내용") or "정부24 공공서비스 안내입니다.").strip(),
        "who": str(item.get("지원대상") or item.get("선정기준") or "공식 상세 안내에서 지원대상을 확인하세요.").strip(),
        "when": str(item.get("신청기한") or "공식 상세 안내에서 신청기한을 확인하세요.").strip(),
        "method": list_value(item.get("신청방법"), "공식 상세 페이지에서 신청방법 확인"),
        "documents": ["공식 상세 페이지에서 구비서류 확인"],
        "office": office,
        "processing_time": "공식 상세 안내 확인",
        "source_name": f"정부24 · {str(item.get('소관기관명') or '대한민국 공공서비스').strip()}",
        "source_url": safe_url(item.get("상세조회URL")),
        "source_checked": date.today().isoformat(),
        "keywords": [matched_term],
        "offline_notice": "접수 가능 기관과 방문 전 준비사항을 공식 상세 페이지에서 확인하세요.",
    }
    if nationwide:
        result["office_mode"] = "nationwide_nearest"
    return result


def search_public_services(query, service_key):
    audiences, names = search_terms(query)
    searches = [("사용자구분", term) for term in audiences]
    searches.extend(("서비스명", term) for term in audiences)
    searches.extend(("서비스명", term) for term in names)
    if not searches:
        searches = [("서비스명", query.strip())]

    found = {}
    for condition, term in searches[:5]:
        for item in fetch_page(service_key, condition, term):
            service_id = str(item.get("서비스ID") or "").strip()
            if service_id and service_id not in found:
                found[service_id] = normalize_service(item, term)
            if len(found) >= MAX_RESULTS:
                return list(found.values())
    return list(found.values())


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = read_json_body(self)
            query = str(body.get("query", "")).strip()[:300]
            if not query:
                return self.send_json(400, {"error": "검색할 상황을 입력해 주세요."})

            service_key = os.getenv("PUBLIC_DATA_SERVICE_KEY", "").strip()
            if not service_key:
                return self.send_json(200, {
                    "services": [],
                    "configured": False,
                    "note": "공공데이터 검색 키가 설정되지 않아 등록된 생활 파일만 검색했습니다.",
                })

            services = search_public_services(query, service_key)
            self.send_json(200, {
                "services": services,
                "configured": True,
                "note": "공공데이터포털의 대한민국 공공서비스 정보를 함께 검색했습니다.",
            })
        except HTTPError as exc:
            note = "인증 정보를 확인해 주세요." if exc.code in (401, 403) else "공공데이터 서버 응답을 확인해 주세요."
            self.send_json(200, {"services": [], "configured": True, "note": note})
        except (URLError, TimeoutError):
            self.send_json(200, {"services": [], "configured": True, "note": "공공데이터 서버에 잠시 연결할 수 없습니다."})
        except Exception:
            self.send_json(200, {"services": [], "configured": True, "note": "공공데이터 검색 중 오류가 발생했습니다."})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
