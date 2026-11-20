begin;

-- Serialize publication, including hypothetical uploads of another snapshot.
select pg_advisory_xact_lock(hashtext('data_tada.location_collection_publish'));

create temporary table location_publish_input on commit drop as
select dataset, row_number, payload
from data_tada.location_collection_rows
where snapshot_id = __SNAPSHOT_ID__;

create index on location_publish_input (dataset);
analyze location_publish_input;

insert into data_tada.rental_listings
    (listing_id, source_url, address, address_precision, deposit_krw, monthly_rent_krw,
     floor_raw, latitude, longitude, map_point_status, checked_at, collection_payload)
select payload->>'listing_id', payload->>'source_url', nullif(payload->>'address',''),
       case when payload->>'building_address' <> '' then 'building' end,
       nullif(payload->>'deposit_krw','')::bigint, nullif(payload->>'monthly_rent_krw','')::bigint,
       nullif(payload->>'floor_raw',''),
       nullif(payload->>'latitude','')::double precision, nullif(payload->>'longitude','')::double precision,
       case when payload->>'latitude' <> '' then 'coordinate_available' else 'no_coordinate' end,
       (payload->>'checked_at')::timestamptz, payload
from location_publish_input
where dataset = 'rentals'
on conflict (listing_id) do update set
    address = excluded.address, address_precision = excluded.address_precision,
    deposit_krw = excluded.deposit_krw, monthly_rent_krw = excluded.monthly_rent_krw,
    floor_raw = excluded.floor_raw, latitude = excluded.latitude, longitude = excluded.longitude,
    map_point_status = excluded.map_point_status, checked_at = excluded.checked_at,
    collection_payload = excluded.collection_payload
where rental_listings.source_url = excluded.source_url
    and (rental_listings.collection_payload is null or rental_listings.checked_at <= excluded.checked_at);

insert into data_tada.rental_area_memberships (area_code, listing_id)
select a.area_code, i.payload->>'listing_id'
from location_publish_input i
join data_tada.areas a on a.area_code = i.payload->>'area_code'
where i.dataset = 'rental_memberships'
on conflict do nothing;

with known_memberships as (
    select i.payload->>'store_id' as store_id, min(a.area_code) as area_code
    from location_publish_input i
    join data_tada.areas a on a.area_code = i.payload->>'area_code'
    where i.dataset = 'cafe_memberships'
    group by 1
)
insert into data_tada.cafe_stores
    (store_id, area_code, name, address, latitude, longitude, permit_status,
     profile_match_status, source_url, collection_as_of, collection_payload)
select i.payload->>'store_id', m.area_code, i.payload->>'name',
       coalesce(nullif(i.payload->>'road_address',''), nullif(i.payload->>'lot_address','')),
       nullif(i.payload->>'latitude','')::double precision, nullif(i.payload->>'longitude','')::double precision,
       null, 'unmatched', i.payload->>'source_url', __CAFE_CHECKED_AT__::timestamptz, i.payload
from location_publish_input i
left join known_memberships m on m.store_id = i.payload->>'store_id'
where i.dataset = 'cafes'
on conflict (store_id) do update set
    area_code = excluded.area_code, name = excluded.name, address = excluded.address,
    latitude = excluded.latitude, longitude = excluded.longitude, source_url = excluded.source_url,
    collection_as_of = excluded.collection_as_of, collection_payload = excluded.collection_payload
where cafe_stores.collection_payload is not null and cafe_stores.collection_as_of <= excluded.collection_as_of;

insert into data_tada.cafe_area_memberships (area_code, store_id)
select a.area_code, i.payload->>'store_id'
from location_publish_input i
join data_tada.areas a on a.area_code = i.payload->>'area_code'
where i.dataset = 'cafe_memberships'
on conflict do nothing;

with new_menus as (
    select i.row_number, i.payload, i.payload->>'store_id' as store_id
    from location_publish_input i
    where i.dataset = 'cafe_menus'
    and not exists (
        select 1 from data_tada.cafe_menus m
        where m.store_id = i.payload->>'store_id' and m.collection_payload = i.payload
    )
), last_menu as (
    select m.store_id, max(m.menu_index) as menu_index
    from data_tada.cafe_menus m
    join (select distinct store_id from new_menus) n using (store_id)
    group by m.store_id
)
insert into data_tada.cafe_menus
    (store_id, menu_index, name, price_krw, price_status, checked_at, collection_payload)
select n.store_id, coalesce(l.menu_index, 0) + row_number() over (partition by n.store_id order by n.row_number),
       payload->>'menu_name', nullif(payload->>'price_krw','')::bigint,
       case when payload->>'price_krw' <> '' then 'observed' else 'not_disclosed_or_variable' end,
       case when payload->>'source' = 'seongsu_pilot' then (payload->>'source_date')::timestamptz
            else __CAFE_CHECKED_AT__::timestamptz end,
       payload
from new_menus n
left join last_menu l using (store_id);

-- Verify row identity before making the run available as a completed snapshot.
do $verify$
begin
    if exists (
        select 1 from location_publish_input i
        where (dataset = 'rentals' and not exists (
            select 1 from data_tada.rental_listings r where r.listing_id = i.payload->>'listing_id'
              and r.collection_payload = i.payload
        )) or (dataset = 'cafes' and not exists (
            select 1 from data_tada.cafe_stores c where c.store_id = i.payload->>'store_id'
              and c.collection_payload = i.payload
        )) or (dataset = 'cafe_menus' and not exists (
            select 1 from data_tada.cafe_menus m where m.store_id = i.payload->>'store_id'
              and m.collection_payload = i.payload
        )) or (dataset = 'rental_memberships' and exists (
            select 1 from data_tada.areas a where a.area_code = i.payload->>'area_code'
        ) and not exists (
            select 1 from data_tada.rental_area_memberships r
            where r.area_code = i.payload->>'area_code' and r.listing_id = i.payload->>'listing_id'
        )) or (dataset = 'cafe_memberships' and exists (
            select 1 from data_tada.areas a where a.area_code = i.payload->>'area_code'
        ) and not exists (
            select 1 from data_tada.cafe_area_memberships c
            where c.area_code = i.payload->>'area_code' and c.store_id = i.payload->>'store_id'
        ))
    ) then
        raise exception 'Location collection projection incomplete';
    end if;
end
$verify$;

update data_tada.location_collection_runs
set uploaded_at = now()
where snapshot_id = __SNAPSHOT_ID__ and uploaded_at is null;

commit;
