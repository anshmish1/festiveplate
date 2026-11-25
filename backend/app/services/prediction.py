"""Surplus *prediction* for events.

Output is always labelled as a prediction / estimate - never as a measurement of
actual waste. When the donor supplies their own historical consumption data it is
used; otherwise transparent baseline assumptions are used and listed.
"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional

PREDICTION_LABEL = "PREDICTION - estimated potential surplus, not a measurement of actual food waste"

# Baseline assumptions (documented, adjustable). show_up = fraction of expected guests who attend.
BASELINES: Dict[str, Dict[str, float]] = {
    "WEDDING": {"show_up": 0.85, "servings_per_guest": 1.0},
    "CORPORATE": {"show_up": 0.80, "servings_per_guest": 0.95},
    "FESTIVAL": {"show_up": 0.90, "servings_per_guest": 1.0},
    "RESTAURANT_DAY": {"show_up": 0.90, "servings_per_guest": 1.0},
    "OTHER": {"show_up": 0.85, "servings_per_guest": 1.0},
}


def predict_surplus(
    *,
    event_type: str,
    planned_servings: int,
    expected_attendance: int,
    actual_attendance: Optional[int] = None,
    historical: Optional[List[Dict[str, int]]] = None,
) -> Dict:
    base = BASELINES.get(event_type, BASELINES["OTHER"])
    assumptions: List[str] = []
    history = [h for h in (historical or []) if h.get("planned_servings", 0) > 0 and h.get("consumed_servings", -1) >= 0]

    if history:
        rates = [min(1.0, h["consumed_servings"] / h["planned_servings"]) for h in history]
        rate = statistics.mean(rates)
        spread = statistics.pstdev(rates) if len(rates) > 1 else 0.10
        if actual_attendance is not None and expected_attendance > 0:
            # Adjust for today's turnout relative to the plan.
            rate *= min(1.2, actual_attendance / expected_attendance)
            assumptions.append(f"Adjusted for actual attendance {actual_attendance} vs expected {expected_attendance}.")
        rate = min(1.0, rate)
        consumed = planned_servings * rate
        method = "historical_consumption"
        assumptions.insert(0, f"Average consumption rate {rate:.0%} from {len(history)} past event(s) you supplied.")
    else:
        attendance = actual_attendance if actual_attendance is not None else expected_attendance * base["show_up"]
        if actual_attendance is None:
            assumptions.append(f"Baseline assumption: {base['show_up']:.0%} of expected guests attend ({event_type.lower()}).")
        else:
            assumptions.append(f"Using actual attendance of {actual_attendance}.")
        assumptions.append(f"Baseline assumption: {base['servings_per_guest']:g} serving(s) per guest.")
        consumed = min(planned_servings, attendance * base["servings_per_guest"])
        spread = 0.10
        method = "baseline_assumptions"

    surplus = max(0.0, planned_servings - consumed)
    margin = planned_servings * spread
    low, high = max(0, round(surplus - margin)), min(planned_servings, round(surplus + margin))
    return {
        "label": PREDICTION_LABEL,
        "is_prediction": True,
        "method": method,
        "predicted_surplus_portions": round(surplus),
        "range_low": low,
        "range_high": high,
        "planned_servings": planned_servings,
        "assumptions": assumptions,
        "advice": (
            "If this surplus materialises, list it on FestivePlate as soon as service ends so NGOs have time to collect."
            if surplus >= 10
            else "Little surplus expected."
        ),
    }
