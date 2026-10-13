"""Install a Supabase-hosted scheduler without exporting local Git credentials."""
import os
from pathlib import Path
import httpx
from .health import assess

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "arthurjanicaudschool/project-survival"


def install(store, eid):
    if not store.load(eid):
        raise ValueError("Explicit START required before scheduler installation")
    store.db.execute((ROOT / "supabase/migrations/002_scheduler.sql").read_text(encoding="utf-8"))
    store.db.execute("create extension if not exists pg_cron")
    store.db.execute("create extension if not exists http with schema extensions")
    store.db.execute((ROOT / "supabase/operations/watchdog.sql").read_text(encoding="utf-8"))
    with store.db.transaction():
        store.db.execute("insert into scheduler_config(experiment_id,repository) values(%s,%s) on conflict(experiment_id) do nothing", (eid, REPOSITORY))
        # Existing activation is preserved on reinstall.
        store.db.execute("select cron.schedule('survival-watchdog','*/2 * * * *','select public.survival_watchdog_tick();')")
    return status(store, eid)


def activate(store, eid, token):
    if not token.startswith("github_pat_"):
        raise ValueError("Use a dedicated fine-grained GitHub token, restricted to this repository and Actions read/write")
    with httpx.Client(timeout=20, headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}) as api:
        response = api.get(f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/cycle.yml")
        response.raise_for_status()
        if response.json().get("state") != "active":
            raise ValueError("GitHub workflow must be active")
    with store.db.transaction():
        store.db.execute("select pg_advisory_xact_lock(hashtextextended('survival-watchdog-secret',2))")
        existing = store.db.execute("select id from vault.secrets where name='survival_github_scheduler'").fetchone()
        if existing:
            store.db.execute("select vault.update_secret(%s,%s)", (existing[0], token))
        else:
            store.db.execute("select vault.create_secret(%s,'survival_github_scheduler','Dedicated repository Actions scheduler token')", (token,))
        store.db.execute("update scheduler_config set enabled=true where experiment_id=%s", (eid,))
    # API acceptance is still not cycle completion.
    return {"tick": store.db.execute("select survival_watchdog_tick()").fetchone()[0], "scheduler": status(store, eid)}


def status(store, eid):
    state = store.load(eid)
    result = {"current_health": assess(state) if state else None}
    if not store.db.execute("select to_regclass('public.scheduler_config') is not null").fetchone()[0]:
        return result | {"installed": False, "enabled": False}
    config = store.db.execute("select repository,branch,enabled from scheduler_config where experiment_id=%s", (eid,)).fetchone()
    result.update(installed=config is not None, enabled=config[2] if config else False)
    result["recent_dispatches"] = [dict(zip(("at", "status", "request_id", "http_status", "error_code"), row)) for row in store.db.execute(
        "select created_at,status,request_id,http_status,error_code from scheduler_dispatches where experiment_id=%s order by created_at desc limit 8", (eid,)).fetchall()]
    if store.db.execute("select to_regclass('cron.job') is not null").fetchone()[0]:
        result["cron_jobs"] = [dict(zip(("jobname", "schedule", "active"), row)) for row in store.db.execute(
            "select jobname,schedule,active from cron.job where jobname='survival-watchdog'").fetchall()]
    return result
