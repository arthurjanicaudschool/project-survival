"""Observable features and portfolio diagnostics, never invented forecasts."""

from decimal import Decimal as D
from math import sqrt, log
from statistics import pstdev, NormalDist, correlation
import re
from .models import ZERO

CATEGORIES = {
    "Crypto": ("bitcoin", "ethereum", "btc", "crypto", "solana"),
    "Economics": (
        "fed ",
        "federal reserve",
        "ecb",
        "inflation",
        "cpi",
        "recession",
        "rates",
    ),
    "Politics": ("election", "trump", "democrat", "republican", "shutdown", "powell"),
    "Sports": ("nba", "nfl", "mlb", "win the", "championship", " vs "),
    "Weather": ("hurricane", "temperature", "rain", "weather"),
    "Tech": ("gemini", "openai", "model", "spacex", "starship", "google", "ipo"),
    "Culture": ("elon musk", "tweet", "post "),
}


def classify(question, supplied=None):
    if supplied and supplied != "Unclassified":
        return supplied, "provider"
    q = question.lower()
    for category, terms in CATEGORIES.items():
        if any(t in q for t in terms):
            return category, "inferred from question; not provider taxonomy"
    return "Other", "inferred fallback"


def features(market):
    result = {}
    for outcome, b in market.books.items():
        bid = max((l.price for l in b.bids), default=None)
        ask = min((l.price for l in b.asks), default=None)
        rows = market.history.get(outcome, [])
        prices = [float(r["price"]) for r in rows if r.get("price") is not None]
        returns = [log(y / x) for x, y in zip(prices, prices[1:]) if x > 0 and y > 0]
        result[outcome] = {
            "bid": str(bid) if bid is not None else None,
            "ask": str(ask) if ask is not None else None,
            "spread": str(ask - bid) if ask is not None and bid is not None else None,
            "minimum_entry_cost": str(
                b.minimum * (ask + b.fee_rate * (ask * (1 - ask)) ** b.fee_exponent)
            )
            if ask is not None
            else None,
            "minimum_quantity": str(b.minimum),
            "observed_at": b.observed_at.isoformat(),
            "momentum_absolute": str(D(str(prices[-1])) - D(str(prices[0])))
            if len(prices) > 1
            else None,
            "recent_change": str(D(str(prices[-1])) - D(str(prices[-2])))
            if len(prices) > 1
            else None,
            "log_return_volatility_per_observation": pstdev(returns)
            if len(returns) > 1
            else None,
            "observations": len(prices),
            "history_start": rows[0].get("timestamp") if rows else None,
            "history_end": rows[-1].get("timestamp") if rows else None,
            "bid_depth_quantity": str(sum((l.size for l in b.bids), ZERO)),
            "ask_depth_quantity": str(sum((l.size for l in b.asks), ZERO)),
            "limitation": "Observed market features, not a settlement probability or forecast; sampling intervals may differ.",
        }
    return result


def risk_exposure(wallet, markets):
    categories = {}
    factors = {}
    for p in wallet.positions.values():
        if p.quantity <= 0:
            continue
        m = markets.get(p.market_id)
        q = m.question.lower() if m else ""
        c = m.category if m else "Unknown"
        categories[c] = str(D(categories.get(c, "0")) + p.cost)
        factor = next(
            (
                v
                for k, v in [
                    ("bitcoin", "Bitcoin"),
                    ("ethereum", "Ethereum"),
                    ("fed ", "US rates"),
                    ("gemini", "Google AI"),
                    ("elon", "Elon activity"),
                ]
                if k in q
            ),
            c,
        )
        factors[factor] = str(D(factors.get(factor, "0")) + p.cost)
    series = {}
    for p in wallet.positions.values():
        m = markets.get(p.market_id)
        if p.quantity <= 0 or not m:
            continue
        rows = sorted(
            m.history.get(p.outcome, []), key=lambda r: str(r.get("timestamp", ""))
        )
        series[p.market_id + ":" + p.outcome] = {
            str(y["timestamp"]): float(y["price"]) - float(x["price"])
            for x, y in zip(rows, rows[1:])
            if "timestamp" in x and "timestamp" in y and "price" in x and "price" in y
        }
    pairs = []
    keys = list(series)
    for i, left in enumerate(keys):
        for right in keys[i + 1 :]:
            shared = sorted(set(series[left]) & set(series[right]))
            x = [series[left][t] for t in shared]
            y = [series[right][t] for t in shared]
            measured = (
                correlation(x, y)
                if len(shared) >= 6 and pstdev(x) > 0 and pstdev(y) > 0
                else None
            )
            pairs.append(
                {
                    "left": left,
                    "right": right,
                    "matched_samples": len(shared),
                    "observed_price_change_correlation": measured,
                }
            )
    return {
        "category_cost": categories,
        "economic_factor_cost": factors,
        "sampled_correlations": pairs,
        "method": "Economic-topic exposure plus correlations of observed price changes on matching timestamps (minimum 6). Short sample, not a stable dependency estimate or settlement correlation.",
    }


def diversity(agents):
    choices = {
        a["id"]: {
            d["market_id"]
            for d in a["decisions"]
            if d["action"] in ("BUY", "SELL") and d["market_id"]
        }
        for a in agents
    }
    pairs = []
    for i, a in enumerate(agents):
        for b in agents[i + 1 :]:
            union = choices[a["id"]] | choices[b["id"]]
            if union:
                pairs.append(len(choices[a["id"]] & choices[b["id"]]) / len(union))
    return {
        "unique_traded_markets": len(set().union(*choices.values())),
        "agents_with_trades": sum(bool(s) for s in choices.values()),
        "mean_pairwise_market_overlap": sum(pairs) / len(pairs) if pairs else None,
        "window": "Recent 40 decisions per agent; includes exploration. Describes market overlap, not independent intelligence or skill.",
    }


def performance(history, aid):
    valid = lambda p: (
        aid in p
        and p[aid].get("roi") is not None
        and (p[aid].get("complete") is True or not p[aid].get("stranded"))
        and p[aid].get("complete") is not False
    )
    rows = [p[aid] for p in history if valid(p)]
    returns = [
        float(y[aid]["roi"]) - float(x[aid]["roi"])
        for x, y in zip(history, history[1:])
        if valid(x) and valid(y)
    ]
    return {
        "valid_samples": len(rows),
        "incomplete_samples": sum(not valid(p) for p in history),
        "return_change_volatility": pstdev(returns) if len(returns) > 1 else None,
        "method": "Unannualized changes in sampled portfolio return. Not a Sharpe ratio or proof of future profitability.",
    }


def observed_drawdown(agent, history, current_nav, fx):
    peak = D(agent["wallet"]["initial"])
    worst = ZERO
    values = [
        D(p[agent["id"]]["nav_eur"]) * fx
        for p in history
        if isinstance(p.get(agent["id"]), dict)
        and p[agent["id"]].get("nav_eur") is not None
        and (
            p[agent["id"]].get("complete") is True or not p[agent["id"]].get("stranded")
        )
        and p[agent["id"]].get("complete") is not False
    ]
    if current_nav is not None:
        values.append(current_nav)
    for nav in values:
        peak = max(peak, nav)
        worst = max(worst, 1 - nav / peak)
    agent["stats"].update(peak=str(peak), max_drawdown=str(worst))


def threshold_scenarios(data, markets, now):
    if "latest_close" not in data or not data.get("five_minute_log_volatility"):
        return []
    scenarios = []
    spot = float(data["latest_close"])
    sigma = data["five_minute_log_volatility"]
    for m in markets.values():
        match = re.search(r"above\s+\$([\d,]+)", m.question, re.I)
        subject = (
            "bitcoin"
            if data.get("symbol") == "BTC-USD"
            else "ethereum"
            if data.get("symbol") == "ETH-USD"
            else "solana"
        )
        if not match or subject not in m.question.lower() or not m.end_at:
            continue
        steps = (m.end_at - now).total_seconds() / 300
        if steps <= 0:
            continue
        strike = float(match.group(1).replace(",", ""))
        probability = NormalDist().cdf(
            (log(spot / strike) - 0.5 * sigma * sigma * steps) / (sigma * sqrt(steps))
        )
        scenarios.append(
            {
                "market_id": m.id,
                "scenario_yes_probability": probability,
                "strike": strike,
                "method": "Illustrative zero-drift lognormal scenario using observed five-minute volatility. Coinbase is a proxy; metadata deadline may differ from exact rule. No calibrated forecast or positive edge claim.",
            }
        )
    return scenarios
