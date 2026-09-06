# 화성생활 내비 품질 보고서

- 실행 시각(UTC): 2026-09-06T16:30:11.648384+00:00
- 대상: 이번 작업의 `hwaseong-life-navi` 구현본. 기존 제공 보고서의 통과 횟수는 재사용하지 않음.
- 회귀테스트: **207개 PASS**
- 전체 품질게이트: **7개 단계 PASS**
- 서로 다른 품질영역 검토: **27개 PASS**
- 독립 백테스트: **15회 PASS**
- 자연어 문장: **304개**
- seed당 shuffle round: **15회**, 전체 **225회**
- 백테스트 assertion: **171,900회 PASS**
- seed: `20260907, 314159, 271828, 8675309, 424242, 999983, 13579, 24680, 112358, 161803, 777777, 888888, 123457, 765431, 555551`
- E2E: 실제 HTTP 및 CSP 기반 기본 시나리오 PASS, 장애·개인정보·모바일 시나리오 PASS
- 브라우저 page error: **0건**
- 정적 검사: Python compile, JS syntax, JSON 구조·날짜·공식 URL·중복 검사 PASS
- Secret scan: 실제 자격증명 형태·개인 환경파일 발견 없음
- SDK 3.8.0: 실제 설치·메모리 전송 요청/응답 검증 PASS, live API 요청 0건

## 화면 크기

| 화면 | 결과 |
|---|---|
| 390 × 844 | PASS · 가로 넘침 없음 · 모달 범위 정상 |
| 412 × 915 | PASS · 가로 넘침 없음 · 모달 범위 정상 |
| 768 × 1024 | PASS · 가로 넘침 없음 · 모달 범위 정상 |
| 1440 × 900 | PASS · 가로 넘침 없음 · 모달 범위 정상 |

## 독립 품질영역

1. 구조: PASS — required files present
2. 문법: PASS — all Python + 5 JavaScript files
3. 서비스 스키마: PASS — 36 services
4. 공식 URL 형식·기관: PASS — 61 official HTTPS links; HTTP content limitations in SOURCE_AUDIT
5. 자료 유효기간: PASS — real dates + explicit unverified-content warnings
6. 센터 좌표·이전주소: PASS — 2 behavioral tests
7. 처리 순서: PASS — registration -> city benefit -> voucher -> parental -> child allowance
8. 자연어 정답·오탐·상태격리: PASS — {"ok":true,"assertions":326,"cases":304}
9. 클라이언트·서버 검색 일치: PASS — 304 frontend/server rankings identical
10. 빠른 메뉴: PASS — 16 quick actions
11. 개인정보 외부전송 차단: PASS — 3 behavioral tests
12. API 입력·오류 노출: PASS — 10 behavioral tests
13. 호출제한·메모리 상한: PASS — 3 behavioral tests
14. AI 구조화·허용 ID: PASS — 3 behavioral tests
15. 외부 API 장애 대응: PASS — 8 behavioral tests
16. 화성시 지역 필터: PASS — 4 behavioral tests
17. 관할·길찾기: PASS — 8 behavioral tests
18. HTTP·CSP·파일노출 방어: PASS — 6 behavioral tests
19. 접근성: PASS — labels, native controls, focus + browser keyboard/modal checks
20. 모바일 390: PASS — 390x844, 13 scenarios, page errors 0
21. 모바일 412: PASS — 412x915, 13 scenarios, page errors 0
22. 태블릿 768: PASS — 768x1024, 13 scenarios, page errors 0
23. 데스크톱 1440: PASS — 1440x900, 13 scenarios, page errors 0
24. 배포 구성: PASS — 4 entrypoints; private helper modules; JSON included
25. 문서: PASS — run / test / limitations / data maintenance documented
26. 의존성: PASS — Python local 3.12.10, deployment 3.13; pinned SDK + Playwright
27. Secret 검사: PASS — no real credential patterns or private env files

## 발견한 실패와 수정

- 기존 개인정보 탐지에 카드·계좌번호와 일부 유니코드 변형이 빠져 있어 양단 차단을 보완했다.
- 기존 센터 데이터에 좌표가 없고 남양읍·동탄9동 주소가 최신 공식 안내와 달랐다. 공식 안내에 포함된 지도에서 29개 센터 좌표를 확보하고 두 주소를 수정했다.
- “주소를 바꾸고 싶어요”, “여권이 만료됐어요”, “청년인데 창업하려고 해요” 검색이 실패했다. 문맥 조합을 클라이언트·서버에 함께 적용하고 정답셋에 추가했다.
- 첫만남이용권은 기존 정답셋에서 미지원 항목이었다. 기능 추가 후 동일 문장의 예상 결과를 검색·순위 검증으로 갱신했다.
- 기존 Linux 고정 E2E 경로와 CSP에서 금지된 문자열 eval 테스트 대기식을 발견했다. 크로스플랫폼 브라우저 실행과 함수형 대기로 수정했다. CSP의 unsafe-eval 허용은 추가하지 않았다.
- 지도 실패 후 방문지 버튼의 구조가 사라지는 문제를 화면 검토에서 발견해 복원 처리했다.
- 기존 20회 리뷰는 같은 검사의 반복이었다. 이번 결과는 27개 서로 다른 품질영역에 대한 증거를 기록한다.
- 테스트 도구 설치는 최초 제한된 네트워크에서 실패했고, 승인된 설치로 완료했다. 이후 검증은 모두 재실행했다.

## 실제 확인 범위와 제한

- 36개 서비스로 요구 최소 30개를 충족한다. 50개 확장은 완료 항목이 아니다.
- 기존 32개 상세정보는 제공된 자료를 바탕으로 유지했다. 신규 출산서비스, 출산지원금, 4개 구 구성과 센터 위치는 공식 본문을 대조했다. HTTP 성공을 전체 행정내용 검증으로 계산하지 않았다.
- 부동산거래관리시스템·인터넷등기소·무공해차 통합누리집은 자동 점검에서 본문을 읽지 못했다. 해당 3개 서비스는 재확인 필요 표시와 제한 사유를 제공한다. 출처별 상태는 SOURCE_AUDIT.json 참고.
- 운영 API 키로 OpenAI·공공데이터·네이버의 실서비스를 호출하지 않았으며 Vercel 배포도 수행하지 않았다. 성공 계약은 모의 응답 및 실제 SDK 메모리 전송으로 검증했다.
- Windows Python 3.12.10 / Node.js 24.20.0 / Playwright 1.55.0 Chromium으로 검증했다. Vercel 대상 Python 3.13의 클라우드 빌드 및 macOS/Linux 실행기는 해당 OS에서 실기동 검증하지 않았다.
- API rate limit은 프로세스 단위이며 여러 서버리스 인스턴스를 합친 전역 한도가 아니다.
- 개인정보 탐지는 형태 기반이며 모든 개인정보를 완벽하게 식별한다고 보장하지 않는다.

## 패키징·무결성

- 검증 소스 SHA-256: `fbeda4e90fae9434c313de1b3093ad65adbd1261e1150e2d996efd6548bc2b20`
- `tests/package_release.py`는 품질게이트 성공 후 ZIP을 만들고 CRC 검사·안전한 새 폴더 재해제·전체 품질게이트 재실행·소스 해시 대조를 수행한다.
- 재해제까지 통과한 경우에만 최종 `hwaseong-life-navi-production.zip`으로 확정한다.
- ZIP에 Git metadata, Python cache/pyc, 설치 도구, 실제 환경파일을 넣지 않는다.
- ZIP 자체 SHA-256과 재해제 판정은 ZIP 옆 `PACKAGE_RESULTS.json`과 `.zip.sha256`에 기록한다. ZIP 내부 파일에 자기 자신의 ZIP 해시를 삽입하지 않는다.
- 패키징 후 생성되는 외부 `QUALITY_REPORT.md`에는 최종 ZIP SHA-256과 재해제 결과를 추가한다.
