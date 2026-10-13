import os
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
import pytest
import psycopg
from survival.store import Store
from survival.runner import initialize
from survival.models import utcnow
from survival.watchdog import activate


def test_watchdog_rejects_broad_credentials_before_network_or_database():
    with pytest.raises(ValueError, match="fine-grained"):
        activate(None, "test", "broad-credential-placeholder")


@pytest.mark.integration
def test_watchdog_dispatch_missing_secret_lock_and_http_result():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated disposable PostgreSQL required")
    store, second = Store(url), Store(url)
    eid = "scheduler-" + str(uuid4())
    now = utcnow() - timedelta(hours=1)
    try:
        initialize(store, eid, "demo", {"usd_per_eur": "1.1"}, now)
        # Disposable CI database only. Replace network/Vault with observable stubs.
        store.db.execute("""
          create schema if not exists extensions; create schema if not exists vault;
          create type extensions.http_method as enum('POST');
          create type extensions.http_header as (field varchar,value varchar);
          create type extensions.http_request as (method extensions.http_method,uri varchar,headers extensions.http_header[],content_type varchar,content varchar);
          create table if not exists extensions.test_requests(id bigint generated always as identity, url text, body jsonb);
          create table if not exists vault.decrypted_secrets(name text,decrypted_secret text);
          create function extensions.http_set_curlopt(text,text) returns boolean language plpgsql as $$
          begin if $1 not in ('CURLOPT_CONNECTTIMEOUT_MS','CURLOPT_TIMEOUT_MS') then raise exception 'Unsupported test curl option'; end if; return true; end $$;
          create function extensions.http(rq extensions.http_request) returns table(status integer) language plpgsql as $$
          begin insert into extensions.test_requests(url,body) values(rq.uri,rq.content::jsonb); return query select 204; end $$;
        """)
        store.db.execute((Path(__file__).resolve().parent.parent / "supabase/operations/watchdog.sql").read_text(encoding="utf-8"))
        store.db.execute("insert into scheduler_config(experiment_id,repository,enabled) values(%s,'test/repository',true)", (eid,))
        result = store.db.execute("select survival_watchdog_tick()").fetchone()[0]
        assert any(r["status"] == "MISSING_TOKEN" and r["experiment_id"] == eid for r in result)
        assert not store.db.execute("select survival_watchdog_due(%s)", (eid,)).fetchone()[0]
        # Keep the immutable missing-token audit; use a different isolated experiment.
        target = eid + "-ready"
        initialize(store, target, "demo", {"usd_per_eur": "1.1"}, now)
        store.db.execute("insert into scheduler_config(experiment_id,repository,enabled) values(%s,'test/repository',true)", (target,))
        store.db.execute("insert into vault.decrypted_secrets values('survival_github_scheduler','TEST-ONLY-FAKE')")
        with store.locked(target):
            assert not any(r.get("experiment_id") == target for r in second.db.execute("select survival_watchdog_tick()").fetchone()[0])
        result = store.db.execute("select survival_watchdog_tick()").fetchone()[0]
        request = next(r for r in result if r["experiment_id"] == target)
        assert request["status"] == "HTTP_RESULT" and request["http_status"] == 204
        row = store.db.execute("select url,body from extensions.test_requests order by id desc limit 1").fetchone()
        assert row[0] == "https://api.github.com/repos/test/repository/actions/workflows/cycle.yml/dispatches"
        assert row[1]["inputs"] == {"action": "cycle", "source": "supabase-watchdog"}
        assert not store.db.execute("select survival_watchdog_tick()").fetchone()[0]
        store.db.execute("select survival_watchdog_tick()")
        store.db.execute("select survival_watchdog_tick()")
        assert store.db.execute("select count(*) from scheduler_dispatches where experiment_id=%s and status='HTTP_RESULT' and http_status=204", (target,)).fetchone()[0] == 1
        store.db.execute("update experiments set status='FINISHED' where id=%s", (target,))
        assert not store.db.execute("select survival_watchdog_due(%s,%s)", (target, utcnow()+timedelta(hours=2))).fetchone()[0]
        store.db.execute("set role anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            store.db.execute("select survival_watchdog_tick()")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            store.db.execute("select * from extensions.test_requests")
        store.db.execute("reset role")
        failed = eid + "-http-failure"
        initialize(store, failed, "demo", {"usd_per_eur": "1.1"}, now)
        store.db.execute("insert into scheduler_config(experiment_id,repository,enabled) values(%s,'test/repository',true)", (failed,))
        store.db.execute("""create or replace function extensions.http(rq extensions.http_request) returns table(status integer)
          language sql as $$ select 503 $$""")
        result = store.db.execute("select survival_watchdog_tick()").fetchone()[0]
        assert next(r for r in result if r["experiment_id"] == failed)["http_status"] == 503
        assert not store.db.execute("select survival_watchdog_due(%s)", (failed,)).fetchone()[0]
        assert store.db.execute("select survival_watchdog_due(%s,%s)", (failed, utcnow()+timedelta(minutes=3))).fetchone()[0]
    finally:
        store.close(); second.close()
