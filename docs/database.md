# DATA TADA DB 스키마

2026-11-20에 Supabase PostgreSQL에서 `data_tada`, `data_tada_demo`의 테이블 11개와 컬럼 90개, 제약, 인덱스, 서비스 계정 권한을 읽기 전용으로 확인했다. 애플리케이션 DB의 테이블 정의는 [`backend/app/db.py`](../backend/app/db.py)를 기준으로 한다.

## 연결과 사용 범위

| 연결 | 저장소 | 사용 범위 |
| --- | --- | --- |
| `SUPABASE_DATABASE_URL` | Supabase PostgreSQL | `DATA_MODE=supabase`에서 상권 목록, 통계, 예측, 수집한 입지 자료를 읽는다. 조회 코드가 있는 FastAPI 서버만 접속한다. |
| `DATABASE_URL` | 로컬 기본 SQLite. MySQL 연결은 [Compose 예제](../compose.yaml)를 참고한다. | 데모 모드의 상권 목록과 분석 자료, LLM 활성화 시 해설 캐시 및 생성 잠금을 관리한다. |

운영 서버는 Supabase를 호스트와 인증서까지 확인하는 `sslmode=verify-full`로 연결한다. 공개 루트 인증서는 [`data/certificates/supabase-ca.crt`](../data/certificates/supabase-ca.crt)에 있다. DB 접속 URL은 Cloud Run에서 Secret Manager를 통해 주입한다. 확인한 Supabase 서비스 계정은 아래 ‘API 조회’에 적힌 6개 테이블을 읽을 수 있고, 두 스키마의 11개 테이블에 대한 데이터 쓰기 권한이 없다. 11개 모두 행 수준 보안(RLS)이 켜져 있다.

환경 변수 설정, FastAPI를 통한 읽기 확인 및 Supabase Data API 호출 예시는 [Supabase 연결 안내](supabase-api.md)에서 확인할 수 있다.

| 테이블 | 한 행의 단위 | 서비스 사용 |
| --- | --- | --- |
| `data_tada.areas` | 상권 1곳 | API 조회 / 지도 목록 |
| `data_tada.industries` | 업종 1개 | 업종 코드 참조 / API는 카페 코드 `CS100010` 고정 |
| `data_tada.quarterly_metrics` | 상권, 업종, 분기 | API 조회 / 매출, 거래, 점포 |
| `data_tada.quarterly_population` | 상권, 분기 | API 조회 / 유동인구 |
| `data_tada.forecast_runs` | 버전, 업종, 기준 분기별 예측 실행 | API 조회 / 읽을 모델 실행 선택 |
| `data_tada.quarterly_forecasts` | 상권별 모델 실행 및 목표 분기 | API 조회 / 저장 예측값 |
| `data_tada.rental_listings` | 임대 광고 1건 | 임대 비교 및 입지 상세 |
| `data_tada.rental_area_memberships` | 상권과 임대 광고의 연결 1건 | 광고의 상권 조회 |
| `data_tada.cafe_stores` | 카페 점포 1곳 | 상권 내 및 반경 내 카페 조회 |
| `data_tada.cafe_menus` | 카페별 메뉴 1건 | 매장별 메뉴와 가격 |
| `data_tada.cafe_area_memberships` | 상권과 카페 점포의 연결 1건 | 상권 안의 카페 조회 |
| `data_tada.service_cafe_store_brands`, `data_tada.service_cafe_brand_menus` | 브랜드 소속 및 본사 메뉴 | 본사 참고 자료 조회용 뷰 |
| `data_tada.location_collection_runs` | 임대 및 카페 수집 스냅샷 1회 | 출처별 건수, 검증값과 적재 시각 |
| `data_tada.location_collection_rows` | 수집 CSV의 원본 행 1건 | 원문과 보조 자료 보존 |
| `data_tada_demo.location_examples` | 상권별 가상 매물 및 주변 카페 묶음 | 기존 발표 자료 보관 |

운영 서버 계정은 위치 테이블 5개와 브랜드 조회용 뷰 2개를 읽는다. 수집 원본과 적재 목록은 관리 DB에서 조회한다. 아래 컬럼 목록에서 ‘필수’는 `NOT NULL`이며, ‘선택’은 DB에서 `NULL`을 허용한다는 뜻이다. PK는 행을 고유하게 식별하는 기본 키, FK는 다른 테이블의 행을 참조하는 외래 키다. [운영 읽기 권한 SQL](../scripts/sql/location_service_access.sql)

## Supabase 통계 및 예측

### `data_tada.areas`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `area_code`, `name`, `category` | `district_code`, `district`, `administrative_dong_code`, `administrative_dong` |
| `double precision` | | `latitude`, `longitude`, `area_m2`, `radius_m` |
| `boolean` | `map_selectable` | |

- PK는 `area_code`다. 중심점 좌표는 EPSG:4326이다. 위도는 -90~90, 경도는 -180~180이며 좌표를 저장할 때 두 값이 모두 있어야 한다. 지도 선택이 가능한 행은 좌표가 필수다.
- `area_m2`는 제곱미터, `radius_m`은 미터이며 음수를 허용하지 않는다. 반경은 지도에 표시하는 값으로 상권의 실제 경계와 별개다.

### `data_tada.industries`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `industry_code`, `name` | |

- PK는 `industry_code`다. API의 카페 업종 코드는 `CS100010`이다.

### `data_tada.quarterly_metrics`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `area_code`, `industry_code` | |
| `date` | `quarter_start` | |
| `bigint` | `store_count`, `independent_store_count`, `franchise_store_count`, `opened_store_count`, `closed_store_count` | `total_sales_krw`, `transaction_count` |
| `jsonb` | | `sales_shares` |

- PK는 `(area_code, industry_code, quarter_start)`다. `area_code`와 `industry_code`는 각 상권 및 업종 마스터를 참조한다.
- 매출은 원, 거래는 건, 점포는 곳 단위다. 수치 컬럼은 음수를 허용하지 않는다. 매출과 거래 건수는 함께 있거나 함께 `NULL`이다. 전체 점포 수는 독립 점포 수와 프랜차이즈 점포 수의 합이다.
- `sales_shares`는 항목별 구성비를 담는다. 서버는 `sale_share_25`~`31`을 월~일, `32`~`37`을 시간대, `40`~`45`를 10대~60대 이상 거래 건수 비율로 읽는다.

### `data_tada.quarterly_population`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `area_code` | |
| `date` | `quarter_start` | |
| `bigint` | | `floating_population_count`, `worker_count`, `resident_count` |
| `jsonb` | | `floating_population_shares` |

- PK는 `(area_code, quarter_start)`다. `area_code`는 `areas`를 참조한다. 인구 수치 컬럼은 음수를 허용하지 않는다.
- 전체 유동인구는 상권 단위 추정 집계다. 서버는 `pop_share_02`~`07`을 연령, `08`~`13`을 시간대, `14`~`20`을 요일 비율로 읽는다.

### `data_tada.forecast_runs`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `model_version`, `industry_code`, `model`, `purpose` | |
| `date` | `origin_quarter_start` | |
| `timestamptz` | `generated_at` | |

- PK는 `(model_version, industry_code, origin_quarter_start)`다. `industry_code`는 `industries`를 참조한다.
- 서버는 카페와 기준 분기에 해당하는 실행 중 `generated_at`이 가장 늦은 실행을 사용한다. 시각이 같으면 `model_version` 내림차순의 첫 실행을 가져온다.

### `data_tada.quarterly_forecasts`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `area_code`, `industry_code`, `model_version` | |
| `date` | `origin_quarter_start`, `target_quarter_start` | |
| `smallint` | `horizon` | |
| `double precision` | `predicted_sales_krw`, `predicted_store_count`, `sales_lower_80_krw`, `sales_upper_80_krw`, `stores_lower_80`, `stores_upper_80` | `sales_lower_90_krw`, `sales_upper_90_krw`, `stores_lower_90`, `stores_upper_90` |

- PK는 `(area_code, industry_code, origin_quarter_start, model_version, target_quarter_start)`다. `area_code`, `industry_code`는 각 마스터를 참조한다. `(model_version, industry_code, origin_quarter_start)`는 `forecast_runs`, `(area_code, industry_code, origin_quarter_start)`는 `quarterly_metrics`의 기준 분기 행을 참조한다.
- `horizon`은 1 또는 2이며 `target_quarter_start`는 `origin_quarter_start + horizon × 3개월`이다. 매출(원), 점포 수(곳) 예측과 각 구간의 상하한은 음수를 허용하지 않는다. 80% 하한과 상한 사이에 해당 지표의 예측값이 있어야 한다. 점포 수는 예측값이라 소수로 저장할 수 있다.
- API의 점포당 매출 예측은 총매출 예측을 같은 목표 분기의 점포 수 예측으로 나눈 값이다. 저장된 총매출 및 점포 수 구간은 점포당 매출 구간으로 사용하지 않는다.

## Supabase 입지 참고 및 예시

### `data_tada.rental_listings`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `listing_id`, `source_url` | `address`, `address_precision`, `floor_raw`, `exclusive_area_raw`, `contract_area_raw`, `map_point_status` |
| `bigint` | | `deposit_krw`, `monthly_rent_krw` |
| `double precision` | | `latitude`, `longitude` |
| `timestamptz` | `checked_at` | |
| `jsonb` | | `collection_payload` |

- PK는 `listing_id`다. `source_url`은 고유하다. 보증금과 월세(원)는 음수를 허용하지 않는다. 좌표를 저장할 때 위도와 경도가 함께 있어야 한다. 층과 전용/계약 면적은 광고의 원문 표기다.

### `data_tada.rental_area_memberships`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `area_code`, `listing_id` | |

- PK는 `(area_code, listing_id)`다. 상권 코드와 광고 ID는 각각 `areas`, `rental_listings`를 참조한다. 광고 하나를 여러 상권에 연결할 수 있다.

### `data_tada.cafe_stores`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `store_id`, `name`, `profile_match_status` | `area_code`, `address`, `permit_status`, `source_url` |
| `double precision` | | `latitude`, `longitude` |
| `date` | | `permit_opened_on` |
| `timestamptz` | `collection_as_of` | |
| `jsonb` | | `collection_payload` |

- PK는 `store_id`다. `area_code`는 `areas`에 등록된 연결 상권 중 코드가 가장 작은 값이다. 등록된 연결 상권이 없으면 `NULL`이다. 등록된 전체 연결은 `cafe_area_memberships`에서 조회한다. 공단 상가업소 원천은 인허가 자료가 아니므로 해당 행의 `permit_status`는 `NULL`이다. 수집한 공단 점포는 기존 매장 프로필과 별도로 매칭하지 않아 `profile_match_status`가 `unmatched`다.

### `data_tada.cafe_menus`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `store_id`, `name`, `price_status` | `menu_group` |
| `integer` | `menu_index` | |
| `bigint` | | `price_krw` |
| `timestamptz` | `checked_at` | |
| `jsonb` | | `collection_payload` |

- PK는 `(store_id, menu_index)`다. `store_id`는 `cafe_stores`를 참조한다. 메뉴 순번과 가격은 음수를 허용하지 않는다. `price_status`가 `observed`이면 가격이 필수이며, `not_disclosed_or_variable`이면 가격은 `NULL`이다.

### `data_tada.cafe_area_memberships`

- PK는 `(area_code, store_id)`다. 상권 코드와 점포 ID는 각각 `areas`, `cafe_stores`를 참조한다. 점포 하나가 여러 상권에 들어가면 각 관계를 저장한다.

### 수집 원본

- `location_collection_runs`의 PK는 `snapshot_id`다. `manifest`에는 수집 요약과 출처별 건수 및 검증값이 있다. `uploaded_at`이 채워진 스냅샷은 적재 검증을 통과했다.
- `location_collection_rows`의 PK는 `(snapshot_id, dataset, row_number)`다. `payload`는 해당 CSV 행을 담은 JSON 객체다. 상권 집계, 임대 정보 완비 목록, LH 공고, 브랜드 메뉴 및 기프트 상품, 점포별 브랜드, 미연결 메뉴 후보를 찾을 수 있다. `areas`에 미등록된 공간 연결도 원본 `rental_memberships`와 `cafe_memberships`에 보존한다.
- 매물, 카페 점포 및 매장별 메뉴의 `collection_payload`에도 각 CSV 행을 보관한다. 메뉴별 출처와 기준일을 확인할 수 있다. [적재 코드](../scripts/upload_location_collection.py)에서 CSV와 `dataset`의 대응을 확인할 수 있다.
- 적재 코드에 `--rental`과 `--cafe`로 수집 결과 폴더를, `--notices`로 LH 공고 CSV를 넘긴다. 기본 실행은 입력 건수와 식별자 검증만 수행한다. `--apply`로 DB에 저장하며 로컬 환경의 `SUPABASE_ACCESS_TOKEN`을 사용한다. 적재를 마친 동일 수집 스냅샷은 재실행 시 DB의 검증값과 행 수를 확인한다.

### `data_tada_demo.location_examples`

| 자료형 | 필수 | 선택 |
| --- | --- | --- |
| `text` | `area_code` | |
| `jsonb` | `rentals`, `stores` | |
| `boolean` | `is_demo` | |

- PK는 `area_code`이며 `data_tada.areas`를 참조한다. `rentals`, `stores`는 JSON 배열이어야 한다. `is_demo`는 기본값 `true`이며 검사 제약도 `true`만 허용한다.
- 매물 JSON에는 매물 ID, 상권 코드, 좌표, 월세, 보증금, 면적, 층과 확인 시각을 담는다. 카페 JSON에는 점포 ID, 이름, 좌표 및 메뉴 이름과 가격을 담는다. 정확한 응답 필드와 선택값은 [`Rental`, `Store`, `MenuItem` 모델](../backend/app/schemas.py)을 참고한다.
- 발표 자료로 보관한다. 운영 API는 수집 테이블에서 상권과 매물을 연결한다.

## 조회 키, 단위와 인덱스

- 서버는 `YYYYQn`을 분기 첫 날짜로 바꾼다. 예를 들어 `2026Q2`는 `2026-04-01`이다. `quarterly_metrics`는 기준 분기까지의 과거 이력과 기준 분기 한 행, `quarterly_population`은 동일 상권과 기준 분기의 한 행을 읽는다. 예측은 기준 분기와 모델 버전으로 결합하고 목표 분기순으로 반환한다. SQL은 [`supabase_data.py`](../backend/app/supabase_data.py)의 `CATALOG`와 `SNAPSHOTS`에 있다.
- 비율 JSON은 0~1 범위로 해석한다. 서버는 전체 건수 또는 인구에 구성비를 곱해 연령 및 시간대의 분기 값을 표시한다. 요일 값은 해당 분기에 실제로 있었던 그 요일의 일수로 나눈 일평균이다. 누락된 비율은 `null`로 남긴다.
- 기본 키와 `source_url` 고유 제약 외에 다음 B-tree 인덱스를 확인했다.

| 인덱스 | 대상 테이블과 컬럼 |
| --- | --- |
| `areas_district_dong_idx` | `areas(district_code, administrative_dong_code)`, `map_selectable`인 행만 |
| `metrics_quarter_idx` | `quarterly_metrics(industry_code, quarter_start)` |
| `forecast_run_idx` | `quarterly_forecasts(model_version, industry_code, origin_quarter_start)` |
| `rental_memberships_listing_idx` | `rental_area_memberships(listing_id)` |
| `cafe_stores_area_idx` | `cafe_stores(area_code)` |
| `cafe_area_memberships_store_idx` | `cafe_area_memberships(store_id)` |
| `cafe_stores_coordinates_idx` | 좌표가 있는 `cafe_stores(latitude, longitude)` |

## 애플리케이션 DB와 초기화

| 테이블 | 기본 키 및 컬럼 | 사용 방식 |
| --- | --- | --- |
| `areas` | `code VARCHAR(32)` PK, `payload JSON` 필수 | 데모 상권 위치 목록. [`commercial_areas.json`](../data/catalog/commercial_areas.json)에서 가져온다. |
| `analysis_snapshots` | `key VARCHAR(100)` PK, `payload JSON` 필수 | 데모의 상권, 업종, 분기별 분석 자료. 키 예시는 `demo:3120052:CS100010:2026Q2`다. [`snapshots.json`](../data/demo/snapshots.json)이 원본이다. |
| `explanations` | `key VARCHAR(64)` PK, `status VARCHAR(20)`, `owner VARCHAR(36)`, `lease_until FLOAT`, `expires_at FLOAT`, `payload JSON`. 모든 컬럼 필수. | 해설 키는 SHA-256 문자열이다. 상태는 `running`, `completed`, `failed`를 사용한다. `owner`는 생성 요청 식별자고 두 만료 시각은 Unix epoch 초다. `payload`는 완료 해설 또는 빈 객체다. |

애플리케이션 DB의 세 테이블은 SQLAlchemy 모델로 정의한다. 로컬 설정의 `SEED_ON_START=true`는 테이블을 준비하며 데모 모드에서는 JSON 원본을 가져온다. Compose 예제의 `init`은 [`scripts/import_demo.py`](../scripts/import_demo.py)를 실행하고, 성공한 뒤 서버가 시작된다. 운영 설정 `SEED_ON_START=false`는 서버 시작 시 테이블 생성과 자료 적재를 수행하지 않는다. 이 저장소에는 운영 PostgreSQL 스키마를 일괄 적용하는 마이그레이션 경로가 연결되어 있지 않다.
