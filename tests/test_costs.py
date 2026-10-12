from decimal import Decimal as D
from survival.costs import report


def test_eur_prices_count_cached_input_once_and_extrapolate_sessions():
    state = {"agents": [{"stats": {"llm_usage": {
        "requests": 4, "sessions": 1, "prompt_tokens": 1000000,
        "cached_prompt_tokens": 250000, "completion_tokens": 100000,
    }}}]}
    result = report(state)
    short = result["eur_scenarios"]["short_global"]
    assert D(short["measured_committed_cycles_eur"]) == D("2.2225")
    assert D(short["seven_day_extrapolation_current_504_sessions_eur"]) == D("2.2225") * 504
    assert result["metered_sessions"] == 1


def test_no_usage_has_no_weekly_forecast():
    result = report({"agents": [{"stats": {}}]})
    assert result["eur_scenarios"]["short_global"]["seven_day_extrapolation_current_504_sessions_eur"] is None
