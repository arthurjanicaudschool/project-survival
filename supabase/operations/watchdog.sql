-- Supabase only: CLI installs pg_cron and http before loading this file.
-- Called by cron as postgres. No service, Azure or wallet key is needed here.
-- Synchronous HTTPS avoids persisting Authorization in pg_net's public queue.
create or replace function public.survival_watchdog_tick()
returns jsonb language plpgsql security definer
set search_path = pg_catalog,public as $$
declare c record; token text; rid bigint; code integer; result jsonb := '[]'::jsonb;
begin
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
  insert into public.scheduler_dispatches(experiment_id,status) values(c.experiment_id,'REQUESTED') returning id into rid;
  code := null;
  begin
   perform extensions.http_set_curlopt('CURLOPT_CONNECTTIMEOUT_MS','5000');
   perform extensions.http_set_curlopt('CURLOPT_TIMEOUT_MS','15000');
   perform extensions.http_set_curlopt('CURLOPT_FOLLOWLOCATION','0');
   select status into code from extensions.http(row(
    'POST'::extensions.http_method,
    'https://api.github.com/repos/' || c.repository || '/actions/workflows/cycle.yml/dispatches',
    array[row('Authorization','Bearer ' || token)::extensions.http_header,
      row('Accept','application/vnd.github+json')::extensions.http_header,
      row('User-Agent','ProjectSurvivalWatchdog')::extensions.http_header],
    'application/json',
    jsonb_build_object('ref',c.branch,'inputs',jsonb_build_object('action','cycle','source','supabase-watchdog'))::text
   )::extensions.http_request);
  exception when others then
   -- Do not persist provider exception text, request bodies or headers.
   code := null;
  end;
  insert into public.scheduler_dispatches(experiment_id,status,request_id,http_status) values(c.experiment_id,'HTTP_RESULT',rid,code);
  result := result || jsonb_build_array(jsonb_build_object('experiment_id',c.experiment_id,'status','HTTP_RESULT','request_id',rid,'http_status',code));
 end loop;
 return result;
end;
$$;
revoke all on function public.survival_watchdog_tick() from public,anon,authenticated;
