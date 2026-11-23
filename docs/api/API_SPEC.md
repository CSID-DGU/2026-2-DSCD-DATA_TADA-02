# API 명세서 v0.1

- 기준: 2026-11-20 서버 코드와 자동 생성 [OpenAPI JSON](openapi.json).
- 개발 주소: `http://127.0.0.1:8000`.
- 대화형 명세: `/docs`, 읽기용 명세: `/redoc`, 원본 명세: `/openapi.json`.
- 공통 형식: JSON, 요청 `Content-Type: application/json`.
- 공통 응답 헤더: `X-Request-ID`, `Server-Timing: app;dur=...`.
- 금액: 원, 면적: ㎡, 거리: m, 변화율: %.
- 지원 업종: V1 카페 `CS100010`. 현재 연결된 기준 분기는 `2026Q2`.
- 자료 상태: `supabase` 모드는 지도 위치, 서울시 상권 통계, Ridge 기준 모델 예측과 수집된 임대 광고, 카페, 메뉴를 PostgreSQL에서 읽는다. `demo` 모드는 지도 위치를 제외한 분석과 입지에 가상 자료를 쓴다.

## 인풋: 공통 분석 조건

| 필드 | 타입 | 필수/기본값 | 조건 |
| --- | --- | --- | --- |
| area_codes | string[] | POST 분석/해설에서 필수 | 1~3개, 중복 불가, 실제 목록의 코드 |
| industry_code | string | `CS100010` | 현재 다른 업종은 422 |
| quarter | string | `2026Q2` | `YYYYQ1`~`YYYYQ4`, 잘못된 형식은 422 |

분석 자료가 연결되지 않은 유효한 상권/분기는 200과 null/빈 배열/이유로 반환한다. 목록에 없는 상권 코드는 404다. 자료 없는 상권을 0값으로 채우지 않는다.

## 아웃풋: 공통 메타데이터

비교와 상세 응답의 `meta`에는 다음을 담는다.

```json
{
  "data_mode": "demo",
  "data_version": "synthetic-demo-20261106-v1",
  "metric_version": "metrics-v1",
  "industry_code": "CS100010",
  "quarter": "2026Q2",
  "warning": "분석 수치, 예측, 매물과 메뉴는 개발용 가상 자료입니다. 실제 상권 위치 목록과 구분합니다."
}
```

## 엔드포인트 목록

| 메서드 | 경로 | 인풋 | 아웃풋 |
| --- | --- | --- | --- |
| GET | `/health/live` | 없음 | 프로세스 응답 가능 여부 |
| GET | `/health/ready` | 없음 | DB 연결과 상권 테이블 접근 가능 여부 |
| GET | `/metrics` | 필요 시 Bearer | 프로세스별 요청 수와 응답시간 histogram |
| GET | `/api/v1/config` | 없음 | 업종, 연결 분기, 최대 후보 수, LLM 활성화 상태 |
| GET | `/api/v1/areas` | 검색/구/동/페이지 query | 상권 위치 목록 |
| POST | `/api/v1/comparisons` | 공통 분석 조건 | 후보별 현재 지표와 광고 조건 |
| GET | `/api/v1/areas/{area_code}/analysis` | 코드, quarter | 한 상권의 전체 상세 자료 |
| GET | `/api/v1/areas/{area_code}/nearby-stores` | 기준 매물과 반경 | 거리 순 주변 점포 |
| GET | `/api/v1/cafes/{store_id}/brand-menu` | 공단 점포 ID | 해당 브랜드가 공개한 메뉴 및 상품 |
| POST | `/api/v1/explanations` | 화면 맥락, 필요 시 Bearer | 완료/진행/비활성/자료 부족/실패 |

## 1. 서비스 설정

`GET /api/v1/config`

- 아웃풋: `data_mode`, `llm_enabled`, `llm_auth_required`, `max_candidates=3`, `industries`, `quarters`, `demo_area_codes`. 가상 자료가 있는 상권은 5개이며, 한 번에 비교할 수 있는 상권은 3개다.
- 용도: 프론트가 지원하지 않는 업종이나 기준 분기를 임의로 보여주지 않도록 한다.
- 보안: API 키와 접근 토큰 값은 응답하지 않는다.

## 2. 지도와 상권 검색

`GET /api/v1/areas?q=성수&district=성동구&dong=성수2가3동&offset=0&limit=100`

| query | 타입 | 기본값 | 범위 |
| --- | --- | --- | --- |
| q | string | 빈 값 | 최대 80자, 이름/구/동 포함 검색 |
| district | string | 빈 값 | 최대 40자, 자치구 정확 일치 |
| dong | string | 빈 값 | 최대 40자, 행정동 정확 일치 |
| offset | integer | 0 | 0 이상 |
| limit | integer | 2000 | 1~2000 |

- 아웃풋: `items`, 전체 일치 수 `total`, `crs=EPSG:4326`, 지도 표시 의미 `marker_meaning`.
- 상권 필드: `code`, `name`, `category`, `district`, `administrative_dong`, `latitude`, `longitude`, `area_m2`, `radius_m`.
- 좌표 주의: Leaflet에는 `[latitude, longitude]`, 향후 GeoJSON에는 `[longitude, latitude]` 순서로 전달한다.
- `radius_m`은 면적 기반 탐색 표시다. 실제 상권 경계가 아니다.

## 3. 후보 비교

`POST /api/v1/comparisons`

```json
{
  "area_codes": ["3120052", "3120104", "3120100"],
  "industry_code": "CS100010",
  "quarter": "2026Q2"
}
```

- 아웃풋: `meta`, `items[]`.
- 항목: `area`, `metrics`, `rentals[]`, `observations[]`, `missing_reason`. 과거 분기 자료는 종합해설의 전년 비교와 매출 추이에 사용한다.
- 순서: 요청의 `area_codes` 순서를 유지한다. 카드 표시 범위는 프론트에서 처리하며 서버는 선택한 최대 3개 전체를 반환한다. 비교와 해설 모두 4개 이상을 요청하면 422다.
- 화면 재사용: 종합해설/매출/수요성/임대료를 바꿔도 같은 비교 응답을 사용할 수 있다. 기존 section ID `competition`은 종합해설, `profitability`는 매출에 대응한다.

| metrics 필드 | 뜻과 계산 | 단위/결측 |
| --- | --- | --- |
| total_sales_krw | 해당 분기 카페 총매출 | 원 |
| store_count | 같은 분기 카페 점포 수 | 곳 |
| transaction_count | 같은 분기 거래 건수 | 건 |
| average_sales_krw | 총매출 / 점포 수 | 원/곳/분기, 분모 0이면 null |
| transactions_per_store | 거래 건수 / 점포 수 | 건/곳/분기, 분모 0이면 null |
| average_payment_krw | 총매출 / 거래 건수 | 원/건, 분모 0이면 null |
| sales_yoy_pct | (현재 총매출 / 전년 같은 분기 총매출 - 1) × 100 | %, 전년 분모 0/결측이면 null |
| stores_yoy_pct | 점포 수의 전년 동분기 대비 변화율 | % |
| transactions_yoy_pct | 총 거래 건수의 전년 동분기 대비 변화율 | %, 전년 분모 0/결측이면 null |
| average_sales_yoy_pct | 점포당 평균 매출의 전년 동분기 대비 변화율 | % |
| competition_type | 두 원지표 변화 부호의 현재 조합 | 유형명, 자료 부족, 변화 없음/경계 |

매출과 점포 수 증가가 (+,+)면 시장확장형, (+,-)면 매출개선형, (-,-)면 시장축소형, (-,+)면 경쟁압박형이다. 0은 별도 경계로 처리한다. 총매출 증가만으로 점포당 매출 증가를 단정하지 않는다.

## 4. 상권 상세

`GET /api/v1/areas/3120052/analysis?quarter=2026Q2`

| 필드 | 내용 |
| --- | --- |
| meta, area | 공통 메타데이터와 선택 상권 |
| current | 비교 화면과 동일한 현재 지표 |
| observations[] | 과거 분기, 총매출, 점포 수, 거래 건수, 평균 매출, 두 원지표 YoY |
| forecast | `model_version`, `interval_method`, `coverage_validated`, `points[]` |
| forecast.points[] | 미래 분기, `total_sales_krw` 총매출, 평균 매출, 두 원지표 YoY, 평균 매출 80/90% 하한/상한 |
| demand | `transactions`, `floating_population`별 분포 |
| rentals[] | 광고 원조건 |
| stores[] | 상권 안에 있는 카페, 확보한 매장별 메뉴와 가격 |
| boundary | 실제 경계 미연결로 null |
| missing_reason | 자료가 없을 때 이유 |

- 과거/예측 구분: 관측값과 예측값을 하나의 실제 이력 배열로 섞지 않는다.
- `demo` 예측 버전은 `illustration-only-no-trained-model`이며 구간은 가상 폭이다.
- `supabase`는 총매출 예측을 점포 수 예측으로 나눠 점포당 예측을 계산한다. 점포당 평균 매출의 예측 구간은 제공하지 않으므로 `lower80_krw` 등 구간 필드는 null이다.
- 수요 분포: `unit`, `age_basis`, `weekday_basis`, `time_basis`와 `age[]`, `weekday[]`, `time[]`.
- 분포 한 구분: `label`, `value`, `share_pct`. 연령/시간은 분기 합계, 요일은 해당 요일 일수로 나눈 일평균이다. 구성비의 분모는 각 구분의 분기 전체 합계다.

### 임대광고 계약

`id`, `area_code`, `title`, 좌표, `monthly_rent_krw`, `deposit_krw`, `area_m2`, `floor`, `maintenance_fee_krw`, `observed_at`, `source_url`, `source_name`, `is_transfer`, `is_demo`.

- 없는 관리비는 null이다. 0원이라고 표시하지 않는다.
- 매물 상세에는 원래 계약 조건을 표시한다. 비교 화면은 조건에 맞는 매물의 월세 합계를 면적 합계로 나눠 설정 면적으로 환산한다. 예상 월세를 점포당 분기 평균 매출 ÷ 3으로 나눠 월 환산 매출 대비 비율을 계산하며, 보증금/관리비는 포함하지 않는다. 가상 매물의 참고값으로 실제 시세나 특정 면적 점포의 예상 매출을 뜻하지 않는다.
- `observed_at`은 자료 확인 시점이다. 현재 계약 가능한 매물임을 뜻하지 않는다.

## 5. 기준 매물 주변 점포

`GET /api/v1/areas/{area_code}/nearby-stores?listing_id={listing_id}&radius_m=300`

- 인풋: 경로 상권 코드, 필수 `listing_id`, `radius_m`은 100/300/500 중 하나, `quarter` 기본 `2026Q2`.
- 처리: 해당 상권에 속한 기준 매물인지 확인하고 Haversine 직선거리로 필터링한다.
- 아웃풋: `Store[]`, 거리 오름차순. 한 점포는 `id`, `name`, `address`, 좌표, `menu[]`, `observed_at`, `source_url`, `distance_m`, `brand`, `is_demo`.
- 메뉴: `name`, `price_krw`, 해당하면 `source_date`, `source_url`. 메뉴가 없으면 빈 배열이며 가격이 없으면 null이다.
- 오류: 다른 상권 매물/알 수 없는 매물은 404, 허용되지 않은 반경은 422.
- 운영 모드는 기준 매물 주위의 수집 카페를 검색하며 선택한 상권 경계 밖의 점포도 반경에 들어오면 반환한다. 매물이 없는 상권에서는 상세의 `stores`를 사용할 수 있다.
- 브랜드 자료의 `channel`은 `official_menu` 또는 `gift_catalog`다. 기프트 상품 금액은 매장별 메뉴 가격과 구분한다.

## 6. 페이지별 해설 생성과 캐시

`POST /api/v1/explanations`

```json
{
  "scope": "comparison",
  "section": "competition",
  "area_codes": ["3120052", "3120104", "3120100"],
  "quarter": "2026Q2",
  "industry_code": "CS100010"
}
```

| 필드 | 값과 조건 |
| --- | --- |
| scope | comparison / detail |
| section | profitability / competition / demand / rent / location |
| 비교 허용 조합 | comparison + profitability/competition/demand/rent |
| 상세 허용 조합 | detail + profitability/competition/demand/location, 상권 정확히 1개 |
| demand_metric | transactions / floating_population, 기본 transactions |
| location_view | rentals / stores, 기본 rentals |
| listing_id | 주변 점포 해설이면 필수, 다른 페이지에 지정하면 422 |
| radius_m | 100 / 300 / 500, 기본 300 |
| rental_area_m2 | 임대료 비교의 기준 면적, 기본 66.1157㎡, 0 초과 3305.785 이하 |
| rental_floor | 임대료 비교의 층 조건, 기본 빈 문자열(전체 층), 최대 40자 |

필터별 세부 설명은 후속 조정할 수 있다. 현재 생성은 서버에서 구성한 해당 페이지 근거만 사용한다.

| HTTP | status | 의미와 클라이언트 처리 |
| --- | --- | --- |
| 200 | completed | content 표시, cache_hit 확인 |
| 202 | running | 같은 근거를 생성 중, Retry-After 후 동일 POST 재호출 |
| 200 | disabled | 설정 비활성, 메시지 표시, 자동 재시도 없음 |
| 200 | unavailable | 후보 중 자료 없는 상권이 있음, 메시지 표시 |
| 502 | failed | 공급자/시간초과/결과 검증 실패, 기본 지표 유지, 사용자 재시도 가능 |
| 401 | 공통 error | 서비스 접근 토큰이 필요하거나 틀림 |
| 404/422 | 공통 error | 알 수 없는 상권/매물 또는 잘못된 조건 |

아웃풋:

```json
{
  "status": "completed",
  "cache_key": "sha256 hex",
  "cache_hit": false,
  "content": {
    "summary": "개발용 가상 자료의 요약 예시",
    "blocks": [{"title": "해설 주제", "text": "설명 예시", "evidence_ids": ["3120052.sales_yoy_pct"]}],
    "caveats": ["해석 범위 예시"]
  },
  "message": null,
  "retry_after_seconds": null,
  "prompt_version": "page-commentary-v2-report12",
  "model": "사용자가 환경변수로 지정한 모델",
  "evidence": {"data_mode": "demo", "quarter": "2026Q2", "facts": {"3120052.sales_yoy_pct": 12.3}}
}
```

위 숫자와 문장은 명세 설명용 가상 예시이며 실제 LLM 호출 결과가 아니다. 실제 응답의 evidence에는 자료 버전 등 추가 맥락이 포함된다.

- 캐시 분리: 근거 값/자료 버전/지표 버전/프롬프트/모델/페이지/분기/조건이 달라지면 별도 결과다.
- 캐시 수명: 기본 86,400초. 카드 화살표와 화면 크기는 근거 조건에 포함하지 않는다.
- 생성 잠금: DB에 생성 소유자와 만료 시점을 기록한다. 다른 인스턴스의 동일 요청도 중복 생성을 피한다.
- 영속 작업 큐 없음: 202가 자동 백그라운드 작업 등록을 뜻하지 않는다. 최초 HTTP 요청이 생성 완료까지 열려 있다. 최초 요청이 끊기거나 서버가 종료되면 잠금 만료 뒤 후속 POST가 재생성한다.
- 키 보관: OpenAI 키는 서버 환경변수/Secret Manager에 둔다. 브라우저 빌드 변수에 넣지 않는다.
- 접근 제어: SERVICE_ACCESS_TOKEN이 있으면 해설/metrics에 `Authorization: Bearer ...`가 필요하다. 외부 공개용 사용자 인증은 후속이다.

## 7. 서버 측정 엔드포인트

- `/health/live`: 살아 있는 프로세스가 HTTP를 처리하는지 확인한다. DB와 LLM의 정상 상태를 보장하지 않는다.
- `/health/ready`: DB 접속과 상권 테이블 조회가 가능해야 200, 실패하면 503이다. 데이터 최신성과 전체 LLM 공급자 상태까지 검사하지 않는다.
- `/metrics`: `http_requests_total`, `http_request_duration_seconds_bucket`, `_count`, `_sum`을 반환한다.
- 프로세스 지표: `process_start_time_seconds`, `process_uptime_seconds`, `process_cpu_seconds_total`도 반환한다. CPU 값은 프로세스 누적 CPU 초이며 CPU 사용률 %와 다르다.
- 라벨: HTTP 메서드, 템플릿 경로, 상태코드. 개별 상권 코드와 임의 URL을 라벨로 축적하지 않는다.
- 집계 범위: 현재 프로세스의 시작 이후다. 재시작하면 초기화되며 여러 Cloud Run 인스턴스의 합계는 외부 수집기가 맡는다.
- 시간 범위: Server-Timing은 앱이 요청을 받은 뒤 응답 객체를 준비할 때까지다. 네트워크 왕복, 전체 응답 본문 전송과 브라우저 렌더링 시간은 제외된다.

## 공통 오류

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "입력 필드와 검증 실패 이유",
    "request_id": "UUID"
  }
}
```

내부 예외와 공급자 오류 원문, 비밀 값은 응답하지 않는다. `/api/v1/explanations`의 생성 실패 502는 위 공통 error 대신 명시한 해설 status 응답을 사용한다.
