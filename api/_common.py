import ipaddress
import json
import re
import threading
import time
import unicodedata
from collections import defaultdict, deque

MAX_BODY_BYTES = 4096
_RATE_BUCKETS = defaultdict(deque)
_RATE_LOCK = threading.Lock()

SENSITIVE_PATTERNS = [
    re.compile(r"(?<!\d)(?:\d[ -]?){11,19}(?!\d)"),  # 카드·계좌번호 형태
    re.compile(r"\b\d{6}\s*[- ]?\s*[1-8]\d{6}\b"),
    re.compile(r"\b01[016789]\s*[- ]?\s*\d{3,4}\s*[- ]?\s*\d{4}\b"),
    re.compile(r"\b0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70|50\d)\s*[- ]?\s*\d{3,4}\s*[- ]?\s*\d{4}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b\d{3}\s*[- ]?\s*\d{2}\s*[- ]?\s*\d{5}\b"),
    re.compile(r"[가-힣A-Za-z0-9·.()-]{1,30}(?:대로|로|길)\s*\d{1,5}(?:-\d{1,5})?(?:\s*\d{1,4}동)?"),
    re.compile(r"[가-힣A-Za-z0-9·.()-]{1,20}(?:읍|면|동|리)\s+\d{1,5}(?:-\d{1,5})?\b"),
]


class RequestError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def read_json_body(handler, max_bytes=MAX_BODY_BYTES):
    if handler.headers.get('Transfer-Encoding'):
        raise RequestError(400, "요청 전송 형식을 확인해 주세요.")
    if handler.headers.get('Content-Type') and handler.headers.get('Content-Type').split(';')[0].strip().lower() != 'application/json':
        raise RequestError(415, "JSON 요청만 지원합니다.")
    raw_length = handler.headers.get("Content-Length")
    if raw_length is None:
        raise RequestError(411, "요청 본문 길이를 확인할 수 없습니다.")
    try:
        length = int(raw_length)
    except (TypeError, ValueError):
        raise RequestError(400, "잘못된 요청입니다.")
    if length < 0 or length > max_bytes:
        raise RequestError(413, "요청 내용이 너무 깁니다.")
    raw = handler.rfile.read(length)
    if len(raw) != length:
        raise RequestError(400, "요청 내용이 완전하지 않습니다.")
    try:
        body = json.loads(raw or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RequestError(400, "JSON 요청 형식을 확인해 주세요.")
    if not isinstance(body, dict):
        raise RequestError(400, "요청 형식을 확인해 주세요.")
    return body


def client_key(handler):
    candidates = []
    import os
    forwarded = (handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip() if os.getenv('VERCEL') == '1' else ''
    if forwarded:
        candidates.append(forwarded)
    if getattr(handler, "client_address", None):
        candidates.append(str(handler.client_address[0] or "").strip())
    for candidate in candidates:
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return "unknown"


def enforce_rate_limit(handler, bucket, limit=30, window_seconds=60):
    now = time.monotonic()
    key = f"{bucket}:{client_key(handler)}"
    cutoff = now - window_seconds
    with _RATE_LOCK:
        if key not in _RATE_BUCKETS and len(_RATE_BUCKETS) >= 2048:
            for expired in [k for k,q in _RATE_BUCKETS.items() if not q or q[-1] < cutoff]:
                _RATE_BUCKETS.pop(expired, None)
            if len(_RATE_BUCKETS) >= 2048:
                raise RequestError(429, "요청이 많습니다. 잠시 후 다시 시도해 주세요.")
        queue = _RATE_BUCKETS[key]
        while queue and queue[0] < cutoff:
            queue.popleft()
        if len(queue) >= limit:
            raise RequestError(429, "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
        queue.append(now)
        # Serverless 인스턴스가 오래 유지될 때의 메모리 상한 보호.
        if len(_RATE_BUCKETS) > 2048:
            stale = [k for k, q in _RATE_BUCKETS.items() if not q or q[-1] < cutoff]
            for stale_key in stale[:512]:
                _RATE_BUCKETS.pop(stale_key, None)


def contains_sensitive_info(value=""):
    text = unicodedata.normalize('NFKC', str(value or ""))
    text = re.sub(r'[\u200b-\u200f\u2060\ufeff]', '', text)
    text = re.sub(r'[\u2010-\u2015\u2212]', '-', text)
    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)


def validate_text(value, *, field="입력값", max_length=300, required=False):
    if value is not None and not isinstance(value, str):
        raise RequestError(400, f"{field} 형식을 확인해 주세요.")
    text = str(value or "").strip()
    if required and not text:
        raise RequestError(400, f"{field}을(를) 입력해 주세요.")
    if len(text) > max_length:
        raise RequestError(400, f"{field}은(는) {max_length}자 이내로 입력해 주세요.")
    return text


def validate_coordinates(latitude, longitude):
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise RequestError(400, "현재 위치 정보를 확인할 수 없습니다.")
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        raise RequestError(400, "현재 위치 정보를 확인할 수 없습니다.")
    # 이 서비스는 대한민국 내 네이버 지도 경로 탐색만 지원합니다.
    if not (32.0 <= lat <= 40.0 and 124.0 <= lng <= 133.0):
        raise RequestError(400, "대한민국 내 위치만 지원합니다.")
    return lat, lng


def send_json(handler, status, payload, *, cache_control="no-store"):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", cache_control)
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    if status == 429:
        handler.send_header('Retry-After', '60')
    handler.end_headers()
    handler.wfile.write(data)


def send_error(handler, error):
    if isinstance(error, RequestError):
        send_json(handler, error.status, {"error": error.message})
    else:
        send_json(handler, 500, {"error": "처리 중 오류가 발생했습니다."})


def handle_options(handler):
    handler.send_response(204)
    handler.send_header("Allow", "POST, OPTIONS")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
