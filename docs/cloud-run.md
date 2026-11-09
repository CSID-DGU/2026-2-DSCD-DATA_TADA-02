# Google Cloud Run 배포

- 프로젝트: `data-tada-capstone-20261109`.
- 리전: 서울 `asia-northeast3`.
- 서비스: `data-tada`.
- 공개 주소: [DATA TADA 서비스](https://data-tada-265941513825.asia-northeast3.run.app).
- 배포 확인일: 2026-11-09. 리비전 `data-tada-00001-qpq`, 트래픽 100%.
- 이미지 저장소: `asia-northeast3-docker.pkg.dev/data-tada-capstone-20261109/data-tada/service`.
- 서버 실행 계정: `data-tada-runtime@data-tada-capstone-20261109.iam.gserviceaccount.com`.
- 데이터: 기존 Supabase의 읽기 전용 상권 통계와 기준 예측. 매물과 카페 메뉴는 발표용 가상 자료다.
- LLM: 비활성. 유료 모델 호출을 수행하지 않는다.

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
| `LLM_ENABLED` | `false` |
| `DATABASE_URL` | `sqlite:////app/tmp/service.db`, 현재 비활성 해설 캐시용 경로 |
| `SUPABASE_DATABASE_URL` | Secret Manager의 `data-tada-supabase-url` 버전 1 |
| `SUPABASE_SSLROOTCERT` | `/app/data/certificates/supabase-ca.crt` |

Supabase 접속 정보는 서버 계정만 읽도록 Secret Manager에 보관한다. 공개 루트 인증서는 이미지에 포함하며 DB 접속에 호스트 이름과 인증서 검증을 사용한다. [Cloud Run 비밀 설정](https://docs.cloud.google.com/run/docs/configuring/services/secrets)

현재 서버는 실제 데이터를 Supabase에서 읽는다. LLM이 꺼져 있어 로컬 해설 캐시는 읽거나 쓰지 않으며, 시작할 때 데이터 적재나 테이블 생성을 하지 않는다. LLM을 켜거나 데모 모드를 운영하려면 영속 DB가 필요하며 설정 검증이 이를 강제한다. Cloud Run 인스턴스의 로컬 파일은 영속 저장소로 사용하지 않는다. [Cloud Run 파일 시스템](https://docs.cloud.google.com/run/docs/container-contract#file_system)

## 배포

```powershell
gcloud run deploy data-tada --image=asia-northeast3-docker.pkg.dev/data-tada-capstone-20261109/data-tada/service:20261109 --project=data-tada-capstone-20261109 --region=asia-northeast3 --service-account=data-tada-runtime@data-tada-capstone-20261109.iam.gserviceaccount.com --allow-unauthenticated --port=8080 --cpu=1 --memory=512Mi --min-instances=0 --max-instances=2 --concurrency=20 --timeout=120 --set-env-vars=APP_ENV=production,DATA_MODE=supabase,SEED_ON_START=false,LLM_ENABLED=false,DATABASE_URL=sqlite:////app/tmp/service.db,SUPABASE_SSLROOTCERT=/app/data/certificates/supabase-ca.crt --set-secrets=SUPABASE_DATABASE_URL=data-tada-supabase-url:1
```

화면과 API는 같은 HTTPS 주소에서 제공한다. 최소 인스턴스는 0개로 설정해 요청이 없을 때 상시 실행을 피하고, 최대 인스턴스는 2개로 제한한다. 사용량에 따라 Cloud Run, Cloud Build, Artifact Registry와 Secret Manager 비용이 발생할 수 있다.

## 배포 확인

- 서비스 주소: `gcloud run services describe data-tada --project=data-tada-capstone-20261109 --region=asia-northeast3 --format='value(status.url)'`.
- `/health/live`: 프로세스 응답 확인.
- `/health/ready`: Supabase 연결 확인.
- `/api/v1/areas`: 지도 상권 목록 조회.
- `/api/v1/comparisons`: 후보 5개 비교.
- `/api/v1/areas/3120052/analysis`: 단일 상권 상세.
- `/`: 화면과 `/assets/` 정적 파일 응답 확인.

2026-11-09 배포 직후 위 경로의 실제 응답을 확인했다. 지도 상권 1,596개, 후보 5개 비교, 성수역 상세의 관측 22분기와 기준 예측, 가상 매물 3건, LLM `disabled`를 확인했다. 화면 HTML과 JS/CSS 파일은 HTTP 200을 반환했다. 이 확인은 브라우저의 모든 화면 조작이나 장기 부하 검증을 뜻하지 않는다.
