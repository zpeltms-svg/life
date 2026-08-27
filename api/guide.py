import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "services.json"


def load_services():
    with DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)["services"]


def keyword_fallback(query, services):
    q = query.lower()
    scores = []
    for service in services:
        score = sum(3 if len(k) >= 4 else 2 for k in service.get("keywords", []) if k.lower() in q)
        scores.append((score, service))
    categories = {s[1]["category"] for s in scores if s[0] > 0}
    matches = [s for s in services if s["category"] in categories]
    matches.sort(key=lambda x: x.get("priority", 99))
    return [s["id"] for s in matches[:6]]


def ai_select(query, services):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    from openai import OpenAI

    compact = [
        {
            "id": s["id"],
            "category": s["category_label"],
            "title": s["title"],
            "summary": s["summary"],
            "keywords": s.get("keywords", []),
        }
        for s in services
    ]
    client = OpenAI(api_key=api_key)
    prompt = f"""
당신은 '화성생활 내비'의 상황 분류 보조자입니다.
아래 서비스 목록에 존재하는 정보만 사용하세요.
사용자 상황과 관련성이 높은 서비스 id를 우선순위대로 최대 6개 고르세요.
관련 서비스가 없으면 빈 배열을 반환하세요.
행정적 판단이나 새로운 사실을 만들지 마세요.

사용자 상황: {query}
서비스 목록: {json.dumps(compact, ensure_ascii=False)}

반드시 아래 JSON 형식만 반환하세요.
{{"service_ids":["ID"],"note":"시민에게 보여줄 짧은 한 문장"}}
"""
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=prompt,
    )
    text = response.output_text.strip()
    return json.loads(text)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            query = str(body.get("query", "")).strip()[:300]
            if not query:
                return self.send_json(400, {"error": "질문을 입력해 주세요."})

            services = load_services()
            try:
                result = ai_select(query, services)
            except Exception:
                result = None

            if not result:
                result = {
                    "service_ids": keyword_fallback(query, services),
                    "note": "입력한 상황과 관련된 화성시 생활행정 정보를 찾았습니다."
                }
            self.send_json(200, result)
        except Exception as exc:
            self.send_json(500, {"error": "처리 중 오류가 발생했습니다.", "detail": str(exc)[:200]})

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
