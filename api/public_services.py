import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from api._common import (
    RequestError,
    contains_sensitive_info,
    enforce_rate_limit,
    handle_options,
    read_json_body,
    send_error,
    send_json,
    validate_text,
)

API_URL = "https://api.odcloud.kr/api/gov24/v3/serviceList"
MAX_RESULTS = 6
MIN_RELEVANCE_SCORE = 3

AUDIENCE_ALIASES = {
    "장애": "장애인", "장애인": "장애인", "임산부": "임산부", "출산": "출산",
    "한부모": "한부모", "다문화": "다문화", "청년": "청년", "노인": "노인",
    "어르신": "노인", "구직": "구직자", "실업": "구직자", "농업": "농업인",
}
STOPWORDS = {
    "지원", "서비스", "혜택", "신청", "정보", "필요", "관련", "받고", "싶어요", "있나요",
    "알려줘", "알려주세요", "도와줘", "도움", "대한", "어떤", "화성", "화성시", "화성특례시",
}
CENTRAL_MARKERS = ("중앙행정기관", "공공기관", "중앙부처")
LOCAL_TYPE_MARKERS = ("지방자치단체", "지자체", "광역자치단체", "기초자치단체")
OTHER_LOCAL_RE = re.compile(r"(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|제주특별자치도|(?<!화성)(?:수원|용인|성남|고양|부천|안산|안양|평택|시흥|김포|광명|광주|군포|하남|오산|이천|안성|의왕|양평|여주|과천|의정부|남양주|파주|양주|구리|포천|동두천)[시군구])")
GENERIC_LOCAL_RE = re.compile(r"(?:특별시|광역시|특별자치시|특별자치도|도청|시청|군청|구청|(?:^|\s)[가-힣]{2,}(?:시|군|구)(?:\s|$))")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def search_terms(query):
    normalized = re.sub(r"\s+", " ", query.strip())
    audiences = []
    for needle, value in AUDIENCE_ALIASES.items():
        if needle in normalized and value not in audiences:
            audiences.append(value)
    words = re.findall(r"[가-힣A-Za-z0-9]{2,}", normalized)
    names = []
    for word in words:
        if word in STOPWORDS or word in audiences or word in names:
            continue
        names.append(word)
    return audiences[:2], names[:3]


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
        headers={"Accept": "application/json", "User-Agent": "hwaseong-life-navi/2.0"},
    )
    with urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data") or []
    return data if isinstance(data, list) else []


def is_hwaseong_or_national(item):
    if not isinstance(item, dict):
        return False
    agency = " ".join(str(item.get(key) or "") for key in ("소관기관명", "접수기관", "소관기관"))
    agency_type = " ".join(str(item.get(key) or "") for key in ("소관기관유형", "기관유형"))
    scope = agency + ' ' + ' '.join(str(item.get(k) or '') for k in ('서비스명', '지원대상', '선정기준'))
    if OTHER_LOCAL_RE.search(scope):
        return False
    if re.search(r'(?:화성시|화성특례시)', agency):
        return True
    if any(marker in agency_type for marker in CENTRAL_MARKERS):
        return True
    if any(marker in agency_type for marker in LOCAL_TYPE_MARKERS):
        # 경기도 광역사업은 화성시민도 대상일 수 있으므로 허용하되, 다른 기초지자체는 제외합니다.
        if "경기도" in agency and not OTHER_LOCAL_RE.search(agency):
            return True
        return False
    if OTHER_LOCAL_RE.search(agency):
        return False
    # 기관유형 누락 데이터에서도 명백한 타 지자체 기관명은 제외합니다.
    if GENERIC_LOCAL_RE.search(agency) and "화성" not in agency and agency.strip() != "경기도":
        return False
    # 기관유형과 지역표기가 모두 없는 중앙기관·공공기관 데이터만 보수적으로 허용합니다.
    return agency.strip() in ('경기도', '대한민국', '전국') or bool(re.search(r'(?:보건복지부|행정안전부|국토교통부|고용노동부|교육부|여성가족부|질병관리청|국세청|한국장학재단|국민건강보험공단|국민연금공단)', agency))


def clean_text(value, limit):
    text = CONTROL_RE.sub("", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def safe_url(value):
    value = str(value or "").strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        parsed = None
    if parsed and parsed.scheme == "https" and parsed.netloc and not parsed.username and not parsed.password:
        return value
    return "https://www.gov.kr/portal/rcvfvrSvc/main"


def list_value(value, fallback):
    value = str(value or "").strip()
    if not value:
        return [fallback]
    parts = [clean_text(part.strip(" -•"), 300) for part in re.split(r"[\n•]", value) if part.strip(" -•")]
    return parts[:5] or [fallback]


def normalize_service(item, matched_term):
    service_id = clean_text(item.get("서비스ID"), 100)
    office = clean_text(item.get("접수기관") or item.get("소관기관명") or "공식 상세 안내 확인", 300)
    nationwide = "전국" in office and any(word in office for word in ("읍면동", "주민센터", "행정복지센터"))
    result = {
        "id": f"PUBLIC-{service_id}",
        "category": "public-data",
        "category_label": "공공서비스",
        "title": clean_text(item.get("서비스명") or "공공서비스", 120),
        "priority": 50,
        "summary": clean_text(item.get("서비스목적요약") or item.get("지원내용") or "정부24 공공서비스 안내입니다.", 800),
        "who": clean_text(item.get("지원대상") or item.get("선정기준") or "공식 상세 안내에서 지원대상을 확인하세요.", 800),
        "when": clean_text(item.get("신청기한") or "공식 상세 안내에서 신청기한을 확인하세요.", 300),
        "method": list_value(item.get("신청방법"), "공식 상세 페이지에서 신청방법 확인"),
        "documents": ["공식 상세 페이지에서 구비서류 확인"],
        "office": office[:300],
        "processing_time": "공식 상세 안내 확인",
        "source_name": f"정부24 · {clean_text(item.get('소관기관명') or '대한민국 공공서비스', 100)}",
        "source_url": safe_url(item.get("상세조회URL")),
        "source_checked": "",
        "retrieved_at": date.today().isoformat(),
        "verification_note": "공공데이터 조회 결과입니다. 조회일은 행정내용 검증일이 아닙니다.",
        "keywords": [clean_text(matched_term, 50)],
        "offline_notice": "접수 가능 기관과 방문 전 준비사항을 공식 상세 페이지에서 확인하세요.",
    }
    if nationwide:
        result["office_mode"] = "nationwide_nearest"
    return result


def relevance_score(item, query, matched_term):
    title = str(item.get("서비스명") or "")
    audience = str(item.get("지원대상") or "")
    summary = str(item.get("서비스목적요약") or item.get("지원내용") or "")
    score = 0
    for term in set(re.findall(r"[가-힣A-Za-z0-9]{2,}", query) + [matched_term]):
        if term in title:
            score += 5
        if term in audience:
            score += 3
        if term in summary:
            score += 1
    if score and "화성" in str(item.get("소관기관명") or ""):
        score += 6
    return score


def search_public_services(query, service_key):
    audiences, names = search_terms(query)
    searches = [("사용자구분", term) for term in audiences]
    searches.extend(("서비스명", term) for term in audiences)
    searches.extend(("서비스명", term) for term in names)
    if not searches:
        searches = [("서비스명", query.strip())]
    searches = searches[:5]

    candidates = {}
    successful_requests = 0
    failures = []
    with ThreadPoolExecutor(max_workers=len(searches)) as executor:
        futures = {executor.submit(fetch_page, service_key, condition, term): term for condition, term in searches}
        for future in as_completed(futures):
            term = futures[future]
            try:
                items = future.result()
                successful_requests += 1
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError, AttributeError) as error:
                failures.append(error)
                continue
            for item in items:
                if not is_hwaseong_or_national(item):
                    continue
                service_id = clean_text(item.get("서비스ID"), 100)
                if not service_id:
                    continue
                score = relevance_score(item, query, term)
                if score < MIN_RELEVANCE_SCORE:
                    continue
                previous = candidates.get(service_id)
                if previous is None or score > previous[0]:
                    candidates[service_id] = (score, normalize_service(item, term))

    if successful_requests == 0 and failures:
        auth_error = next((error for error in failures if isinstance(error, HTTPError) and error.code in (401, 403)), None)
        raise auth_error or failures[0]

    ranked = sorted(candidates.values(), key=lambda pair: (-pair[0], pair[1]["title"], pair[1]["id"]))
    return [service for _, service in ranked[:MAX_RESULTS]]


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            enforce_rate_limit(self, "public-services", limit=18)
            body = read_json_body(self)
            query = validate_text(body.get("query"), field="검색 상황", max_length=300, required=True)
            if contains_sensitive_info(query):
                return send_json(self, 200, {
                    "services": [], "configured": bool(os.getenv("PUBLIC_DATA_SERVICE_KEY")),
                    "note": "개인정보로 보이는 내용이 포함되어 외부 공공데이터 검색을 건너뛰었습니다.",
                })

            service_key = (os.getenv("PUBLIC_DATA_SERVICE_KEY") or "").strip()
            if not service_key:
                return send_json(self, 200, {
                    "services": [], "configured": False,
                    "available": False,
                    "status": "not_configured",
                    "note": "등록된 공식 생활 파일을 정상 검색했습니다. 공공데이터 확장 검색은 선택 연동이며 현재 꺼져 있습니다.",
                })
            try:
                services = search_public_services(query, service_key)
                note = "정부24 공공서비스 중 화성시·경기도·전국 적용 가능성이 있는 결과를 함께 검색했습니다."
                status = "ready"
                available = True
            except HTTPError as error:
                services = []
                note = "공공데이터 인증 정보를 확인해 주세요." if error.code in (401, 403) else "공공데이터 서버 응답을 확인해 주세요."
                status = "auth_error" if error.code in (401, 403) else "server_error"
                available = False
            except (URLError, TimeoutError):
                services = []
                note = "공공데이터 서버에 잠시 연결할 수 없습니다."
                status = "unavailable"
                available = False
            except Exception:
                services = []
                note = "공공데이터 검색 중 오류가 발생했습니다."
                status = "error"
                available = False
            send_json(self, 200, {"services": services, "configured": True, "available": available, "status": status, "note": note})
        except RequestError as error:
            send_error(self, error)
        except Exception:
            send_json(self, 500, {"error": "공공서비스 검색 중 오류가 발생했습니다."})

    def do_OPTIONS(self):
        handle_options(self)
