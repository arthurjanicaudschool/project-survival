begin;
alter table experiments drop constraint if exists experiments_status_check;
alter table experiments add constraint experiments_status_check check(status in ('RUNNING','CLOSING','FINISHED'));
create table if not exists analysis_sessions (
 id text primary key, experiment_id text not null references experiments(id), agent_id text not null,
 status text not null, created_at timestamptz not null, updated_at timestamptz not null default now(), payload jsonb not null,
 foreign key(experiment_id,agent_id) references agents(experiment_id,id)
);
create table if not exists external_cache(key text primary key, expires_at timestamptz not null, payload jsonb not null);
create table if not exists llm_meter (
 id text primary key, experiment_id text not null references experiments(id), agent_id text not null,
 created_at timestamptz not null default now(), status text not null,
 estimated_eur numeric not null check(estimated_eur>=0), payload jsonb not null
);
create index if not exists llm_meter_day on llm_meter(experiment_id,created_at);
create index if not exists analysis_agent on analysis_sessions(experiment_id,agent_id,created_at);
-- Conservative one-time baseline for previously committed token counts. Older
-- unmetered requests cannot be reconstructed; actual billing remains external.
insert into llm_meter(id,experiment_id,agent_id,status,estimated_eur,payload)
 select 'historical-v5:'||experiment_id||':'||id,experiment_id,id,'HISTORICAL_ESTIMATE',
 (coalesce((payload#>>'{stats,llm_usage,prompt_tokens}')::numeric,0)*5.28
 +coalesce((payload#>>'{stats,llm_usage,completion_tokens}')::numeric,0)*15.84)/1000000,
 jsonb_build_object('method','Conservative historical committed-token baseline; failed/unmetered requests unknown')
 from agents where payload#>'{stats,llm_usage}' is not null
 on conflict(id) do nothing;
do $$ declare t text; begin
 foreach t in array array['analysis_sessions','external_cache','llm_meter'] loop
  execute format('alter table %I enable row level security',t);
  execute format('revoke all on %I from anon,authenticated',t);
 end loop;
end $$;
-- A runtime identity can be provisioned separately without migration privileges.
do $$ begin if not exists(select 1 from pg_roles where rolname='survival_runtime') then create role survival_runtime nologin; end if; end $$;
grant usage on schema public to survival_runtime;
grant select on experiments,strategies,agents,markets,cycles,market_snapshots,agent_decisions,simulated_orders,simulated_fills,positions,ledger_entries,portfolio_snapshots,agent_memories,system_events,final_reports,dashboard_states,dashboard_updates,llm_attempts,analysis_sessions,external_cache,llm_meter to survival_runtime;
grant insert on experiments,strategies,agents,markets,cycles,market_snapshots,agent_decisions,simulated_orders,simulated_fills,positions,ledger_entries,portfolio_snapshots,agent_memories,system_events,final_reports,dashboard_states,dashboard_updates,llm_attempts,analysis_sessions,external_cache,llm_meter to survival_runtime;
grant update on experiments,agents,markets,positions,agent_memories,dashboard_states,dashboard_updates,analysis_sessions,external_cache,llm_meter to survival_runtime;
grant select on scheduler_config,scheduler_dispatches to survival_runtime;
do $$ declare t text; begin
 foreach t in array array['experiments','strategies','agents','markets','cycles','market_snapshots','agent_decisions','simulated_orders','simulated_fills','positions','ledger_entries','portfolio_snapshots','agent_memories','system_events','final_reports','dashboard_states','dashboard_updates','llm_attempts','analysis_sessions','external_cache','llm_meter','scheduler_config','scheduler_dispatches'] loop
  execute format('drop policy if exists runtime_access on %I',t);
  execute format('create policy runtime_access on %I to survival_runtime using (true) with check (true)',t);
 end loop;
end $$;
commit;
