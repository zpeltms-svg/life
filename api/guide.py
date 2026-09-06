import json
import os
import re
import unicodedata
from http.server import BaseHTTPRequestHandler
from pathlib import Path

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

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "services.json"


def load_services():
    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)["services"]


def _normalize(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"[.,!?;:()\[\]{}\"'`~@#$%^&*_+=|\\/<>]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact(value):
    return re.sub(r"\s+", "", _normalize(value))


def _weight(keyword):
    size = len(_compact(keyword))
    if size >= 6:
        return 8
    if size >= 4:
        return 6
    if size >= 2:
        return 4
    return 3


def _score_service(query, service):
    normalized = _normalize(query)
    compact = _compact(query)
    if not normalized:
        return 0
    if any(_compact(word) in compact for word in service.get('exclude_keywords', [])):
        return 0
    score = 0
    for group in service.get('intent_groups', []):
        if all(_compact(word) in compact for word in group):
            score += 8
    title = _normalize(service.get("title"))
    title_compact = _compact(service.get("title"))
    if title and title in normalized:
        score += 14
    if title_compact and title_compact in compact:
        score += 14
    seen = set()
    for keyword in service.get("keywords", []):
        normalized_keyword = _normalize(keyword)
        compact_keyword = _compact(keyword)
        if not normalized_keyword or compact_keyword in seen:
            continue
        seen.add(compact_keyword)
        if normalized_keyword in normalized or compact_keyword in compact:
            score += _weight(keyword)
    for negative in service.get("negative_keywords", []):
        normalized_negative = _normalize(negative)
        compact_negative = _compact(negative)
        if normalized_negative and (normalized_negative in normalized or compact_negative in compact):
            score -= 12
    for token in title.split(" "):
        if len(token) >= 2 and token in normalized:
            score += 2
    return score


def keyword_fallback(query, services, limit=6):
    scored = []
    for service in services:
        score = _score_service(query, service)
        if score >= 4:
            scored.append((score, service.get("priority", 99), str(service.get("id") or "")))
    birth = bool(re.search(r'(?:아기|아이|자녀).*(?:태어|낳)|출산했|출생신고', _compact(query)))
    order = ['BIRTH-001', 'BIRTH-002', 'BIRTH-003', 'BIRTH-004', 'BIRTH-005'] if birth else []
    scored.sort(key=lambda item: (order.index(item[2]) if item[2] in order else 10, -item[0], item[1], item[2]))
    return [item[2] for item in scored[:limit]]


def ai_select(query, services):
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None

    from openai import OpenAI

    compact = [
        {
            "id": service["id"],
            "category": service["category_label"],
            "title": service["title"],
            "summary": service["summary"],
            "keywords": service.get("keywords", []),
        }
        for service in services
    ]
    ids = [service["id"] for service in services]
    schema = {
        "type": "object",
        "properties": {
            "service_ids": {
                "type": "array",
                "items": {"type": "string", "enum": ids},
            },
        },
        "required": ["service_ids"],
        "additionalProperties": False,
    }
    system = (
        "당신은 화성생활 내비의 상황 분류 보조자입니다. "
        "제공된 서비스 목록만 사용하고 행정 사실을 새로 만들지 마세요. "
        "관련성이 높은 서비스 id를 최대 6개 고르며, 관련 서비스가 없으면 빈 배열을 반환하세요."
    )
    client = OpenAI(api_key=api_key, timeout=8.0, max_retries=0)
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        store=False,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"사용자 상황: {query}\n서비스 목록: {json.dumps(compact, ensure_ascii=False)}"},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "service_selection",
                "strict": True,
                "schema": schema,
            }
        },
        max_output_tokens=250,
    )
    parsed = json.loads(response.output_text)
    if not isinstance(parsed, dict) or not isinstance(parsed.get('service_ids'), list):
        return None
    allowed = set(ids)
    selected = []
    for service_id in parsed.get("service_ids", []):
        if isinstance(service_id, str) and service_id in allowed and service_id not in selected:
            selected.append(service_id)
    selected = [sid for sid in selected if not any(_compact(word) in _compact(query) for word in next(s for s in services if s['id'] == sid).get('exclude_keywords', []))]
    return {"service_ids": selected[:6], "note": "등록된 서비스 목록에서 관련 항목을 선택했습니다.", "used_ai": True}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            enforce_rate_limit(self, "guide", limit=24)
            body = read_json_body(self)
            query = validate_text(body.get("query"), field="상황", max_length=300, required=True)
            services = load_services()

            if contains_sensitive_info(query):
                return send_json(self, 200, {
                    "service_ids": keyword_fallback(query, services),
                    "note": "개인정보로 보이는 내용이 포함되어 AI 연동 없이 등록된 생활 파일만 검색했습니다.",
                    "used_ai": False,
                })

            result = None
            try:
                result = ai_select(query, services)
            except Exception:
                result = None

            if not result:
                result = {
                    "service_ids": keyword_fallback(query, services),
                    "note": "입력한 상황과 관련된 등록 생활행정 정보를 찾았습니다.",
                    "used_ai": False,
                }
            send_json(self, 200, result)
        except RequestError as error:
            send_error(self, error)
        except Exception:
            send_json(self, 500, {"error": "생활행정 검색 중 오류가 발생했습니다."})

    def do_OPTIONS(self):
        handle_options(self)
