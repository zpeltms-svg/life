import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))

def main():
    gate=read('QUALITY_GATE_RESULTS.json');backtest=read('BACKTEST_RESULTS.json');reviews=read('REVIEW_RESULTS.json');e2e=read('E2E_RESULTS.json')
    assert gate['ok'] and backtest['ok'] and reviews['ok'] and e2e['ok']
    regression=next(s for s in gate['stages'] if s['stage']=='regression')['output']
    count=int(re.search(r'Ran (\d+) tests',regression)[1])
    lines=['# 화성생활 내비 품질 보고서','',f"- 실행 시각(UTC): {gate['checked_at']}",'- 대상: 이번 작업의 `hwaseong-life-navi` 구현본. 기존 제공 보고서의 통과 횟수는 재사용하지 않음.',f'- 회귀테스트: **{count}개 PASS**',f"- 전체 품질게이트: **{len(gate['stages'])}개 단계 PASS**",f"- 서로 다른 품질영역 검토: **{reviews['review_domains']}개 PASS**",f"- 독립 백테스트: **{backtest['independent_runs']}회 PASS**",f"- 자연어 문장: **{backtest['cases_per_round']}개**",f"- seed당 shuffle round: **{backtest['rounds_per_run']}회**, 전체 **{backtest['total_rounds']}회**",f"- 백테스트 assertion: **{backtest['total_assertions']:,}회 PASS**",f"- seed: `{', '.join(map(str,backtest['seeds']))}`",'- E2E: 실제 HTTP 및 CSP 기반 기본 시나리오 PASS, 장애·개인정보·모바일 시나리오 PASS',f"- 브라우저 page error: **{e2e['page_errors']}건**",'- 정적 검사: Python compile, JS syntax, JSON 구조·날짜·공식 URL·중복 검사 PASS','- Secret scan: 실제 자격증명 형태·개인 환경파일 발견 없음','- SDK 3.8.0: 실제 설치·메모리 전송 요청/응답 검증 PASS, live API 요청 0건','', '## 화면 크기','', '| 화면 | 결과 |','|---|---|']
    for row in e2e['viewports']:lines.append(f"| {row['width']} × {row['height']} | PASS · 가로 넘침 없음 · 모달 범위 정상 |")
    lines+=['','## 독립 품질영역','']
    for row in reviews['rows']:lines.append(f"{row['review']}. {row['domain']}: PASS — {row['evidence']}")
    lines+=['','## 발견한 실패와 수정','',
      '- 기존 개인정보 탐지에 카드·계좌번호와 일부 유니코드 변형이 빠져 있어 양단 차단을 보완했다.',
      '- 기존 센터 데이터에 좌표가 없고 남양읍·동탄9동 주소가 최신 공식 안내와 달랐다. 공식 안내에 포함된 지도에서 29개 센터 좌표를 확보하고 두 주소를 수정했다.',
      '- “주소를 바꾸고 싶어요”, “여권이 만료됐어요”, “청년인데 창업하려고 해요” 검색이 실패했다. 문맥 조합을 클라이언트·서버에 함께 적용하고 정답셋에 추가했다.',
      '- 첫만남이용권은 기존 정답셋에서 미지원 항목이었다. 기능 추가 후 동일 문장의 예상 결과를 검색·순위 검증으로 갱신했다.',
      '- 기존 Linux 고정 E2E 경로와 CSP에서 금지된 문자열 eval 테스트 대기식을 발견했다. 크로스플랫폼 브라우저 실행과 함수형 대기로 수정했다. CSP의 unsafe-eval 허용은 추가하지 않았다.',
      '- 지도 실패 후 방문지 버튼의 구조가 사라지는 문제를 화면 검토에서 발견해 복원 처리했다.',
      '- 기존 20회 리뷰는 같은 검사의 반복이었다. 이번 결과는 27개 서로 다른 품질영역에 대한 증거를 기록한다.',
      '- 테스트 도구 설치는 최초 제한된 네트워크에서 실패했고, 승인된 설치로 완료했다. 이후 검증은 모두 재실행했다.',
      '', '## 실제 확인 범위와 제한','',
      '- 36개 서비스로 요구 최소 30개를 충족한다. 50개 확장은 완료 항목이 아니다.',
      '- 기존 32개 상세정보는 제공된 자료를 바탕으로 유지했다. 신규 출산서비스, 출산지원금, 4개 구 구성과 센터 위치는 공식 본문을 대조했다. HTTP 성공을 전체 행정내용 검증으로 계산하지 않았다.',
      '- 부동산거래관리시스템·인터넷등기소·무공해차 통합누리집은 자동 점검에서 본문을 읽지 못했다. 해당 3개 서비스는 재확인 필요 표시와 제한 사유를 제공한다. 출처별 상태는 SOURCE_AUDIT.json 참고.',
      '- 운영 API 키로 OpenAI·공공데이터·네이버의 실서비스를 호출하지 않았으며 Vercel 배포도 수행하지 않았다. 성공 계약은 모의 응답 및 실제 SDK 메모리 전송으로 검증했다.',
      '- Windows Python 3.12.10 / Node.js 24.20.0 / Playwright 1.55.0 Chromium으로 검증했다. Vercel 대상 Python 3.13의 클라우드 빌드 및 macOS/Linux 실행기는 해당 OS에서 실기동 검증하지 않았다.',
      '- API rate limit은 프로세스 단위이며 여러 서버리스 인스턴스를 합친 전역 한도가 아니다.',
      '- 개인정보 탐지는 형태 기반이며 모든 개인정보를 완벽하게 식별한다고 보장하지 않는다.',
      '', '## 패키징·무결성','',
      f"- 검증 소스 SHA-256: `{gate['fingerprint']}`",
      '- `tests/package_release.py`는 품질게이트 성공 후 ZIP을 만들고 CRC 검사·안전한 새 폴더 재해제·전체 품질게이트 재실행·소스 해시 대조를 수행한다.',
      '- 재해제까지 통과한 경우에만 최종 `hwaseong-life-navi-production.zip`으로 확정한다.',
      '- ZIP에 Git metadata, Python cache/pyc, 설치 도구, 실제 환경파일을 넣지 않는다.',
      '- ZIP 자체 SHA-256과 재해제 판정은 ZIP 옆 `PACKAGE_RESULTS.json`과 `.zip.sha256`에 기록한다. ZIP 내부 파일에 자기 자신의 ZIP 해시를 삽입하지 않는다.',
      '- 패키징 후 생성되는 외부 `QUALITY_REPORT.md`에는 최종 ZIP SHA-256과 재해제 결과를 추가한다.',
      '']
    (ROOT/'QUALITY_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'report: {count} regression tests, {reviews["review_domains"]} review domains')

if __name__=='__main__':main()
