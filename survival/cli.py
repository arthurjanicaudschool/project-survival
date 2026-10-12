import argparse
import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from .models import utcnow
from .store import Store
from .providers import Polymarket, AzureReasoner, reference_fx
from .fixtures import FixtureProvider, FixtureReasoner
from .runner import initialize, cycle, projection


def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    p = argparse.ArgumentParser(description="PROJECT SURVIVAL · paper trading only")
    p.add_argument(
        "command",
        choices=[
            "start",
            "cycle",
            "demo",
            "api-check",
            "export",
            "migrate",
            "quota-check",
        ],
    )
    p.add_argument("--experiment", default=os.getenv("EXPERIMENT_ID", "survival-001"))
    p.add_argument("--output", default="exports")
    p.add_argument("--cycle-id")
    args = p.parse_args()
    if args.command == "api-check":
        provider = Polymarket()
        try:
            markets = provider.collect()
            print(
                json.dumps(
                    {
                        "markets": len(markets),
                        "books": sum(len(m.books) for m in markets.values()),
                        "errors": provider.errors,
                    },
                    indent=2,
                )
            )
            if not any(m.books for m in markets.values()):
                raise RuntimeError(
                    "No executable public books; check provider availability"
                )
        finally:
            provider.close()
        return
    demo = args.command == "demo"
    store = Store(demo_path="data/demo.sqlite" if demo else None)
    try:
        if args.command == "migrate":
            sql = (
                Path(__file__).resolve().parent.parent
                / "supabase/migrations/001_initial.sql"
            ).read_text()
            store.db.execute(sql)
            print("Migration applied")
        elif args.command == "quota-check":
            print(json.dumps(store.quota_usage(), indent=2))
        elif args.command == "export":
            store.export(args.experiment, args.output)
            print(f"Exported to {args.output}")
        elif args.command == "start":
            state = initialize(store, args.experiment, "live", reference_fx())
            print(f"START {state['started_at']} → {state['end_at']}")
        elif demo:
            now = utcnow()
            eid = "demo-fixture"
            if not store.load(eid):
                initialize(
                    store,
                    eid,
                    "demo",
                    {
                        "usd_per_eur": "1.10",
                        "reference_date": now.date().isoformat(),
                        "fetched_at": now.isoformat(),
                        "source": "SYNTHETIC",
                        "method": "DEMO fixed synthetic rate",
                    },
                    now,
                )
            state = cycle(
                store, eid, FixtureProvider(now), FixtureReasoner(), args.cycle_id, now
            )
            target = Path("frontend/public/demo.json")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(projection(state)), encoding="utf-8")
            print(
                "DEMO cycle persisted to isolated SQLite and frontend/public/demo.json"
            )
        else:
            provider = Polymarket()
            try:
                # Lazy initialization permits valuation even when Azure is down.
                class LazyAzure:
                    def decide(self, *a):
                        return AzureReasoner().decide(*a)

                state = cycle(
                    store, args.experiment, provider, LazyAzure(), args.cycle_id
                )
                print(
                    json.dumps(
                        {
                            "status": state["status"],
                            "updated_at": state["updated_at"],
                            "cycles": len(state["cycles"]),
                        }
                    )
                )
            finally:
                provider.close()
    finally:
        store.close()


if __name__ == "__main__":
    main()
