# Supabase 접근과 Data API 사용법

## 이 서비스에서 사용하는 경로

React는 DATA TADA의 FastAPI를 호출한다. FastAPI는 SQLAlchemy와 psycopg로 Supabase PostgreSQL을 직접 조회한다. 따라서 화면이나 FastAPI의 기존 분석 기능을 수정할 때 필요한 Supabase 설정은 PostgreSQL 접속 정보다. 팀원이 자료를 확인할 때도 먼저 같은 FastAPI 조회 경로를 사용하면 서비스가 계산하고 반환하는 값을 볼 수 있다.

### 1. 서버에서 Supabase 읽기 연결 설정

Supabase Dashboard의 **Connect**에서 팀에서 지정한 프로젝트의 연결 형식을 확인한다. 기존 서비스와 같이 세션 풀러를 사용할 때는 **Session pooler**의 호스트와 포트, 팀에서 발급한 읽기 전용 DB 계정을 사용한다. SQLAlchemy의 드라이버 접두사는 `postgresql+psycopg://`다. 비밀번호에 `@`, `:`, `/` 같은 URL 구분자가 있으면 비밀번호 부분만 URL 인코딩한다. [Supabase PostgreSQL 연결 문서](https://supabase.com/docs/guides/database/connecting-to-postgres)

로컬 프로젝트의 `.env`에 다음을 설정한다. 접속 URL 예시는 자리표시자다. 운영에서는 접속 URL을 Secret Manager에서 주입한다.

```dotenv
DATA_MODE=supabase
SEED_ON_START=false
LLM_ENABLED=false
SUPABASE_DATABASE_URL=postgresql+psycopg://READ_ONLY_ROLE.PROJECT_REF:ENCODED_PASSWORD@POOLER_HOST:5432/postgres
SUPABASE_SSLROOTCERT=data/certificates/supabase-ca.crt
```

[`SupabaseData`](../backend/app/supabase_data.py)가 `sslmode=verify-full`과 지정한 루트 인증서를 사용한다. `.env`와 DB 접속 URL은 로컬 또는 서버의 환경 설정에 보관한다. 브라우저 코드, `VITE_` 변수, 작업 로그에는 DB 접속 URL이나 비밀번호를 넣지 않는다.

### 2. FastAPI의 실제 조회 경로 확인

[README](../README.md)의 로컬 실행 방법으로 서버를 시작한 뒤 PowerShell에서 요청한다. 정상 연결 시 `/health/ready`는 `status=ready`, `data_mode=supabase`를 반환한다.

```powershell
$baseUrl = 'http://127.0.0.1:8000'
Invoke-RestMethod "$baseUrl/health/ready"
Invoke-RestMethod "$baseUrl/api/v1/areas?limit=3"
Invoke-RestMethod "$baseUrl/api/v1/areas/3120052/analysis?quarter=2026Q2"
```

`/health/ready`가 503이면 서버 로그에서 DB 연결 여부를 확인하고, 읽기 계정과 풀러 호스트, 루트 인증서 경로를 점검한다. 분석 요청의 컬럼과 결합 키는 [DB 스키마](database.md), 요청 형식과 응답은 [DATA TADA API 명세](api/API_SPEC.md)에 있다.

## Supabase Data REST API를 직접 사용하는 경우

Data REST API는 Supabase가 승인된 테이블을 `https://<project-ref>.supabase.co/rest/v1/<table>` 경로에 제공하는 HTTP 인터페이스다. 팀이 Data API를 선택한 별도의 개발 대상에서 아래 방식을 사용할 수 있다. 현재 상권 데이터의 조회는 위 FastAPI 경로를 사용한다. [Supabase Data REST API 문서](https://supabase.com/docs/guides/api)

1. Supabase Dashboard의 **Integrations > Data API**에서 프로젝트 API URL과 대상 스키마 및 테이블 공개 설정을 확인한다. **Settings > API Keys** 또는 프로젝트의 **Connect**에서 publishable key를 확인한다.
2. 대상 스키마와 테이블이 Data API에 공개되어 있고, 요청 역할에 스키마 `USAGE`, 테이블 `SELECT`, 조회할 행에 대한 RLS 정책이 있는지 확인한다. 이 프로젝트의 `data_tada`, `data_tada_demo`는 기존 서버용 읽기 계정으로 조회한다. 아래 예시는 `api` 스키마의 `example_areas`를 사용하도록 별도 승인받은 개발 환경을 가정한다. [커스텀 스키마 접근](https://supabase.com/docs/guides/api/using-custom-schemas)
3. GET 요청에는 프로젝트의 publishable key를 `apikey` 헤더에 넣고, 기본 스키마가 아닌 경우 `Accept-Profile`로 스키마를 지정한다. 로그인 사용자 권한이 필요한 테이블이면 Supabase Auth가 발급한 사용자 액세스 토큰을 `Authorization: Bearer ...`에 넣는다. 서비스 비밀 키와 `service_role` 키는 권한이 높은 서버 자격 증명으로 관리한다. [Supabase API 키와 사용자 인증](https://supabase.com/docs/guides/getting-started/api-keys)

팀에서 제공한 프로젝트 URL과 publishable key를 각각 `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` 환경 변수에 준비한 뒤 실행한다. 예제에서 `select`는 반환 컬럼, `eq.`는 일치 조건, `limit`은 최대 행 수다. `SUPABASE_USER_ACCESS_TOKEN`은 해당 요청에 로그인 권한이 필요할 때만 설정한다.

```powershell
$headers = @{
    apikey = $env:SUPABASE_PUBLISHABLE_KEY
    'Accept-Profile' = 'api'
}
if ($env:SUPABASE_USER_ACCESS_TOKEN) {
    $headers['Authorization'] = "Bearer $env:SUPABASE_USER_ACCESS_TOKEN"
}
$projectUrl = $env:SUPABASE_URL.TrimEnd('/')
$requestUrl = "$projectUrl/rest/v1/example_areas?select=area_code,name&area_code=eq.3120052&limit=1"
Invoke-RestMethod -Method Get -Uri $requestUrl -Headers $headers
```

요청에 실패하면 오류 본문을 확인한다. 인증 오류는 키 또는 토큰, 스키마나 테이블 오류는 Data API 공개 설정, 권한 오류는 해당 역할의 권한을 점검한다. 성공 응답이 빈 배열이면 조회 조건과 RLS 정책에서 그 사용자에게 표시되는 행이 있는지 확인한다.
