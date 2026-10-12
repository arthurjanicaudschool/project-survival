"""Read-only providers. Only the unified PublicClient is imported."""

import json
import logging
import os
import time
from datetime import timedelta
from decimal import Decimal as D
import httpx
from polymarket import PublicClient
from .models import Book, Level, Market, Decision, utcnow
from .agents import SETTINGS

log = logging.getLogger(__name__)


def retry(fn):
    for attempt in range(3):
        try:
            return fn()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2**attempt)


class Polymarket:
    def __init__(self):
        self.client = PublicClient()
        self.errors = []

    def close(self):
        self.client.close()

    def refresh(self, market, outcome):
        old = market.books[outcome]
        b = retry(lambda: self.client.get_order_book(asset_id=old.asset_id))
        if not b.timestamp:
            raise ValueError("Missing book timestamp")
        market.books[outcome] = Book(
            asset_id=old.asset_id,
            observed_at=b.timestamp,
            bids=[
                Level(price=l.price, size=l.size)
                for l in sorted(b.bids, key=lambda l: l.price, reverse=True)[
                    : SETTINGS["book_depth_levels"]
                ]
                if 0 < l.price < 1 and l.size > 0
            ],
            asks=[
                Level(price=l.price, size=l.size)
                for l in sorted(b.asks, key=lambda l: l.price)[
                    : SETTINGS["book_depth_levels"]
                ]
                if 0 < l.price < 1 and l.size > 0
            ],
            minimum=b.min_order_size,
            tick=b.tick_size,
            fee_rate=old.fee_rate,
            fee_exponent=old.fee_exponent,
            evidence=b.hash,
        )

    def collect(self, held_ids=()):
        self.errors = []
        now = utcnow()
        discovered = retry(
            lambda: self.client.list_markets(
                closed=False,
                order="volume24hr",
                ascending=False,
                liquidity_num_min=float(SETTINGS["min_liquidity"]),
                page_size=SETTINGS["discovery_limit"],
            ).first_page()
        ).items
        candidates = [
            m
            for m in discovered
            if m.state.active
            and m.state.accepting_orders
            and m.state.end_date
            and now < m.state.end_date < now + timedelta(days=8)
        ][: SETTINGS["max_markets"]]
        raw = {str(m.id): m for m in candidates}
        for mid in held_ids:
            if mid not in raw:
                try:
                    raw[mid] = retry(lambda: self.client.get_market(id=mid))
                except Exception as exc:
                    self.errors.append(f"Market {mid}: {type(exc).__name__}")
        markets = {}
        for mid, m in raw.items():
            try:
                markets[mid] = self.normalize(m)
            except Exception as exc:
                self.errors.append(
                    f"Market {mid}: {type(exc).__name__}: {str(exc)[:180]}"
                )
        return markets

    def normalize(self, m):
        version = m.version
        if version not in ("v1", "v2"):
            raise ValueError(f"Unsupported protocol {version}")
        assets = {}
        for name, o in (("YES", m.outcomes.yes), ("NO", m.outcomes.no)):
            aid = o.position_id if version == "v2" else o.token_id
            if aid is None:
                raise ValueError("Missing outcome identifier")
            assets[name] = str(aid)
        market = Market(
            id=str(m.id),
            slug=m.slug or "",
            url=f"https://polymarket.com/event/{m.events[0].slug if m.events and m.events[0].slug else m.slug}",
            question=m.question or "",
            description=m.description or "",
            resolution_source=m.resolution.source or "",
            condition_id=str(m.condition_id) if m.condition_id else None,
            version=version,
            group=str(m.events[0].id) if m.events else str(m.id),
            category=m.category
            or (m.tags[0].label if m.tags else "Unclassified")
            or "Unclassified",
            end_at=m.state.end_date,
            active=bool(
                m.state.active and not m.state.closed and m.state.accepting_orders
            ),
            liquidity=m.metrics.liquidity or D(0),
            volume=m.metrics.volume_24hr or D(0),
            assets=assets,
        )
        if m.state.closed or str(m.resolution.uma_resolution_status) == "resolved":
            rows = (
                retry(
                    lambda: self.client.get_resolutions(
                        question_id=m.resolution.question_id
                    )
                )
                if m.resolution.question_id
                else ()
            )
            for row in rows:
                if (
                    row.payouts
                    and row.resolved_at
                    and (
                        not row.condition_id
                        or str(row.condition_id) == market.condition_id
                    )
                ):
                    if sum(row.payouts) == 1 and all(0 <= p <= 1 for p in row.payouts):
                        market.resolved = True
                        market.payouts = {"YES": row.payouts[0], "NO": row.payouts[1]}
                        return market
        trading = m.trading
        if trading.fees_enabled is False:
            rate, exponent = D(0), D(1)
        elif trading.fees_enabled is True and trading.fee_schedule:
            rate, exponent = (
                trading.fee_schedule.rate,
                D(str(trading.fee_schedule.exponent)),
            )
        else:
            raise ValueError("Unknown fee configuration; trading suspended")
        # Delayed sports orders require a second observation at matching time.
        # Excluded until a delayed-order observer is provided.
        if trading.seconds_delay:
            market.active = False
        for outcome, aid in assets.items():
            try:
                b = retry(lambda: self.client.get_order_book(asset_id=aid))
                if not b.timestamp:
                    raise ValueError("Book without provider timestamp")
                market.books[outcome] = Book(
                    asset_id=aid,
                    observed_at=b.timestamp,
                    bids=[
                        Level(price=l.price, size=l.size)
                        for l in sorted(b.bids, key=lambda l: l.price, reverse=True)[
                            : SETTINGS["book_depth_levels"]
                        ]
                        if 0 < l.price < 1 and l.size > 0
                    ],
                    asks=[
                        Level(price=l.price, size=l.size)
                        for l in sorted(b.asks, key=lambda l: l.price)[
                            : SETTINGS["book_depth_levels"]
                        ]
                        if 0 < l.price < 1 and l.size > 0
                    ],
                    minimum=b.min_order_size,
                    tick=b.tick_size,
                    fee_rate=rate,
                    fee_exponent=exponent,
                    evidence=b.hash,
                )
                time.sleep(0.12)
                history = retry(
                    lambda: self.client.list_price_history(
                        asset_id=aid,
                        start=utcnow() - timedelta(days=2),
                        end=utcnow(),
                        bucket_seconds=14400,
                        page_size=16,
                    ).first_page()
                )
                market.history[outcome] = [
                    p.model_dump(mode="json") for p in history.items
                ]
            except Exception as exc:
                self.errors.append(f"Outcome {aid}: {type(exc).__name__}")
        return market


def reference_fx():
    # ECB daily reference via Frankfurter. USD is a reference proxy for pUSD,
    # not an assertion of token redemption or an executable FX conversion.
    with httpx.Client(timeout=20) as c:
        r = retry(
            lambda: c.get(
                "https://api.frankfurter.dev/v1/latest",
                params={"base": "EUR", "symbols": "USD"},
            )
        )
        r.raise_for_status()
        data = r.json()
    rate = D(str(data["rates"]["USD"]))
    from datetime import date

    age = (utcnow().date() - date.fromisoformat(data["date"])).days
    if rate <= 0 or age < 0 or age > 5:
        raise ValueError("Invalid or stale EUR/USD reference")
    return {
        "usd_per_eur": str(rate),
        "reference_date": data["date"],
        "fetched_at": utcnow().isoformat(),
        "source": "https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD",
        "method": "Frozen ECB EUR/USD reference; fictional 1 pUSD = 1 reference USD. No FX trading or token peg gain included.",
    }


class AzureReasoner:
    def __init__(self):
        from openai import AzureOpenAI

        self.client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            timeout=45,
            max_retries=2,
        )

    def decide(self, agent, wallet, markets, memory):
        sources = [
            m.url or f"https://polymarket.com/event/{m.slug}" for m in markets.values()
        ]
        sources += [
            m.resolution_source
            for m in markets.values()
            if m.resolution_source.startswith("https://")
        ]
        selected = sorted(
            markets.values(),
            key=lambda m: (
                not any(
                    p.market_id == m.id and p.quantity > 0
                    for p in wallet.positions.values()
                ),
                m.end_at or utcnow(),
            ),
        )[: SETTINGS["markets_per_agent"]]
        evidence = []
        for m in selected:
            item = m.model_dump(mode="json")
            for b in item["books"].values():
                b["asks"] = sorted(b["asks"], key=lambda l: D(l["price"]))[
                    : SETTINGS["book_depth_levels"]
                ]
                b["bids"] = sorted(
                    b["bids"], key=lambda l: D(l["price"]), reverse=True
                )[: SETTINGS["book_depth_levels"]]
            evidence.append(item)
        payload = {
            "portfolio": wallet.model_dump(mode="json"),
            "memory": memory,
            "risk": agent["risk"],
            "markets": evidence,
            "allowed_sources": sources,
            "schema": Decision.model_json_schema(),
            "external_news": "No verified external news provider configured; do not invent current events.",
        }
        response = self.client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            messages=[
                {"role": "system", "content": agent["prompt"]},
                {"role": "user", "content": json.dumps(payload)},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=SETTINGS["max_llm_tokens"],
        )
        d = Decision.model_validate_json(response.choices[0].message.content or "")
        if d.agent_id != agent["id"] or any(url not in sources for url in d.sources):
            raise ValueError("Invalid agent identity or unsupported source")
        return d
