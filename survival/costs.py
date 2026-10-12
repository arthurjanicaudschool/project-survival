"""Report measured usage and explicit scenarios, never invented Azure prices."""
import os
import json
from pathlib import Path
from decimal import Decimal as D
from .agents import SETTINGS


def report(state):
    usage = [a["stats"].get("llm_usage", {}) for a in state["agents"]]
    totals = {k: sum(u.get(k, 0) for u in usage) for k in ("requests", "prompt_tokens", "completion_tokens", "cached_prompt_tokens")}
    input_rate = os.getenv("AZURE_INPUT_USD_PER_MILLION")
    output_rate = os.getenv("AZURE_OUTPUT_USD_PER_MILLION")
    price = None
    if input_rate and output_rate:
        # Conservative: do not assume a discount for cached input tokens.
        price = str((D(totals["prompt_tokens"]) * D(input_rate) + D(totals["completion_tokens"]) * D(output_rate)) / D(1000000))
    max_requests = SETTINGS["research_rounds"] + 1
    pricing = json.loads((Path(__file__).resolve().parent.parent / "config/azure_pricing_eur.json").read_text(encoding="utf-8"))
    sessions = sum(u.get("sessions", int(u.get("requests", 0) > 0)) for u in usage)
    cached = min(totals["prompt_tokens"], totals["cached_prompt_tokens"])
    euro = {}
    for offer, rates in pricing["per_million_tokens"].items():
        measured = ((D(totals["prompt_tokens"] - cached) * D(rates["input"]))
                    + D(cached) * D(rates["cached_input"])
                    + D(totals["completion_tokens"]) * D(rates["output"])) / D(1000000)
        euro[offer] = {"measured_committed_cycles_eur": str(measured),
            "seven_day_extrapolation_current_504_sessions_eur": str(measured / sessions * 504) if sessions else None,
            "seven_day_extrapolation_optional_924_sessions_eur": str(measured / sessions * 924) if sessions else None}
    return {"measured_since_v2": totals, "models": sorted({u["model"] for u in usage if u.get("model")}),
            "metered_sessions": sessions, "user_supplied_eur_rates": pricing,
            "eur_scenarios": euro,
            "eur_limitations": "Offer unknown; each row is conditional on that offer. Cached inputs use the supplied cache-read price. Cache-write tokens are not reported separately by the API: any separate cache-write charge is excluded and cannot be calculated. Seven-day figures extrapolate the measured sample at full session quotas, not a forecast or a ceiling. Historical and rolled-back cycles are excluded.",
            "estimated_measured_cost_usd": price,
            "price_status": "User-supplied USD rates, cached input billed at full rate" if price is not None else "USD rates not supplied; see conditional EUR offer scenarios",
            "historical_v1_tokens": "Not recorded; cannot reconstruct historical billing",
            "scenarios": [{"name": name, "dynamic_sessions_per_day": dynamic, "standard_sessions_per_day": standard,
                "all_agent_sessions_per_day": 4 * dynamic + 6 * standard,
                "sessions_per_week": 7 * (4 * dynamic + 6 * standard),
                "max_successful_completions_per_week": 7 * (4 * dynamic + 6 * standard) * rounds,
                "max_output_tokens_per_week": 7 * (4 * dynamic + 6 * standard) * rounds * SETTINGS["max_llm_tokens"]}
                for name, dynamic, standard, rounds in [("v1", 12, 4, 1), ("v2_current", 12, 4, max_requests), ("v2_more_frequent_not_enabled", 24, 6, max_requests)]],
            "limitations": "Upper bounds, not a forecast. Database totals cover committed cycles only; calls from a rolled-back cycle and some SDK retries may be absent. Consult LLM_USAGE in GitHub logs and Azure billing for complete charges. Input context, provider failures and token truncation affect actual usage. Session frequency is unchanged in v2. Web providers have no per-request commercial charge; quotas/availability still apply."}
