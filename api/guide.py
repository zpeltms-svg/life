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


SEMANTIC_CONCEPTS = [
    ('move', 12, [r'(?:이사|이삿짐|전입|새집|새거주지|거주지를옮|주소.*이전)']),
    ('birth', 11, [r'(?:아기|아이|신생아).*(?:태어|낳)|(?:출산|출생)']),
    ('job', 8, [r'(?:취업|구직|일자리|인턴|채용)']),
    ('startup', 11, [r'(?:창업|가게를?열|사업을?시작|사업장)']),
    ('bulky_waste', 14, [r'(?:소파|침대|장롱|책상|냉장고|세탁기|가구).*(?:버리|치우|폐기|처분)|(?:대형폐기물|폐가구|큰쓰레기)']),
    ('pet', 9, [r'(?:반려동물|강아지|고양이|애완동물)']),
    ('animal_care', 10, [r'(?:동물병원|진료비|아프|예방접종|예방주사|백신|광견병|내장칩)']),
    ('animal_vaccine', 16, [r'(?:광견병|내장칩|종합백신)']),
    ('passport', 14, [r'(?:여권)']),
    ('renewal', 9, [r'(?:재발급|갱신|만료|기한이?끝|잃어버|분실)']),
    ('resident_record', 13, [r'(?:주민등록표?|등본|초본|주소이력)']),
    ('family_certificate', 14, [r'(?:가족관계|기본증명서|혼인관계증명서|가족.*증명.*서류)']),
    ('seal_certificate', 14, [r'(?:인감증명|인감서류)']),
    ('signature_certificate', 14, [r'(?:본인서명|서명사실)']),
    ('marriage', 14, [r'(?:혼인신고|결혼.*신고|혼인등록)']),
    ('death_report', 14, [r'(?:사망신고|사망.*등록)']),
    ('lease_report', 13, [r'(?:임대차|전월세|전세|월세).*(?:계약|신고)']),
    ('fixed_date', 15, [r'(?:확정일자)']),
    ('building_register', 15, [r'(?:건축물대장|건물대장)']),
    ('land_register', 15, [r'(?:토지대장|임야대장)']),
    ('local_tax_certificate', 15, [r'(?:지방세|세금).*(?:완납|납세증명|체납없)']),
    ('vehicle_tax', 15, [r'(?:자동차세|차량세금|차세금)']),
    ('vehicle_registration', 15, [r'(?:자동차|차량|차).*(?:등록증)']),
    ('health_certificate', 15, [r'(?:보건증|건강진단결과서)']),
    ('vaccination', 11, [r'(?:예방접종|예방주사|접종병원|위탁의료기관)']),
    ('water_bill', 15, [r'(?:상하수도|수도).*(?:요금|세|납부|자동이체)']),
    ('kiosk', 15, [r'(?:무인민원|무인발급|24시간.*(?:등본|증명서)|주말.*(?:등본|증명서)|야간.*(?:등본|증명서))']),
    ('complaint', 10, [r'(?:국민신문고|고충민원|민원.*(?:넣|접수|신청))']),
    ('call_center', 12, [r'(?:담당부서.*모르|어디에문의|민원.*전화|시청전화|콜센터)']),
    ('disability_parking', 15, [r'(?:장애인).*(?:주차표지|주차증|차량표지|자동차표지)']),
    ('ev_subsidy', 15, [r'(?:전기차|전기자동차).*(?:보조금|지원금|구매지원)']),
    ('parking_fine', 15, [r'(?:주정차|주차).*(?:과태료|단속|위반|의견진술|이의신청)']),
    ('admin_center', 11, [r'(?:주민센터|행정복지센터).*(?:어디|찾|위치|관할)|(?:관할).*(?:주민센터|행정복지센터)']),
]
CONTEXT_CONCEPTS = {'renewal', 'animal_care'}


def _semantic_concepts(value):
    compact = _compact(value)
    return {name: weight for name, weight, patterns in SEMANTIC_CONCEPTS if any(re.search(pattern, compact) for pattern in patterns)}


def _service_search_text(service):
    groups = [word for group in service.get('intent_groups', []) for word in group]
    return ' '.join(str(value or '') for value in [service.get('title'), *groups, *service.get('semantic_phrases', [])])


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
    query_concepts = {} if re.search(r'(?:취업증명서|사업자등록증|추천|구매|보험|사진관|도장가게|충전소|충전기|배관공사|디자인|투자상담|무엇인가|원리.*궁금|뜻이.*궁금)', compact) else _semantic_concepts(query)
    service_concepts = _semantic_concepts(_service_search_text(service))
    matched_concepts = [(concept, weight) for concept, weight in query_concepts.items() if concept in service_concepts]
    concept_matches = 0
    for concept, weight in matched_concepts:
        if concept in CONTEXT_CONCEPTS and len(matched_concepts) < 2:
            continue
        score += weight
        concept_matches += 1
    if concept_matches >= 2:
        score += 10
    if 'renewal' in query_concepts and 'renewal' not in service_concepts:
        score -= 12
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
            "who": service.get("who", ""),
            "method": service.get("method", []),
            "exclude_keywords": service.get("exclude_keywords", []),
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
        "관련성이 높은 서비스 id를 최대 6개 고르며, 관련 서비스가 없으면 빈 배열을 반환하세요. "
        "사용자의 생활사건, 대상, 원하는 행동을 함께 해석하세요. 단어 하나만 겹치는 서비스는 고르지 말고, "
        "제외 표현과 반대 의도를 반드시 지키며 여러 일이 있으면 처리 순서를 고려해 배열을 정렬하세요."
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
