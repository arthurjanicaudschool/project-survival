"""Report measured usage and explicit scenarios, never invented Azure prices."""
import os
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
    return {"measured_since_v2": totals, "models": sorted({u["model"] for u in usage if u.get("model")}),
            "estimated_measured_cost_usd": price,
            "price_status": "User-supplied Azure rates, cached input billed at full rate" if price is not None else "Unknown: actual Azure deployment region/tier/rates not supplied",
            "historical_v1_tokens": "Not recorded; cannot reconstruct historical billing",
            "scenarios": [{"name": name, "dynamic_sessions_per_day": dynamic, "standard_sessions_per_day": standard,
                "all_agent_sessions_per_day": 4 * dynamic + 6 * standard,
                "sessions_per_week": 7 * (4 * dynamic + 6 * standard),
                "max_successful_completions_per_week": 7 * (4 * dynamic + 6 * standard) * rounds,
                "max_output_tokens_per_week": 7 * (4 * dynamic + 6 * standard) * rounds * SETTINGS["max_llm_tokens"]}
                for name, dynamic, standard, rounds in [("v1", 12, 4, 1), ("v2_current", 12, 4, max_requests), ("v2_more_frequent_not_enabled", 24, 6, max_requests)]],
            "limitations": "Upper bounds, not a forecast. Database totals cover committed cycles only; calls from a rolled-back cycle and some SDK retries may be absent. Consult LLM_USAGE in GitHub logs and Azure billing for complete charges. Input context, provider failures and token truncation affect actual usage. Session frequency is unchanged in v2. Web providers have no per-request commercial charge; quotas/availability still apply."}
