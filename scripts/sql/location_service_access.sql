begin;

-- Only the existing server database role can read these location tables.
grant select on data_tada.rental_listings, data_tada.rental_area_memberships,
    data_tada.cafe_stores, data_tada.cafe_area_memberships, data_tada.cafe_menus to data_tada_app;

drop policy if exists location_service_read on data_tada.rental_listings;
create policy location_service_read on data_tada.rental_listings
    for select to data_tada_app using (true);
drop policy if exists location_service_read on data_tada.rental_area_memberships;
create policy location_service_read on data_tada.rental_area_memberships
    for select to data_tada_app using (true);
drop policy if exists location_service_read on data_tada.cafe_stores;
create policy location_service_read on data_tada.cafe_stores
    for select to data_tada_app using (true);
drop policy if exists location_service_read on data_tada.cafe_area_memberships;
create policy location_service_read on data_tada.cafe_area_memberships
    for select to data_tada_app using (true);
drop policy if exists location_service_read on data_tada.cafe_menus;
create policy location_service_read on data_tada.cafe_menus
    for select to data_tada_app using (true);

create index if not exists cafe_stores_coordinates_idx on data_tada.cafe_stores(latitude, longitude)
    where latitude is not null and longitude is not null;

create or replace view data_tada.service_cafe_store_brands as
select payload->>'store_id' as store_id, payload->>'brand' as brand
from data_tada.location_collection_rows
where dataset = 'cafe_store_brands' and snapshot_id = (
    select snapshot_id from data_tada.location_collection_runs
    where uploaded_at is not null and (manifest->'inputs'->'cafe_store_brands'->>'rows')::integer > 0
    order by uploaded_at desc, snapshot_id desc limit 1
);

create or replace view data_tada.service_cafe_brand_menus as
select payload->>'brand' as brand, payload->>'menu_name' as name, payload->>'channel' as channel,
       nullif(payload->>'price_krw', '')::bigint as price_krw, payload->>'source_url' as source_url,
       payload->>'collected_at' as source_date
from data_tada.location_collection_rows
where dataset = 'cafe_brand_menus' and snapshot_id = (
    select snapshot_id from data_tada.location_collection_runs
    where uploaded_at is not null and (manifest->'inputs'->'cafe_store_brands'->>'rows')::integer > 0
    order by uploaded_at desc, snapshot_id desc limit 1
);

revoke all on data_tada.service_cafe_store_brands, data_tada.service_cafe_brand_menus
    from public, anon, authenticated;
grant select on data_tada.service_cafe_store_brands, data_tada.service_cafe_brand_menus to data_tada_app;

commit;
