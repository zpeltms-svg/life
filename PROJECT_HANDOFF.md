# 화성생활 내비 프로젝트 인수인계

> 2026-08-27 추가: `PUBLIC_DATA_SERVICE_KEY`는 `api/public_services.py`에서 실제 사용합니다. `/api/public-services`가 공공서비스 목록을 검색하고, 브라우저는 로컬 생활 파일과 결과를 합쳐 표시합니다. Vercel Production 환경 변수 저장 후 새 배포가 필요합니다.

이 문서는 지금까지 진행한 대화와 개발 작업을 다음 작업자 또는 다음 AI 대화에 전달하기 위한 요약본이다. 실제 API 키와 Client Secret은 보안을 위해 포함하지 않았다.

## 1. 프로젝트 개요

- 프로젝트명: 화성생활 내비
- 저장소: `https://github.com/zpeltms-svg/life.git`
- 기본 브랜치: `main`
- 배포: Vercel
- 확인한 운영 도메인: `https://life-six-inky.vercel.app`
- 로컬 경로: `C:\Users\pc\Desktop\김종완\실습자료_심화\hwaseong-life-navi`
- Git 사용자명: `zpeltms`
- Git 이메일: `zpeltms@gmail.com`

## 2. 서비스 목적

사용자가 “화성으로 이사 왔어요”, “아이가 태어났어요” 같은 생활 상황을 입력하면 관련 행정서비스를 한 권의 파일처럼 정리해서 보여주는 웹서비스다.

주요 생활주기 예시:

- 전입·이사
- 출산·육아
- 청년생활
- 생활폐기물
- 반려동물

## 3. 디자인 요구사항

- 참고 디자인: `https://www.mosbyfiles.com/`
- 서류철·파일철·생활기록 보관소 같은 아카이브 콘셉트
- 종이 질감에 가까운 배경, 검은 선, 형광 연두색 포인트
- 한글 제목은 부드러운 명조 계열, 본문은 읽기 쉬운 한글 산세리프 사용
- 한글 자간·행간과 줄바꿈을 세심하게 조절
- 메인 소개 문구와 설명이 어색하게 3줄로 갈라지지 않도록 구성
- 소개 본문은 데스크톱 기준 자연스러운 2줄 형태 유지
- 모바일에서도 파일철 카드와 상세 모달이 정상 표시되어야 함

## 4. 구현된 주요 기능

### 생활 상황 검색

- 문장 입력으로 관련 서비스 추천
- OpenAI API가 없거나 실패하면 로컬 키워드 검색으로 자동 대체
- 빠른 시작 문장과 파일철 카드 제공
- 입력 문장은 별도로 저장하지 않는다는 개인정보 안내 제공

### 온라인 신청

- 온라인 신청이 가능한 서비스는 결과 카드와 상세 화면에서 강조 표시
- 정부24 또는 화성시 공식 페이지 링크 제공
- 외부 링크는 새 창에서 열림

### 오프라인 신청 및 길찾기

- 현재 위치에서 제출기관까지 자동차 예상시간과 거리 계산
- 네이버 지도 위에 출발점, 도착점, 경로선 표시
- 네이버 지도 앱 길안내 링크 제공
- 사용자가 다른 주소를 입력해 목적지를 변경할 수 있음
- 화성시 읍·면·동 드롭다운과 부분 문자열 검색 제공
- `향` 입력 시 `향남읍`, `동탄7` 입력 시 `동탄7동`처럼 자동 매칭

### 행정복지센터 처리 규칙

서비스 데이터의 `office_mode`로 처리한다.

- `jurisdiction`: 주소지 관할 행정복지센터에서만 가능한 서비스
  - 현재 주소 직접 입력 가능
  - “현재 위치로 주소 설정” 버튼 제공
  - Reverse Geocoding으로 현재 위치를 주소로 변환
  - 법정동이 아니라 행정동 기준으로 드롭다운 자동 선택
  - 사용자가 화성시 읍·면·동을 직접 변경 가능
- `nationwide_nearest`: 전국 읍·면·동에서 접수할 수 있는 서비스
  - 현재 위치와 화성시 행정복지센터 29곳의 좌표를 비교
  - 가장 가까운 센터를 자동 선택
  - 선택한 센터까지 예상시간·거리·지도 경로 제공

현재 분류:

- `MOVE-001`: `jurisdiction`
- `BIRTH-001`: `nationwide_nearest`
- `BIRTH-002`: `jurisdiction`

## 5. 행정복지센터 데이터

파일: `data/welfare-centers.json`

- 화성시 읍·면·동 행정복지센터 29곳 수록
- 각 센터의 `area`, `name`, `address` 저장
- 화성시 공식 주소 자료 사용
- 동탄9동은 별도 최신 공식 안내 주소 반영

공식 출처:

- `https://www.hscity.go.kr/town/minwon/mnlssCvplInfo.jsp`
- `https://www.hscity.go.kr/dongtan/dtTown/dongtan09/dongtan09Guide.jsp`

첫 번째 가까운 센터 검색에서는 29개 주소를 좌표로 변환하기 때문에 몇 초 걸릴 수 있다. 이후에는 브라우저 `localStorage` 캐시를 사용한다.

## 6. API 구조

### `/api/guide`

- 파일: `api/guide.py`
- 사용자 문장을 분석해 관련 서비스 ID 추천
- OpenAI API가 없거나 실패하면 프런트엔드가 로컬 검색으로 대체

### `/api/route`

- 파일: `api/route.py`
- Naver Maps Geocoding으로 목적지 주소를 좌표로 변환
- Directions 5의 `trafast` 옵션으로 자동차 경로 계산
- 예상시간, 거리, 경로 좌표, 목적지 좌표 반환
- 현재 NCP VPC API 주소 사용:
  - `https://maps.apigw.ntruss.com/map-geocode/v2/geocode`
  - `https://maps.apigw.ntruss.com/map-direction/v1/driving`
- 400, 401, 429 오류를 사용자 친화적인 한글 문구로 변환

### `/api/address`

- 파일: `api/address.py`
- 현재 위치 좌표를 주소로 변환
- Naver Maps Reverse Geocoding 사용
- 주소 표시는 도로명 주소를 사용
- 관할 드롭다운 자동 선택은 `admcode`의 행정동을 사용
- 예: 도로명 주소의 법정동이 `반송동`이어도 관할 선택은 `동탄1동`

### `/api/map-config`

- 파일: `api/map_config.py`
- 브라우저용 Naver Maps Client ID만 반환
- Client Secret은 반환하지 않음
- 지도 SDK에서 Geocoder 하위 모듈 사용

### Vercel Rewrite

`vercel.json`에 다음 경로가 등록되어 있다.

- `/api/guide`
- `/api/route`
- `/api/address`
- `/api/map-config`

## 7. Vercel 환경변수

Production 환경에 다음 변수명을 등록한다.

```text
NCP_MAPS_CLIENT_ID
NCP_MAPS_CLIENT_SECRET
OPENAI_API_KEY        # 선택
OPENAI_MODEL          # 선택
```

Naver Cloud Maps Application에서 필요한 기능:

- Web Dynamic Map
- Geocoding
- Reverse Geocoding
- Directions 5

환경변수를 변경하면 반드시 Vercel에서 새 배포 또는 Redeploy를 해야 한다.

## 8. 보안

- `.env`는 `.gitignore`에 포함됨
- 실제 API 키나 Client Secret은 저장소에 커밋하지 않음
- `.env.example`에는 변수명만 기록
- 브라우저에는 Maps Client ID만 전달하며 Client Secret은 서버에서만 사용
- 대화 중 실제 키가 노출된 적이 있으므로 해당 키는 가능하면 Naver Cloud와 공공데이터포털에서 재발급 또는 재생성하는 것이 안전함
- 다음 작업에서도 실제 키 값을 채팅, 코드, README, JSON에 붙여 넣지 말 것

## 9. 테스트와 검증

테스트 파일: `tests/test_project.py`

자동 회귀 검사 16개를 구현했고 모두 통과했다.

검사 내용:

1. 서비스 데이터 존재
2. 서비스 ID 중복 여부
3. 공식 출처 및 확인일 존재
4. 온라인 신청 링크의 HTTPS 여부
5. 행정복지센터 29곳 등록 여부
6. 센터 이름과 주소 형식
7. 주소지 관할 서비스 분류
8. 전국 접수 서비스 분류
9. 읍면동 부분 검색 구현
10. 가장 가까운 센터 계산 구현
11. 현재 위치 주소 변환 구현
12. Directions `trafast` 옵션 사용
13. 최신 Naver Maps API 주소 사용
14. Vercel API Rewrite 존재
15. 평문 Secret 검사
16. Reverse Geocoding의 행정동 사용

실행 명령:

```bash
node --check app.js
python -m unittest tests.test_project -v
python -m py_compile api/guide.py api/route.py api/address.py api/map_config.py
```

추가 검색 회귀 사례:

- `향` → `향남읍`
- `동탄7` → `동탄7동`
- `봉담` → `봉담읍`
- `반월` → `반월동`

운영 API 확인 결과:

- `/api/map-config`: HTTP 200 확인
- `/api/route`: 실제 시간·거리·경로 좌표 반환 확인
- `/api/address`: 도로명 주소와 행정동 반환 확인

## 10. 주요 커밋

- `0008261`: 초기 UI
- `a821d9d`: 서비스 데이터/API
- `634a8fe`: 문서
- `379cd08`: 온라인 신청과 길찾기 서버
- `4a0c8d8`: Naver 지도 경로 미리보기
- `dc55c82`: 최신 Naver Maps API 주소 적용
- `1fb5296`: 목적지 검색과 경로 선택
- `2dc1c16`: 관할 행정복지센터 안내
- `070e149`: 읍면동 목적지 검색 개선
- `eab2a3e`: 수동 목적지 경로 차단 수정
- `a80c49b`: 행정복지센터 전체 안내 흐름 완성
- `a7e6b19`: 현재 주소를 행정동과 매칭

## 11. 주요 파일

- `index.html`: 전체 화면 구조
- `style.css`: 디자인과 반응형 스타일
- `app.js`: 검색, 상세 화면, 지도, 기관 분기, 위치 기능
- `data/services.json`: 생활서비스 데이터
- `data/welfare-centers.json`: 화성시 행정복지센터 데이터
- `api/guide.py`: 추천 API
- `api/route.py`: 길찾기 API
- `api/address.py`: 현재 위치 주소 변환 API
- `api/map_config.py`: 브라우저 지도 설정 API
- `tests/test_project.py`: 회귀 테스트
- `vercel.json`: Vercel API 경로 설정

## 12. 다음 작업 시 확인 사항

1. Vercel 최신 배포가 `Ready`인지 확인한다.
2. 브라우저 위치 권한을 허용한다.
3. 출생신고 상세 화면에서 가장 가까운 센터 버튼을 확인한다.
4. 전입신고·출산지원금에서 주소지 관할 드롭다운과 현재 위치 자동 설정을 확인한다.
5. 반려동물 진료센터에서 예상시간, 지도 경로, 네이버 지도 앱 링크를 확인한다.
6. Naver Maps 오류가 발생하면 화면의 한글 오류 문구와 Vercel Function Logs를 함께 확인한다.
7. 행정기관 주소나 신청 기준은 변경될 수 있으므로 공식 출처를 정기적으로 재검증한다.

## 13. 다음 대화에 전달할 요청 예시

```text
첨부한 PROJECT_HANDOFF.md를 먼저 읽고 현재 화성생활 내비 프로젝트 상태를 파악해줘.
기존 디자인과 기능을 유지하면서 요청한 변경을 구현하고, tests/test_project.py의 회귀 테스트를 모두 통과시킨 뒤 결과를 알려줘.
실제 API 키와 Secret은 절대로 코드나 Git에 넣지 마.
```
