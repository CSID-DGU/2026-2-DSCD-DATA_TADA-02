create schema if not exists analysis_cache;
revoke all on schema analysis_cache from public;

create table if not exists analysis_cache.explanations (
    key varchar(64) primary key,
    status varchar(20) not null,
    owner varchar(36) not null,
    lease_until double precision not null,
    expires_at double precision not null,
    payload json not null
);
revoke all on table analysis_cache.explanations from public;
