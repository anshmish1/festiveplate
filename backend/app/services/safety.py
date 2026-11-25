"""Food-safety *screening* rules.

IMPORTANT: FestivePlate never certifies food as safe. These rules only decide
whether a listing is *eligible for matching* or must be *flagged for human
review*. Hold-time limits are conservative screening thresholds derived from
common food-handling guidance (e.g. cooked food should not sit at room
temperature for more than ~2 hours; hot-held food should stay at or above 60 °C).
The receiving NGO remains responsible for its own inspection at pickup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from .timegeo import utcnow

SAFETY_DISCLAIMER = (
    "Automated screening only - FestivePlate does not certify food as safe. "
    "The receiving organisation must inspect food at pickup and follow FSSAI food-handling guidance."
)

# Maximum hours between preparation and the pickup deadline, per storage condition.
MAX_HOLD_HOURS = {
    "ROOM_TEMPERATURE": 2.0,
    "HOT_HELD": 6.0,
    "REFRIGERATED": 24.0,
    "FROZEN": 72.0,
}

MIN_PICKUP_WINDOW_MINUTES = 30


@dataclass
class SafetyIssue:
    code: str
    severity: str  # BLOCKING | WARNING
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "message": self.message}


@dataclass
class SafetyResult:
    issues: List[SafetyIssue] = field(default_factory=list)

    @property
    def blocking(self) -> List[SafetyIssue]:
        return [i for i in self.issues if i.severity == "BLOCKING"]

    @property
    def result(self) -> str:
        return "FLAGGED" if self.blocking else "ELIGIBLE"


def screen(
    *,
    prepared_at: datetime,
    pickup_deadline: datetime,
    storage_condition: Optional[str],
    food_category: str,
    allergens: Optional[str],
    now: Optional[datetime] = None,
) -> SafetyResult:
    now = now or utcnow()
    res = SafetyResult()

    if prepared_at > now + timedelta(minutes=5):
        res.issues.append(SafetyIssue("PREPARED_IN_FUTURE", "BLOCKING", "Preparation time is in the future."))

    if pickup_deadline <= now:
        res.issues.append(SafetyIssue("DEADLINE_PASSED", "BLOCKING", "The pickup deadline has already passed."))
    elif pickup_deadline - now < timedelta(minutes=MIN_PICKUP_WINDOW_MINUTES):
        res.issues.append(
            SafetyIssue(
                "SHORT_PICKUP_WINDOW",
                "WARNING",
                f"Less than {MIN_PICKUP_WINDOW_MINUTES} minutes remain for pickup; collection may not be feasible.",
            )
        )

    if not storage_condition:
        res.issues.append(
            SafetyIssue("MISSING_STORAGE_INFO", "BLOCKING", "Storage condition was not provided; an admin must review.")
        )
    else:
        limit = MAX_HOLD_HOURS.get(storage_condition)
        if limit is None:
            res.issues.append(SafetyIssue("UNKNOWN_STORAGE", "BLOCKING", f"Unknown storage condition '{storage_condition}'."))
        else:
            hold = (pickup_deadline - prepared_at).total_seconds() / 3600
            elapsed = (now - prepared_at).total_seconds() / 3600
            label = storage_condition.replace("_", " ").lower()
            if elapsed > limit:
                res.issues.append(
                    SafetyIssue(
                        "HOLD_TIME_EXCEEDED",
                        "BLOCKING",
                        f"Food has been {label} for {elapsed:.1f} h, beyond the {limit:g} h screening limit.",
                    )
                )
            elif hold > limit:
                res.issues.append(
                    SafetyIssue(
                        "DEADLINE_BEYOND_SAFE_HOLD",
                        "BLOCKING",
                        f"Pickup deadline is {hold:.1f} h after preparation; the screening limit for {label} food is {limit:g} h.",
                    )
                )
            if storage_condition == "ROOM_TEMPERATURE" and food_category in ("NON_VEG", "EGG", "MIXED"):
                res.issues.append(
                    SafetyIssue(
                        "PERISHABLE_AT_ROOM_TEMP",
                        "WARNING",
                        "Non-vegetarian/egg dishes at room temperature are high-risk; prioritise fast pickup.",
                    )
                )

    if not allergens:
        res.issues.append(SafetyIssue("ALLERGENS_NOT_DECLARED", "WARNING", "Allergen information was not declared."))

    return res
