"""Restore an export into an explicitly empty, migrated, separate database."""

from pathlib import Path
import json
from psycopg import sql
from .models import Wallet

ORDER = [
    "experiments",
    "strategies",
    "agents",
    "markets",
    "cycles",
    "market_snapshots",
    "agent_decisions",
    "simulated_orders",
    "simulated_fills",
    "positions",
    "ledger_entries",
    "portfolio_snapshots",
    "agent_memories",
    "system_events",
    "final_reports",
    "dashboard_states",
    "dashboard_updates",
    "llm_attempts",
    "analysis_sessions",
    "llm_meter",
    "scheduler_config",
    "scheduler_dispatches",
]


def restore(store, directory):
    directory = Path(directory)
    if store.demo:
        raise ValueError("Restore requires a separate PostgreSQL database")
    if store.db.execute("select count(*) from experiments").fetchone()[0]:
        raise ValueError("Restore target must be empty")
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    with store.db.transaction():
        for table in ORDER:
            path = directory / (table + ".csv")
            if not path.exists():
                continue
            with path.open("rb") as file, store.db.cursor() as cursor:
                with cursor.copy(
                    sql.SQL("copy {} from stdin with (format csv,header true)").format(
                        sql.Identifier(table)
                    )
                ) as copy:
                    while chunk := file.read(65536):
                        copy.write(chunk)
        restored = store.load(state["id"])
        if restored != state:
            raise RuntimeError("Restored state differs from exported state")
        for a in restored["agents"]:
            store.assert_wallet(
                state["id"], a["id"], Wallet.model_validate(a["wallet"])
            )
        # A restored backup cannot reuse an encrypted scheduler token implicitly.
        store.db.execute("update scheduler_config set enabled=false")
    return {
        "experiment_id": state["id"],
        "agents": len(state["agents"]),
        "financial_invariants": "verified",
        "scheduler_enabled": False,
    }
