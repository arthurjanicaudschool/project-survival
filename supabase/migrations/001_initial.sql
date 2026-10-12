begin;
create table if not exists experiments (
 id text primary key, mode text not null check(mode in ('live','demo')),
 status text not null check(status in ('RUNNING','FINISHED')),
 started_at timestamptz not null, end_at timestamptz not null,
 state jsonb not null, updated_at timestamptz not null default now(),
 check(end_at > started_at)
);
create table if not exists strategies(id text primary key, payload jsonb not null);
create table if not exists agents (
 experiment_id text references experiments(id), id text check(id ~ '^A([1-9]|10)$'),
 strategy_id text references strategies(id), initial_eur numeric not null check(initial_eur in (10,50)),
 cash numeric not null check(cash>=0), payload jsonb not null,
 primary key(experiment_id,id)
);
create table if not exists markets(id text primary key, payload jsonb not null);
create table if not exists cycles (
 experiment_id text references experiments(id), id text, created_at timestamptz not null,
 primary key(experiment_id,id)
);
create table if not exists market_snapshots (
 id text primary key, experiment_id text references experiments(id), cycle_id text not null,
 market_id text references markets(id), created_at timestamptz not null, payload jsonb not null,
 foreign key(experiment_id,cycle_id) references cycles(experiment_id,id)
);
create table if not exists agent_decisions (
 id text primary key, experiment_id text not null, agent_id text not null,
 cycle_id text not null, created_at timestamptz not null, payload jsonb not null,
 foreign key(experiment_id,agent_id) references agents(experiment_id,id),
 foreign key(experiment_id,cycle_id) references cycles(experiment_id,id)
);
create table if not exists simulated_orders (
 id text primary key, experiment_id text not null, agent_id text not null,
 decision_id text references agent_decisions(id), status text not null check(status in ('FILLED','PARTIAL','REJECTED')),
 created_at timestamptz not null, payload jsonb not null,
 foreign key(experiment_id,agent_id) references agents(experiment_id,id)
);
create table if not exists simulated_fills (
 id text primary key, order_id text references simulated_orders(id),
 quantity numeric not null check(quantity>0), price numeric not null check(price>0 and price<1),
 fee numeric not null check(fee>=0), payload jsonb not null
);
create table if not exists positions (
 experiment_id text not null, agent_id text not null, market_id text references markets(id),
 outcome text check(outcome in ('YES','NO')), quantity numeric not null check(quantity>=0),
 cost numeric not null check(cost>=0), payload jsonb not null,
 primary key(experiment_id,agent_id,market_id,outcome),
 foreign key(experiment_id,agent_id) references agents(experiment_id,id)
);
create table if not exists ledger_entries (
 id text primary key, experiment_id text not null, agent_id text not null,
 kind text not null check(kind in ('INITIAL','BUY','SELL','RESOLUTION')),
 amount numeric not null, created_at timestamptz not null, payload jsonb not null,
 foreign key(experiment_id,agent_id) references agents(experiment_id,id)
);
create table if not exists portfolio_snapshots (
 id text primary key, experiment_id text not null, agent_id text not null,
 created_at timestamptz not null, payload jsonb not null,
 foreign key(experiment_id,agent_id) references agents(experiment_id,id)
);
create table if not exists agent_memories (
 experiment_id text not null, agent_id text not null, payload jsonb not null,
 primary key(experiment_id,agent_id),
 foreign key(experiment_id,agent_id) references agents(experiment_id,id)
);
create table if not exists system_events (
 id text primary key, experiment_id text references experiments(id),
 created_at timestamptz not null, payload jsonb not null
);
create table if not exists final_reports (
 experiment_id text primary key references experiments(id), created_at timestamptz not null, payload jsonb not null
);
create table if not exists dashboard_states (
 experiment_id text primary key references experiments(id), updated_at timestamptz not null, payload jsonb not null
);
create table if not exists llm_attempts (
 id text primary key, experiment_id text references experiments(id), agent_id text not null,
 utc_day date not null, created_at timestamptz not null,
 foreign key(experiment_id,agent_id) references agents(experiment_id,id)
);
create table if not exists dashboard_updates (
 experiment_id text primary key references experiments(id), updated_at timestamptz not null
);
create index if not exists llm_daily on llm_attempts(experiment_id,agent_id,utc_day);
create index if not exists events_time on system_events(experiment_id,created_at desc);
create index if not exists snapshots_time on portfolio_snapshots(experiment_id,created_at);
create index if not exists decisions_time on agent_decisions(experiment_id,agent_id,created_at);

create or replace function prevent_audit_mutation() returns trigger language plpgsql as $$
begin raise exception 'Audit records are append-only'; end; $$;
do $$ declare t text; begin
 foreach t in array array['ledger_entries','simulated_fills','simulated_orders','agent_decisions','market_snapshots','portfolio_snapshots','system_events','final_reports','cycles','llm_attempts'] loop
   execute format('drop trigger if exists immutable_audit on %I',t);
   execute format('create trigger immutable_audit before update or delete on %I for each row execute function prevent_audit_mutation()',t);
 end loop;
 foreach t in array array['experiments','strategies','agents','markets','cycles','market_snapshots','agent_decisions','simulated_orders','simulated_fills','positions','ledger_entries','portfolio_snapshots','agent_memories','system_events','final_reports','dashboard_states','dashboard_updates','llm_attempts'] loop
   execute format('alter table %I enable row level security',t);
   execute format('revoke all on %I from anon, authenticated',t);
 end loop;
end $$;
grant select on dashboard_states to anon,authenticated;
grant select on dashboard_updates to anon,authenticated;
drop policy if exists public_dashboard on dashboard_states;
create policy public_dashboard on dashboard_states for select to anon,authenticated using (true);
drop policy if exists public_updates on dashboard_updates;
create policy public_updates on dashboard_updates for select to anon,authenticated using (true);
-- Only the deliberately public projection is exposed, with no backend secrets.
do $$ begin
 if exists(select 1 from pg_publication_tables where pubname='supabase_realtime' and tablename='dashboard_states') then
   alter publication supabase_realtime drop table dashboard_states;
 end if;
 if not exists(select 1 from pg_publication_tables where pubname='supabase_realtime' and tablename='dashboard_updates') then
   alter publication supabase_realtime add table dashboard_updates;
 end if;
end $$;
commit;
