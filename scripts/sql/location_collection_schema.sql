begin;

create table if not exists data_tada.location_collection_runs (
    snapshot_id text primary key,
    manifest jsonb not null,
    uploaded_at timestamptz
);

create table if not exists data_tada.location_collection_rows (
    snapshot_id text not null references data_tada.location_collection_runs(snapshot_id),
    dataset text not null,
    row_number integer not null check (row_number > 0),
    payload jsonb not null,
    primary key (snapshot_id, dataset, row_number)
);

create table if not exists data_tada.cafe_area_memberships (
    area_code text not null references data_tada.areas(area_code),
    store_id text not null references data_tada.cafe_stores(store_id),
    primary key (area_code, store_id)
);

create index if not exists cafe_area_memberships_store_idx on data_tada.cafe_area_memberships(store_id);

alter table data_tada.location_collection_runs enable row level security;
alter table data_tada.location_collection_rows enable row level security;
alter table data_tada.cafe_area_memberships enable row level security;
revoke all on data_tada.location_collection_runs, data_tada.location_collection_rows,
    data_tada.cafe_area_memberships from public, anon, authenticated;

-- A business-directory record can sit outside every area and has no permit evidence.
alter table data_tada.cafe_stores alter column area_code drop not null;
alter table data_tada.cafe_stores alter column permit_status drop not null;

alter table data_tada.rental_listings add column if not exists collection_payload jsonb;
alter table data_tada.cafe_stores add column if not exists collection_payload jsonb;
alter table data_tada.cafe_menus add column if not exists collection_payload jsonb;

commit;
