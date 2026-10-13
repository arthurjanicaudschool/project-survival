"""Report measured usage and explicit scenarios, never invented Azure prices."""

import os
import json
from pathlib import Path
from decimal import Decimal as D
from .agents import SETTINGS
from .agents import definitions


def report(state):
    usage = [a["stats"].get("llm_usage", {}) for a in state["agents"]]
    totals = {
        k: sum(u.get(k, 0) for u in usage)
        for k in (
            "requests",
            "prompt_tokens",
            "completion_tokens",
            "cached_prompt_tokens",
            "cache_write_prompt_tokens",
        )
    }
    input_rate = os.getenv("AZURE_INPUT_USD_PER_MILLION")
    output_rate = os.getenv("AZURE_OUTPUT_USD_PER_MILLION")
    price = None
    if input_rate and output_rate:
        # Conservative: do not assume a discount for cached input tokens.
        price = str(
            (
                D(totals["prompt_tokens"]) * D(input_rate)
                + D(totals["completion_tokens"]) * D(output_rate)
            )
            / D(1000000)
        )
    max_requests = SETTINGS["research_rounds"] + 1
    extra = (
        sum(
            a["risk"]["calls_per_day"]
            for a in definitions()
            if a["risk"].get("participation_required")
        )
        * 7
        * SETTINGS["participation"]["retry_calls"]
    )
    pricing = json.loads(
        (
            Path(__file__).resolve().parent.parent / "config/azure_pricing_eur.json"
        ).read_text(encoding="utf-8")
    )
    sessions = sum(u.get("sessions", int(u.get("requests", 0) > 0)) for u in usage)
    cached = min(totals["prompt_tokens"], totals["cached_prompt_tokens"])
    written = min(totals["prompt_tokens"] - cached, totals["cache_write_prompt_tokens"])
    euro = {}
    for offer, rates in pricing["per_million_tokens"].items():
        measured = (
            (D(totals["prompt_tokens"] - cached - written) * D(rates["input"]))
            + D(cached) * D(rates["cached_input"])
            + D(written) * D(rates["cache_write"])
            + D(totals["completion_tokens"]) * D(rates["output"])
        ) / D(1000000)
        euro[offer] = {
            "measured_committed_cycles_eur": str(measured),
            "seven_day_extrapolation_current_504_sessions_eur": str(
                measured / sessions * 504
            )
            if sessions
            else None,
            "seven_day_extrapolation_optional_924_sessions_eur": str(
                measured / sessions * 924
            )
            if sessions
            else None,
        }
    return {
        "measured_since_v2": totals,
        "models": sorted({u["model"] for u in usage if u.get("model")}),
        "v5_budget": state.get("health", {}).get("azure_budget"),
        "v5_request_bounds": {
            "normal_requests_per_session": SETTINGS["research_rounds"] + 1,
            "max_requests_with_repair_and_participation": SETTINGS["research_rounds"]
            + 2
            + SETTINGS["participation"]["retry_calls"],
            "max_output_tokens_per_session": (
                SETTINGS["research_rounds"]
                + 1
                + 2
                + SETTINGS["participation"]["retry_calls"]
            )
            * SETTINGS["max_llm_tokens"],
            "total_limit_eur": SETTINGS["analysis_budget_eur"],
            "daily_limit_eur": SETTINGS["analysis_daily_budget_eur"],
            "sdk_automatic_retries": 0,
            "method": "Each request reserves conservative estimated input/output cost before sending; measured usage replaces the reservation. Failures retain the reservation.",
        },
        "participation_correction_bounds": {
            "max_extra_completions_in_one_pending_session": SETTINGS["participation"][
                "retry_calls"
            ],
            "max_extra_completions_per_week_if_never_fulfilled": extra,
            "max_extra_output_tokens_per_week": extra * SETTINGS["max_llm_tokens"],
            "note": "Only the four participation agents, only before first investment, only if they omit BUY despite executable researched options. No increase to daily session quotas. Baseline scenarios below exclude this bounded correction.",
        },
        "metered_sessions": sessions,
        "user_supplied_eur_rates": pricing,
        "eur_scenarios": euro,
        "eur_limitations": "Offer unknown; each row is conditional. Cache reads and cache writes use the supplied rates when reported. Cache writes before v5 were not recorded. Seven-day extrapolation is a scenario, not a forecast. Committed-session usage excludes historical unmetered and failed requests; v5 budget reservations include uncertain requests conservatively.",
        "estimated_measured_cost_usd": price,
        "price_status": "User-supplied USD rates, cached input billed at full rate"
        if price is not None
        else "USD rates not supplied; see conditional EUR offer scenarios",
        "historical_v1_tokens": "Not recorded; cannot reconstruct historical billing",
        "scenarios": [
            {
                "name": name,
                "dynamic_sessions_per_day": dynamic,
                "standard_sessions_per_day": standard,
                "all_agent_sessions_per_day": 4 * dynamic + 6 * standard,
                "sessions_per_week": 7 * (4 * dynamic + 6 * standard),
                "max_successful_completions_per_week": 7
                * (4 * dynamic + 6 * standard)
                * rounds,
                "max_output_tokens_per_week": 7
                * (4 * dynamic + 6 * standard)
                * rounds
                * SETTINGS["max_llm_tokens"],
            }
            for name, dynamic, standard, rounds in [
                ("v1", 12, 4, 1),
                ("v2_current", 12, 4, max_requests),
                ("v2_more_frequent_not_enabled", 24, 6, max_requests),
            ]
        ],
        "limitations": "Upper bounds, not a forecast. Database totals cover committed cycles only; calls from a rolled-back cycle and some SDK retries may be absent. Consult LLM_USAGE in GitHub logs and Azure billing for complete charges. Input context, provider failures and token truncation affect actual usage. Session frequency is unchanged in v2. Web providers have no per-request commercial charge; quotas/availability still apply.",
    }
