# Google Cloud Run 배포

- 프로젝트: `data-tada-capstone-20261109`.
- 리전: 서울 `asia-northeast3`.
- 서비스: `data-tada`.
- 공개 주소: [DATA TADA 서비스](https://data-tada-265941513825.asia-northeast3.run.app).
- 운영 상태 확인일: 2026-11-25. 리비전 `data-tada-no-ttl-1125`, 트래픽 100%.
- 이미지 저장소: `asia-northeast3-docker.pkg.dev/data-tada-capstone-20261109/data-tada/service`.
- 서버 실행 계정: `data-tada-runtime@data-tada-capstone-20261109.iam.gserviceaccount.com`.
- 데이터: Supabase의 읽기 전용 상권 통계, 기준 예측, 수집 임대 광고, 카페와 메뉴.
- LLM: 활성. 방문자 토큰 없이 공개 해설을 제공한다.
- 후보는 지도에서 선택한다. 임대 비교와 입지 상세에서 실데이터를 조회하며, 매물 원문 링크와 반경 내 카페를 제공한다.

후보는 최대 5개까지 비교한다. 비교와 상세 AI 해설에는 요청 후 경과 시간을 표시한다. 브라우저에서 해설을 자동으로 요청한다. 서버는 저장본을 불러오고, 저장본이 없는 경우 OpenAI로 해설을 생성한다.

입지 데이터를 읽는 서버를 배포하기 전에 [읽기 권한 SQL](../scripts/sql/location_service_access.sql)을 적용한다. 기존 운영 서버 계정에 필요한 조회 권한만 추가한다. [서버 코드 구조](server.md) / [DB 스키마](database.md)

## 빌드

프로젝트 루트에서 실행한다. `.gcloudignore`는 빌드에 필요한 파일만 허용하며 `.env`, 로컬 DB, 연구 자료와 프로젝트 메모를 제외한다. `.dockerignore`도 컨테이너 빌드 범위를 제한한다.

```powershell
gcloud builds submit . --tag=asia-northeast3-docker.pkg.dev/data-tada-capstone-20261109/data-tada/service:20261109 --ignore-file=.gcloudignore --project=data-tada-capstone-20261109
```

후속 배포에서는 이미지 태그를 새 값으로 바꾼다.

## 서버 설정

| 변수 | 값 또는 저장 위치 |
| --- | --- |
| `APP_ENV` | `production` |
| `DATA_MODE` | `supabase` |
| `SEED_ON_START` | `false` |
| `LLM_ENABLED` | `true` |
| `LLM_PUBLIC_ACCESS` | `true` |
| `OPENAI_MODEL` | `gpt-6.1-terra` |
| `LLM_TIMEOUT_SECONDS` | `75` |
| `OPENAI_API_KEY` | Secret Manager의 `data-tada-openai-api-key` 버전 1 |
| `SERVICE_ACCESS_TOKEN` | `/metrics` 전용. Secret Manager의 `data-tada-service-access-token` 버전 1 |
| `DATABASE_URL` | `sqlite:////app/tmp/service.db`. 운영 Supabase 모드의 해설은 아래 영속 테이블에 저장한다. |
| `SUPABASE_DATABASE_URL` | Secret Manager의 `data-tada-supabase-url` 버전 1 |
| `SUPABASE_SSLROOTCERT` | `/app/data/certificates/supabase-ca.crt` |

Supabase 접속 정보는 서버 계정만 읽도록 Secret Manager에 보관한다. 공개 루트 인증서는 이미지에 포함하며 DB 접속에 호스트 이름과 인증서 검증을 사용한다. [Cloud Run 비밀 설정](https://docs.cloud.google.com/run/docs/configuring/services/secrets)

서버는 시작할 때 데이터 적재나 테이블 생성을 하지 않는다. Cloud Run 인스턴스의 로컬 파일은 임시 저장소다. [Cloud Run 파일 시스템](https://docs.cloud.google.com/run/docs/container-contract#file_system)


### AI 해설 활성화

상세 해설과 검수본은 기존 Supabase의 `analysis_cache.explanations`에 저장한다. 운영의 Supabase 모드에서 `DATABASE_URL`이 기본 SQLite 값이면 비교 해설도 이 테이블을 사용한다. 두 해설은 기존 `SUPABASE_DATABASE_URL`과 연결 풀을 함께 사용한다. 기존 서버 계정 `data_tada_app`에는 이 스키마의 `USAGE`와 테이블의 `SELECT`, `INSERT`, `UPDATE` 권한이 필요하다. [해설 테이블 정의](../scripts/sql/explanation_cache_schema.sql) / [검수본 적재 도구](../scripts/import_detail_commentary.py)

공개 해설 리비전에는 `LLM_ENABLED=true`, `LLM_PUBLIC_ACCESS=true`, `OPENAI_MODEL=gpt-6.1-terra`를 지정한다. Secret Manager의 OpenAI 키를 `OPENAI_API_KEY`에 연결한다. 방문자는 별도 입력 없이 해설을 보고, 모델 요청은 서버의 OpenAI 키를 사용한다. `SERVICE_ACCESS_TOKEN`은 `/metrics` 인증에 사용한다. Cloud Run 실행 계정에는 연결한 비밀 버전의 읽기 권한이 필요하다. [Cloud Run 비밀 설정](https://docs.cloud.google.com/run/docs/configuring/services/secrets)

## 배포

```powershell
gcloud run deploy data-tada --image=asia-northeast3-docker.pkg.dev/data-tada-capstone-20261109/data-tada/service:20261125-bd562c0 --project=data-tada-capstone-20261109 --region=asia-northeast3 --no-traffic --tag=review
```

화면과 API는 같은 HTTPS 주소에서 제공한다. 최소 인스턴스는 0개로 설정해 요청이 없을 때 상시 실행을 피하고, 최대 인스턴스는 2개로 제한한다. 사용량에 따라 Cloud Run, Cloud Build, Artifact Registry와 Secret Manager 비용이 발생할 수 있다.

기존 서비스에 후속 배포할 때는 이미지 태그를 새 빌드로 바꾼다. 이 명령은 연결된 환경 변수와 비밀을 유지한다. 검증 주소의 `/health/ready`는 해설 테이블 조회도 확인한다. `/api/v1/config`의 해설 활성화와 방문자 인증 여부를 점검하고, 토큰 없이 비교 및 상세 해설을 조회할 수 있는지 확인한다. `/metrics`는 인증 없이 접근하면 401이어야 한다. 검증이 끝나면 공개 트래픽을 전환한다.

## 배포 확인

- 서비스 주소: `gcloud run services describe data-tada --project=data-tada-capstone-20261109 --region=asia-northeast3 --format='value(status.url)'`.
- `/health/live`: 프로세스 응답 확인.
- `/health/ready`: Supabase 연결 확인.
- `/api/v1/areas`: 지도 상권 목록 조회.
- `/api/v1/comparisons`: 배포 대상 빌드의 `/api/v1/config`에 표시된 한도로 비교한다. 현재 저장소에서는 후보 5개를 받고 6개는 422를 반환한다.
- `/api/v1/areas/3120052/analysis`: 단일 상권 상세.
- `/`: 화면과 `/assets/` 정적 파일 응답 확인.

2026-11-09 배포 직후 위 경로의 실제 응답을 확인했다. 지도 상권 1,596개, 후보 5개 비교, 성수역 상세의 관측 22분기와 기준 예측, 가상 매물 3건, LLM `disabled`를 확인했다. 화면 HTML과 JS/CSS 파일은 HTTP 200을 반환했다. 이 확인은 브라우저의 모든 화면 조작이나 장기 부하 검증을 뜻하지 않는다.

2026-11-10에는 해설 버전을 검증용 주소에서 먼저 확인한 뒤 공개 주소로 전환했다. 브라우저에서 비교와 상세의 해설 8개, 임대 층 필터, 거래와 유동인구 전환, 주변 카페 반경 변경을 확인했다. 공개 주소에서 화면과 Supabase 준비 상태를 다시 확인했으며 `LLM_ENABLED=false`를 유지했다.

같은 날 화면 탭 이름을 `매출`로 바꾸고 공개 주소의 비교와 상세 화면에서 확인했다. 링크와 API에서 사용하는 내부 항목 키 `profitability`는 유지했다.

발표 모드 변경 후 검증 주소에서 시작 버튼, 고정 후보, 비교 4개와 상세 20개의 해석, 임대 층 필터, 입지 사례 조건 복귀를 확인했다. 공개 주소에서는 시작 팝업과 매출 해설을 다시 확인했고 GPT는 비활성 상태를 유지했다.

2026-11-20에는 최종 이미지를 공개 트래픽 없이 검증한 뒤 공개 주소를 `data-tada-live-locations-1120b`로 전환했다. 성수역 상세와 임대 비교, 매물 원문 링크, 카페 메뉴와 가격, 매물이 없는 상권의 카페 목록을 브라우저에서 확인했다. 공개 API에서 성수역 매물 26건, 상권 내 카페 56곳, 기준 매물 반경 100m/300m/500m의 카페 7곳/52곳/115곳을 수집 파일과 대조했다. 직전 공개 리비전은 `data-tada-map-selection-1120`이다.

2026-11-23에는 `jsw`의 `bd9abdf`를 Cloud Build `d2f21c34-199e-4dc8-903e-3a35d79abfb4`로 빌드했다. 검증 주소에서 비교 4개와 상세 3개 화면, Supabase 응답과 정적 파일을 확인한 뒤 `data-tada-pr6fix-1123`으로 공개 트래픽 100%를 전환했다. 공개 주소에서도 지도 상권 1,596개, 후보 3개 비교와 4개 요청의 HTTP 422, 성수역 매물 26건과 300m 반경 내 카페 52곳, 두 분기 예측, LLM `disabled`를 확인했다. 직전 공개 리비전은 `data-tada-live-locations-1120b`다.

2026-11-24에는 `jsw`의 `0a028d8`을 Cloud Build `fcfe3418-38dc-4495-9ed6-4856b4f2433a`로 빌드했다. 검증 리비전에서 Supabase 준비 상태, 후보 5개 비교, 해설 경과 시간 화면의 빌드, 무인증 HTTP 401, 저장된 상세 해설 4개를 확인했다. 새 종합해설의 첫 응답은 서버 검증에서 실패했고, 재시도는 후보 5곳 문구를 생성한 뒤 Supabase에 저장했다. `data-tada-ai-timer-1124`로 공개 트래픽 100%를 전환하고 공개 주소에서 지도 1,596개, 후보 5곳 비교, 성수역 매물 26건과 300m 카페 52곳, 종합해설 저장본 적중을 확인했다. 직전 공개 리비전은 `data-tada-pr6fix-1123`이다.

같은 날 방문자 인증을 제거한 `jsw`의 `41d1cba`를 Cloud Build `724520e9-71cc-4d25-b465-6348df8d296d`로 빌드했다. `data-tada-public-ai-1124`에서 공개 해설을 활성화하고 공개 트래픽 100%를 전환했다. 검증 주소에서는 토큰 없이 성수역 수요 해설을 9.5초에 새로 생성하고 두 번째 요청에서 저장본을 불러왔다. 공개 주소의 Chrome에서 입력칸 없이 비교와 상세 해설 본문을 확인했다. 공개 API에서는 저장된 종합해설과 상세 해설 4종을 반환했고, 인증 없는 `/metrics` 요청은 401이었다. 직전 공개 리비전은 `data-tada-ai-timer-1124`다.

2026-11-25에는 `jsw`의 `bd562c0`를 Cloud Build `58bbc936-dda1-48ec-9c53-e96f76f76857`로 빌드해 `data-tada-no-ttl-1125`에 배포했다. 비교 해설의 24시간 유효기간을 제거했다. 검증 주소와 공개 주소의 준비 상태, 기존 비교 및 상세 해설 반환을 확인했다. 공개 트래픽은 새 리비전으로 100% 전환했고 직전 리비전은 `data-tada-public-ai-1124`다.
