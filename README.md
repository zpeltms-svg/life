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
