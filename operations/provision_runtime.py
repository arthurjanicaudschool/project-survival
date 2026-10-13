"""Provision a limited DB login and replace the GitHub runtime secret safely.

Local-only optional dependency: PyNaCl (GitHub sealed-box encryption).
The administration connection is retained only in the local .env.
"""

import os
import json
import base64
import secrets
import subprocess
from pathlib import Path
from dotenv import load_dotenv, set_key
import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from nacl.public import PublicKey, SealedBox

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / ".env")
    admin = os.getenv("DATABASE_ADMIN_URL") or os.environ["DATABASE_URL"]
    credential = subprocess.run(
        ["C:/Program Files/Git/cmd/git.exe", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        check=True,
    )
    fields = dict(
        line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line
    )
    endpoint = "https://api.github.com/repos/arthurjanicaudschool/project-survival/actions/secrets"
    with httpx.Client(
        headers={
            "Authorization": "Bearer " + fields["password"],
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    ) as github:
        key = github.get(endpoint + "/public-key")
        key.raise_for_status()
        key = key.json()
        password = secrets.token_urlsafe(48)
        with psycopg.connect(admin, autocommit=True) as db:
            with db.transaction():
                if not db.execute(
                    "select 1 from pg_roles where rolname='survival_runner'"
                ).fetchone():
                    db.execute("create role survival_runner login inherit")
                db.execute(
                    sql.SQL("alter role survival_runner password {}").format(
                        sql.Literal(password)
                    )
                )
                db.execute("grant survival_runtime to survival_runner")
        config = conninfo_to_dict(admin)
        old = config["user"]
        suffix = "." + old.split(".", 1)[1] if "." in old else ""
        config.update(user="survival_runner" + suffix, password=password)
        runtime = make_conninfo(**config)
        with psycopg.connect(runtime, connect_timeout=20) as db:
            identity = db.execute(
                "select current_user,has_table_privilege(current_user,'ledger_entries','UPDATE'),has_schema_privilege(current_user,'public','CREATE')"
            ).fetchone()
            if identity[0] != "survival_runner" or identity[1] or identity[2]:
                raise RuntimeError(
                    "Runtime role permissions are not sufficiently limited"
                )
            if not db.execute(
                "select id from experiments where id='survival-001'"
            ).fetchone():
                raise RuntimeError("Runtime cannot read active experiment")
        encrypted = base64.b64encode(
            SealedBox(PublicKey(base64.b64decode(key["key"]))).encrypt(runtime.encode())
        ).decode()
        updated = github.put(
            endpoint + "/DATABASE_URL",
            json={"encrypted_value": encrypted, "key_id": key["key_id"]},
        )
        updated.raise_for_status()
        set_key(str(ROOT / ".env"), "DATABASE_ADMIN_URL", admin)
        set_key(str(ROOT / ".env"), "DATABASE_URL", runtime)
    print(
        json.dumps(
            {
                "runtime_user": "survival_runner",
                "github_secret_updated": True,
                "local_runtime_updated": True,
                "ledger_update_allowed": False,
                "schema_create_allowed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
