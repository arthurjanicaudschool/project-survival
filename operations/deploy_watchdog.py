"""Deploy the independent scheduler; secrets are never emitted to stdout."""

import json
import os
from pathlib import Path
import httpx
import psycopg
from dotenv import load_dotenv, dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / ".env")
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    public = dotenv_values(ROOT / "frontend/.env")
    with psycopg.connect(
        os.getenv("DATABASE_ADMIN_URL") or os.environ["DATABASE_URL"]
    ) as db:
        row = db.execute(
            "select decrypted_secret from vault.decrypted_secrets where name='survival_github_scheduler'"
        ).fetchone()
        if not row:
            raise ValueError("Dedicated repository Actions token missing from Vault")
        scheduler_token = row[0]
    bindings = [
        {"type": "plain_text", "name": k, "text": v}
        for k, v in {
            "SUPABASE_URL": public["VITE_SUPABASE_URL"],
            "SUPABASE_ANON_KEY": public["VITE_SUPABASE_ANON_KEY"],
            "EXPERIMENT_ID": os.getenv("EXPERIMENT_ID", "survival-001"),
            "GITHUB_REPOSITORY": "arthurjanicaudschool/project-survival",
        }.items()
    ]
    bindings.append(
        {
            "type": "secret_text",
            "name": "GITHUB_SCHEDULER_TOKEN",
            "text": scheduler_token,
        }
    )
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/scripts/project-survival-watchdog"
    metadata = {
        "main_module": "worker.js",
        "compatibility_date": "2026-10-01",
        "bindings": bindings,
    }
    with httpx.Client(headers={"Authorization": "Bearer " + token}, timeout=60) as api:
        upload = api.put(
            endpoint,
            files={
                "metadata": (None, json.dumps(metadata), "application/json"),
                "worker.js": (
                    "worker.js",
                    (ROOT / "scheduler/worker.js").read_text(encoding="utf-8"),
                    "application/javascript+module",
                ),
            },
        )
        if not upload.is_success or not upload.json().get("success"):
            raise RuntimeError(
                f"Worker upload failed HTTP {upload.status_code}; codes {[e.get('code') for e in upload.json().get('errors', [])]}"
            )
        scheduled = api.put(endpoint + "/schedules", json=[{"cron": "*/5 * * * *"}])
        if not scheduled.is_success or not scheduled.json().get("success"):
            raise RuntimeError(f"Worker cron failed HTTP {scheduled.status_code}")
        confirmed = api.get(endpoint + "/schedules")
        confirmed.raise_for_status()
        if not confirmed.json().get("success"):
            raise RuntimeError("Worker cron not confirmed")
        print(
            json.dumps(
                {
                    "worker": "project-survival-watchdog",
                    "deployed": True,
                    "schedules": confirmed.json()["result"],
                    "paper_only": True,
                }
            )
        )


if __name__ == "__main__":
    main()
