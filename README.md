# DATA TADA 상권 분석 서비스

서울시 카페 예비 창업자가 후보 상권을 최대 3개 선택하고 종합해설, 매출, 수요성과 임대료를 비교하는 웹 서비스다. 비교에서 상권 하나의 매출 추세와 주변 입지로 이어진다.

12주차 주간보고서 3번의 화면 구성을 반영했다. 비교 화면은 종합해설, 매출, 수요성, 임대료의 4개 탭이며 상세 화면은 매출, 수요성, 입지/주변환경의 3개 탭이다. 종합해설에서는 총매출액, 점포 수, 총 거래 건수를 전년 동분기와 비교하고, 매출 상세에서는 총매출액과 점포당 평균 매출의 과거 추세 및 향후 2분기 예측을 함께 표시한다. 임대료는 예시 매물의 면적당 월세를 선택한 면적으로 환산하며, 점포당 분기 평균 매출을 3으로 나눈 월 환산값과의 비율을 제공한다. 이 비율은 실제 시세나 개별 점포의 수익성을 뜻하지 않는다.

상단의 상세 상권 분석 메뉴에서 비교 후보 선택 없이 전체 상권을 검색하고 분석할 수 있다. 매출 비교 카드에서는 현재 값과 전년 대비 변화율, 계산 근거를 제공하며 분기별 추이는 상세 매출에서 확인한다. 종합해설의 상권 카드 하단에는 상권별 AI 해설을 넣을 공간을 별도로 마련했다.

Supabase 모드는 서울시 상권 통계, Ridge 기준 모델 예측과 수집한 임대 광고, 카페, 메뉴를 읽는다. 로컬 데모 모드는 지도 위치를 제외한 분석과 입지에 가상 자료를 쓴다.

배포 주소: [DATA TADA 서비스](https://data-tada-265941513825.asia-northeast3.run.app). 서울 리전 Cloud Run에서 실행하며 LLM 해설은 비활성이다.

## 구조

- React + TypeScript + Vite, Leaflet, Recharts.
- FastAPI + Uvicorn, SQLAlchemy.
- Supabase PostgreSQL에서 상권 데이터 조회, 로컬 SQLite에 해설 캐시 저장.
- React 정적 파일을 같은 FastAPI에서 제공하는 Docker 이미지 1개.
- 서울 리전 Cloud Run에 단일 컨테이너로 배포. 쿠버네티스와 별도 작업 큐 없음.
- 페이지별 LLM 해설의 근거 구성, 모델별 캐시와 생성 잠금. 실제 호출은 기본 비활성.

![서비스 아키텍처](docs/diagrams/service-architecture.png)

## 문서

- [팀 협업 규칙과 개인 작업 로그](CONTRIBUTING.md)
- [서버 구조, 데이터 흐름과 주요 코드](docs/server.md)
- [Supabase와 로컬 DB 스키마](docs/database.md)
- [Supabase 연결 및 Data API 호출 방법](docs/supabase-api.md)
- [API 명세서](docs/api/API_SPEC.md)
- [자동 생성 OpenAPI](docs/api/openapi.json)
- [Cloud Run 배포 설정과 재배포 방법](docs/cloud-run.md)
- [서버 측정과 LLM 모델 비교 계획](docs/observability-and-tests.md)
- [10.31 화면 설계를 반영한 초기 아키텍처 기록](docs/architecture.md)
- [초기 검증 결과](docs/verification.md)
- [지도 이식 출처](docs/map-reuse.md)

## 로컬 실행

Windows 정규 CPython 3.13과 Node.js 24를 사용한다. `.env.example`을 `.env`로 복사하면 로컬 기본값으로 실행할 수 있다. 기본값은 SQLite, 가상 자료와 LLM 비활성이다. `.env`는 Git에서 제외된다.

의존성 설치는 다음 형태다. Python 의존성이 이미 있으면 재설치할 필요 없다.

```powershell
$p = Start-Process -FilePath 'C:\Program Files\Python313\python.exe' -ArgumentList '-m','pip','install','-r','requirements-dev.txt' -WorkingDirectory (Get-Location).Path -Wait -PassThru -NoNewWindow
exit $p.ExitCode
```

프론트엔드를 먼저 빌드한다.

```powershell
Set-Location -LiteralPath 'frontend'
npm ci
npm run build
Set-Location -LiteralPath '..'
```

프로젝트 루트에서 서버를 실행한다.

```powershell
$p = Start-Process -FilePath 'C:\Program Files\Python313\python.exe' -ArgumentList '-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Get-Location).Path -Wait -PassThru -NoNewWindow
exit $p.ExitCode
```

- 서비스: `http://127.0.0.1:8000`
- API 명세 UI: `http://127.0.0.1:8000/docs`
- 생존/준비: `/health/live`, `/health/ready`
- 지표: `/metrics`

첫 화면에서 발표용 후보를 선택하거나 모두 비교할 수 있다. Supabase 모드의 후보는 성수역, 광화문역, 홍익대이며 후보별 매출, 거래 건수, 임대 매물, 카페와 메뉴 확보 현황을 표시한다. 홍익대의 매출과 거래는 자료 없음으로 표시한다. 다른 후보는 상단 상권 탐색에서 지도와 검색으로 선택한다. Supabase 모드에서는 선택한 상권의 통계, 기준 예측, 수집된 매물을 확인할 수 있다. 입지 상세에서 매물 원문을 열고, 상권 안이나 기준 매물 반경 안의 카페와 확보된 메뉴를 조회할 수 있다.

Supabase 모드의 환경 변수와 조회 요청 예시는 [Supabase 연결 및 Data API 호출 방법](docs/supabase-api.md)을 참고한다.

프론트 개발 중에는 `frontend`에서 `npm run dev`를 실행한다. Vite는 API를 8000번 FastAPI에 프록시한다.

## LLM 연결

`.env`의 `LLM_ENABLED`, `OPENAI_API_KEY`, `OPENAI_MODEL`을 설정한다. 모델명은 지원 여부를 확인해 사용자가 지정한다. API 키를 `VITE_` 변수나 프론트 소스에 넣지 않는다.

현재 페이지부터 해설을 생성하며 캐시 적중이면 재사용한다. 카드 화살표 이동은 재생성하지 않는다. 실제 LLM 품질 시험과 Langfuse 연결은 후속이다. 서버의 형식/근거 ID 검사가 문장의 모든 의미와 수치까지 보장하지 않는다.

## 테스트

```powershell
$p = Start-Process -FilePath 'C:\Program Files\Python313\python.exe' -ArgumentList '-m','pytest','backend/tests','-q' -WorkingDirectory (Get-Location).Path -Wait -PassThru -NoNewWindow
exit $p.ExitCode
```

```powershell
Set-Location -LiteralPath 'frontend'
npm test
npm run build
Set-Location -LiteralPath '..'
```

서버 실행 후 읽기 API 부하 시험을 실행한다. 유료 LLM은 호출하지 않는다.

```powershell
$p = Start-Process -FilePath 'C:\Program Files\Python313\python.exe' -ArgumentList 'scripts/load_test.py','--requests','200','--concurrency','10','--output','tmp/load-test.json' -WorkingDirectory (Get-Location).Path -Wait -PassThru -NoNewWindow
exit $p.ExitCode
```

## Docker / MySQL 설계

Docker가 설치된 환경에서는 `.env`에 `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`를 직접 설정한 뒤 `docker compose up --build`를 사용할 수 있다. Compose URL 구성에서 사용할 로컬 비밀번호는 URL 안전 문자로 설정하거나 URL 인코딩해야 한다. `init` 서비스가 테이블과 가상 자료를 넣은 다음 서버가 시작한다.

현재 Cloud Run은 `APP_ENV=production`, `DATA_MODE=supabase`, `SEED_ON_START=false`, `LLM_ENABLED=false`로 배포했다. 읽기 전용 DB 접속 정보는 Secret Manager에서 주입한다. 해설 캐시는 비활성이라 영속 쓰기 DB가 필요하지 않다. LLM 활성화 또는 운영 데모 모드에는 영속 DB가 필요하다. 초기 데이터 import는 별도 관리 작업으로 실행하며, 실제 스키마 변경에는 migration 도입이 필요하다.

Cloud Build의 Docker 이미지 빌드와 Cloud Run의 실제 웹/API 응답을 확인했다. MySQL Compose 실행은 검증하지 않았다.

## Git 관리 범위

서버와 프론트 소스 및 lockfile, 기술 문서, `docs/work-logs/`의 개인 작업 로그, 스크립트, 배포 설정, 공개 DB 루트 인증서, 상권 위치 목록과 가상 자료를 Git에서 관리한다. 기존 `jsw/` 연구 폴더, 발표 자료, `.env`, DB 파일, 실행 로그, `node_modules`, 빌드 결과와 로컬 프로젝트 메모는 제외된다.
