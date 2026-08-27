# 화성생활 내비

화성시민을 위한 상황형 생활행정 안내 웹앱 체험판(MVP)입니다.

## 바로 실행하기

정적 화면과 기본 추천 기능은 별도 설치 없이 로컬 서버만 열면 동작합니다.

### 방법 1: VS Code Live Server
`index.html`을 Live Server로 실행합니다.

### 방법 2: Python 간단 서버
프로젝트 폴더에서:

```bash
python -m http.server 5500
```

브라우저에서 `http://localhost:5500` 접속.

> 이 방식에서는 `/api/guide`가 없기 때문에 자동으로 로컬 키워드 추천으로 동작합니다.

## OpenAI 상황분석 사용
Vercel 배포 후 프로젝트 Environment Variables에 아래 값을 등록합니다.

- `OPENAI_API_KEY`: 본인의 OpenAI API Key
- `OPENAI_MODEL`: 선택사항 (기본값 `gpt-4.1-mini`)
- `PUBLIC_DATA_SERVICE_KEY`: 공공데이터포털의 `행정안전부_대한민국 공공서비스(혜택) 정보` 일반 인증키

`PUBLIC_DATA_SERVICE_KEY`가 설정되면 입력 키워드를 정부24 공공서비스 목록의 서비스명과 사용자구분에서 서버 측으로 검색합니다. 키는 브라우저로 전달되지 않습니다.

API 키는 브라우저 코드에 넣지 마세요.

## Vercel 배포
1. GitHub 새 저장소 생성
2. 이 폴더를 commit/push
3. Vercel → Add New → Project → GitHub 저장소 Import
4. Framework Preset은 자동 감지 또는 Other
5. `OPENAI_API_KEY` 환경변수 등록(선택)
6. Deploy

## 데이터 수정
`data/services.json`만 수정하면 됩니다.

행정정보는 바뀔 수 있으므로 다음 원칙을 지켜주세요.
- 정부24 또는 화성특례시 공식자료만 사용
- `source_name`, `source_url`, `source_checked` 필수
- 확인되지 않은 금액·기간·서류는 임의로 추가하지 않기

## 현재 포함된 예시 공식자료
- 정부24 전입신고
- 정부24 출생신고
- 화성특례시 출산지원
- 화성특례시 청년 일자리 지원
- 화성특례시 대형폐기물 배출신청
- 화성특례시 반려동물 진료센터·입양센터 안내

## 주의
이 프로젝트는 교육·체험용 MVP입니다. 실제 행정신청 전에는 화면의 '공식 원문 열기'에서 최신 내용을 다시 확인하도록 안내해야 합니다.

## 네이버 지도 기능

Vercel Production 환경변수에 다음 값을 Secret으로 등록합니다.

- `NCP_MAPS_CLIENT_ID`: Naver Cloud Maps Client ID
- `NCP_MAPS_CLIENT_SECRET`: Naver Cloud Maps Client Secret

Naver Cloud Maps Application에서 Web Dynamic Map, Geocoding, Reverse Geocoding, Directions 5를 활성화해야 합니다. Secret은 브라우저 코드나 Git 저장소에 입력하지 않습니다.

행정복지센터 길찾기는 `data/welfare-centers.json`의 화성시 공식 주소 목록을 사용합니다. `office_mode`가 `jurisdiction`이면 주소지 관할 센터를 선택하고, `nationwide_nearest`이면 현재 위치와 센터 좌표를 비교해 가장 가까운 센터를 안내합니다.
