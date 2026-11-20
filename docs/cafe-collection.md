# 서울 카페 점포와 메뉴 수집

서울 상권 1,650곳의 경계와 공공기관이 제공하는 카페 주소 및 좌표를 연결한다. 소상공인시장진흥공단 서울 원자료의 카페 업종 코드 `I21201`을 사용한다. 점포 하나가 여러 경계에 포함되면 각 상권에 기록한다. 상권 밖 점포도 서울 점포 목록에서 조회할 수 있다. 목록의 기준일은 공단 자료에 따르며 개별 매장의 당일 영업 상태는 확인하지 않는다. [소상공인시장진흥공단 상가정보](https://www.data.go.kr/data/15083033/fileData.do)

착한가격업소 메뉴는 공공 원자료의 상호와 건물 주소가 카페 한 곳으로 확인될 때 연결한다. `--pilot`과 `--tourism`을 지정하면 기존 성수역 관측 데이터와 서울시 관광 음식의 대표 메뉴도 같은 기준으로 연결한다. 착한가격업소 가격은 지정된 품목에 한해 제공된다. 성수역 메뉴는 이전 수집 시점의 가격이고, 서울시 관광 음식의 대표 메뉴는 항목마다 공개 가격 여부가 다르다. [행정안전부 착한가격업소](https://www.data.go.kr/data/15172358/fileData.do) / [서울시 관광 음식](https://data.seoul.go.kr/dataList/OA-21054/S/1/datasetView.do)

`--brands live`는 빽다방, 더벤티, 메가MGC커피, 스타벅스 공식 메뉴와 할리스 공식 기프트 상품을 읽는다. `store_brands.csv`의 연결은 공단 상호의 브랜드 표기를 기준으로 한다. 할리스 가격은 기프트 상품에 표기된 금액으로, 매장 메뉴의 가격 통계에서 제외한다. 본사 메뉴의 매장별 판매 여부는 확인하지 않는다. [빽다방](https://paikdabang.com/menu/menu_coffee/) / [더벤티](https://www.theventi.co.kr/new2022/menu/all.html) / [메가MGC커피](https://www.mega-mgccoffee.com/menu/) / [스타벅스](https://www.starbucks.co.kr/menu/drink_list.do) / [할리스](https://www.hollys.co.kr/mall/product.do)

## 실행

저장소 루트에서 Windows의 정규 Python 3.13을 사용한다. 기존 임대매물 수집과 같은 `pyshp`, `pyproj`, `shapely`와 상권 경계 ZIP이 필요하다. 경계 경로를 변경할 때는 `--boundary`를 지정한다.

```powershell
$p = Start-Process -FilePath 'C:\Program Files\Python313\python.exe' `
    -ArgumentList '-X','utf8','scripts/collect_cafes.py','--brands','live' `
    -WorkingDirectory (Get-Location).Path -Wait -PassThru -NoNewWindow
exit $p.ExitCode
```

공공데이터포털의 최신 파일을 내려받고 같은 기준일의 파일이 로컬에 있으면 다시 사용한다. 이미 내려받은 공단 ZIP과 착한가격업소 CSV는 각각 `--stores`와 `--stores-date`, `--good-price`와 `--good-price-date`로 지정할 수 있다. 날짜 형식은 `YYYY-MM-DD`다. `--brands cached`는 내려받은 공식 메뉴 원문을 재사용한다.

이전 메뉴 자료까지 연결할 때는 `--pilot data/supabase_upload_20261106/reference`와 `--tourism`에 `jsw/10.23 회의/전체자료_확보검증/processed/tourism_restaurant_menus_hours.csv`를 지정한다. 이전 자료는 이 경로에 파일이 있는 작업 환경에서 사용할 수 있다.

## 로컬 결과

결과는 `data/cafe_collection/<실행일시>/`에 저장한다.

| 파일 | 내용 |
| --- | --- |
| `cafe_stores.csv` | 서울 카페 ID, 상호, 지점명, 주소, 좌표, 상권 연결 상태 |
| `cafe_menus.csv` | 상호와 주소가 연결된 매장의 메뉴명, 확인 가능한 원화 가격, 원본 링크 |
| `unmatched_menu_candidates.csv` | 명칭과 메뉴에서 카페로 추정되지만 공단 점포 ID를 확정하지 못한 착한가격 후보 |
| `brand_menus.csv` | 본사 메뉴와 기프트 상품 정보 |
| `store_brands.csv` | 공단 점포 ID와 브랜드 연결 |
| `area_memberships.csv` | 상권 코드와 상권 안에 포함된 점포 ID |
| `area_coverage.csv` | 각 상권의 점포 수, 매장별 메뉴 및 가격이 있는 점포 수, 브랜드 연결 점포 수 |
| `summary.json` | 원자료 기준일, 상권 연결 수, 메뉴 출처별 수집 건수 |
