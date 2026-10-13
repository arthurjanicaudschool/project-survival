-- Supabase only: CLI installs pg_cron and pg_net before loading this file.
-- Called by cron as postgres. No service, Azure or wallet key is needed here.
create or replace function public.survival_watchdog_tick()
returns jsonb language plpgsql security definer
set search_path = pg_catalog,public as $$
declare c record; token text; rid bigint; result jsonb := '[]'::jsonb;
begin
 -- Preserve HTTP outcomes before pg_net expires its transient response rows.
 insert into public.scheduler_dispatches(experiment_id,status,request_id,http_status)
 select d.experiment_id,'HTTP_RESULT',d.request_id,r.status_code
 from public.scheduler_dispatches d join net._http_response r on r.id=d.request_id
 where d.status='REQUESTED'
 on conflict(request_id,status) do nothing;
 for c in select * from public.scheduler_config where enabled loop
  if not pg_try_advisory_xact_lock(hashtextextended(c.experiment_id,2)) then continue; end if;
  if not public.survival_watchdog_due(c.experiment_id) then continue; end if;
  -- Same lock as the Python engine: never interrupt an active financial cycle.
  if not pg_try_advisory_xact_lock(hashtextextended(c.experiment_id,0)) then continue; end if;
  select decrypted_secret into token from vault.decrypted_secrets
    where name='survival_github_scheduler' limit 1;
  if token is null or length(token)=0 then
   insert into public.scheduler_dispatches(experiment_id,status) values(c.experiment_id,'MISSING_TOKEN');
   result := result || jsonb_build_array(jsonb_build_object('experiment_id',c.experiment_id,'status','MISSING_TOKEN'));
   continue;
  end if;
  select net.http_post(
   url := 'https://api.github.com/repos/' || c.repository || '/actions/workflows/cycle.yml/dispatches',
   headers := jsonb_build_object('Authorization','Bearer ' || token,'Accept','application/vnd.github+json',
     'User-Agent','ProjectSurvivalWatchdog','Content-Type','application/json'),
   body := jsonb_build_object('ref',c.branch,'inputs',jsonb_build_object('action','cycle','source','supabase-watchdog')),
   timeout_milliseconds := 15000
  ) into rid;
  insert into public.scheduler_dispatches(experiment_id,status,request_id) values(c.experiment_id,'REQUESTED',rid);
  result := result || jsonb_build_array(jsonb_build_object('experiment_id',c.experiment_id,'status','REQUESTED','request_id',rid));
 end loop;
 return result;
end;
$$;
revoke all on function public.survival_watchdog_tick() from public,anon,authenticated;
