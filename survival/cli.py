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
            "research-check",
            "health",
            "cost-report",
            "watchdog-install",
            "watchdog-activate",
            "watchdog-status",
        ],
    )
    p.add_argument("--experiment", default=os.getenv("EXPERIMENT_ID", "survival-001"))
    p.add_argument("--output", default="exports")
    p.add_argument("--cycle-id")
    args = p.parse_args()
    if args.command == "research-check":
        from .research import ResearchTools

        provider = Polymarket()
        try:
            tools = ResearchTools(provider)
            markets = {}
            search = tools.call("search_markets", {"query": "Bitcoin"}, markets)
            browse = tools.call("browse_markets", {"order": "liquidity"}, markets)
            pagination = (
                tools.call(
                    "browse_markets",
                    {"order": "liquidity", "cursor": browse["next_cursor"]},
                    markets,
                )
                if browse.get("next_cursor")
                else {"error": "No browsing cursor returned"}
            )
            results = search.get("markets", []) or browse.get("markets", [])
            inspected = (
                tools.call("get_market", {"reference": results[0]["id"]}, markets)
                if results
                else {"error": "No search result"}
            )
            news = tools.call("search_web", {"query": "Bitcoin"}, markets)
            # Verify at least one independent page read, not only a search index.
            page = tools.call(
                "read_web",
                {"url": "https://www.federalreserve.gov/monetarypolicy/fomc.htm"},
                markets,
            )
            primary = {
                topic: tools.call(
                    "get_public_data", {"topic": topic, "symbol": symbol}, markets
                )
                for topic, symbol in [
                    ("crypto", "BTC-USD"),
                    ("inflation", ""),
                    ("weather", ""),
                    ("social", "elonmusk"),
                ]
            }
            print(
                json.dumps(
                    {
                        "search": {
                            "ok": "error" not in search,
                            "markets": len(search.get("markets", [])),
                        },
                        "browse": {
                            "ok": "error" not in browse,
                            "markets": len(browse.get("markets", [])),
                        },
                        "pagination": {
                            "ok": "error" not in pagination,
                            "markets": len(pagination.get("markets", [])),
                            "error": pagination.get("error"),
                        },
                        "inspection": {
                            "ok": "error" not in inspected,
                            "error": inspected.get("error"),
                        },
                        "web_search": {
                            "ok": "error" not in news,
                            "articles": len(news.get("articles", [])),
                            "provider": news.get("provider"),
                            "errors": news.get("provider_errors"),
                        },
                        "web_read": {
                            "ok": "error" not in page,
                            "characters": len(page.get("excerpt", "")),
                            "error": page.get("error"),
                        },
                        "structured_primary_data": {
                            topic: {
                                "ok": "error" not in data,
                                "error": data.get("error"),
                                "url": data.get("url"),
                            }
                            for topic, data in primary.items()
                        },
                    },
                    indent=2,
                )
            )
            if any(
                "error" in result
                for result in (search, browse, pagination, inspected, news, page)
            ):
                raise RuntimeError(
                    "Research preflight incomplete; inspect provider/tool availability"
                )
        finally:
            provider.close()
        return
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
            if os.getenv("DATABASE_ADMIN_URL"):
                store.close()
                store = Store(os.environ["DATABASE_ADMIN_URL"])
            for migration in sorted(
                (Path(__file__).resolve().parent.parent / "supabase/migrations").glob(
                    "*.sql"
                )
            ):
                store.db.execute(migration.read_text(encoding="utf-8"))
            print("Migration applied")
        elif args.command.startswith("watchdog-"):
            if args.command != "watchdog-status" and os.getenv("DATABASE_ADMIN_URL"):
                store.close()
                store = Store(os.environ["DATABASE_ADMIN_URL"])
            from . import watchdog

            if args.command == "watchdog-install":
                result = watchdog.install(store, args.experiment)
            elif args.command == "watchdog-activate":
                import getpass

                token = os.getenv("SURVIVAL_SCHEDULER_GITHUB_TOKEN") or getpass.getpass(
                    "Dedicated fine-grained GitHub token (hidden): "
                )
                result = watchdog.activate(store, args.experiment, token.strip())
            else:
                result = watchdog.status(store, args.experiment)
            print(json.dumps(result, indent=2, default=str))
        elif args.command == "quota-check":
            print(json.dumps(store.quota_usage(), indent=2))
        elif args.command == "export":
            store.export(args.experiment, args.output)
            print(f"Exported to {args.output}")
        elif args.command in ("health", "cost-report"):
            state = store.load(args.experiment)
            if not state:
                raise ValueError("No experiment; explicit START required")
            if args.command == "cost-report":
                from .costs import report

                print(json.dumps(report(state), indent=2))
            else:
                from .health import assess

                print(
                    json.dumps(
                        {
                            "current_health": assess(state),
                            "status": state["status"],
                            "now_utc": utcnow().isoformat(),
                            "last_market_sync": state.get("last_market_sync"),
                            "health": state.get("health"),
                            "agents": [
                                {
                                    "id": a["id"],
                                    "runtime": a.get("runtime"),
                                    "last_analysis": a["memory"].get("last_call"),
                                    "last_decision": a["decisions"][-1]["action"]
                                    if a["decisions"]
                                    else None,
                                    "usage": a["stats"].get("llm_usage"),
                                }
                                for a in state["agents"]
                            ],
                        },
                        indent=2,
                    )
                )
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
            provider.store = store
            try:
                # Lazy initialization permits valuation even when Azure is down.
                class LazyAzure:
                    instance = None

                    def decide(self, *a):
                        if self.instance is None:
                            self.instance = AzureReasoner(provider)
                        return self.instance.decide(*a)

                    @property
                    def last_audit(self):
                        return self.instance.last_audit if self.instance else {}

                state = cycle(
                    store, args.experiment, provider, LazyAzure(), args.cycle_id
                )
                print(
                    json.dumps(
                        {
                            "status": state["status"],
                            "updated_at": state["updated_at"],
                            "cycles": len(state["cycles"]),
                            "health": state.get("health"),
                            "agents": [
                                {
                                    "id": a["id"],
                                    "runtime": a.get("runtime"),
                                    "usage": a["stats"].get("llm_usage"),
                                }
                                for a in state["agents"]
                            ],
                        }
                    )
                )
            finally:
                provider.close()
    finally:
        store.close()


if __name__ == "__main__":
    main()
