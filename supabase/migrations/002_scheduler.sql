begin;
create table if not exists scheduler_config (
 experiment_id text primary key references experiments(id),
 repository text not null check(repository ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
 branch text not null default 'main', enabled boolean not null default false
);
create table if not exists scheduler_dispatches (
 id bigint generated always as identity primary key,
 experiment_id text not null references experiments(id),
 created_at timestamptz not null default clock_timestamp(),
 status text not null check(status in ('REQUESTED','MISSING_TOKEN','HTTP_RESULT')),
 request_id bigint, http_status integer,
 unique(request_id,status)
);
create index if not exists scheduler_recent on scheduler_dispatches(experiment_id,created_at desc);
alter table scheduler_config enable row level security;
alter table scheduler_dispatches enable row level security;
revoke all on scheduler_config,scheduler_dispatches from public,anon,authenticated;
drop trigger if exists immutable_audit on scheduler_dispatches;
create trigger immutable_audit before update or delete on scheduler_dispatches
 for each row execute function prevent_audit_mutation();

create or replace function survival_watchdog_due(eid text, observed_at timestamptz default clock_timestamp())
returns boolean language sql stable set search_path = pg_catalog,public as $$
 select coalesce((
  select c.enabled and e.status <> 'FINISHED'
   and coalesce((e.state->'health'->>'started_at')::timestamptz,e.updated_at)
       <= observed_at - interval '9 minutes'
   and not exists(select 1 from public.scheduler_dispatches d
    where d.experiment_id=e.id and d.status <> 'HTTP_RESULT'
      and d.created_at > observed_at - interval '9 minutes')
  from public.experiments e join public.scheduler_config c on c.experiment_id=e.id
  where e.id=eid
 ),false);
$$;
revoke all on function survival_watchdog_due(text,timestamptz) from public,anon,authenticated;
commit;
