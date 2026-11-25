"""Turn a (translated-to-English) voice transcript into a *draft* donation record.

The result is always a draft: the donor must review and confirm every field
before the listing can be published. Missing values stay missing - they are
never guessed.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .timegeo import to_naive_utc, utcnow

# Approximate centroids of Bengaluru localities (used only to pre-fill the map pin;
# donors confirm the exact pickup point).
BENGALURU_AREAS: Dict[str, Tuple[float, float]] = {
    "electronic city": (12.8452, 77.6602),
    "hsr layout": (12.9116, 77.6474),
    "koramangala": (12.9352, 77.6245),
    "bommanahalli": (12.9034, 77.6239),
    "begur": (12.8763, 77.6363),
    "btm layout": (12.9166, 77.6101),
    "jayanagar": (12.9250, 77.5938),
    "jp nagar": (12.9077, 77.5851),
    "indiranagar": (12.9719, 77.6412),
    "whitefield": (12.9698, 77.7500),
    "marathahalli": (12.9592, 77.6974),
    "hebbal": (13.0358, 77.5970),
    "yelahanka": (13.1007, 77.5963),
    "malleshwaram": (13.0031, 77.5643),
    "rajajinagar": (12.9915, 77.5560),
    "basavanagudi": (12.9406, 77.5738),
    "banashankari": (12.9255, 77.5468),
    "bellandur": (12.9304, 77.6784),
    "sarjapur": (12.8603, 77.7860),
    "majestic": (12.9767, 77.5713),
    "mg road": (12.9756, 77.6050),
    "hosur road": (12.8890, 77.6390),
}

_ACRONYMS = {"hsr": "HSR", "btm": "BTM", "jp": "JP", "mg": "MG"}


def display_area(key: str) -> str:
    return " ".join(_ACRONYMS.get(w, w.capitalize()) for w in key.split())


_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "half": 0.5, "an": 1, "a": 1,
}
_NUMBER_WORD_RE = r"(?:\d+(?:\.\d+)?|(?:(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|and|a|an|half)[\s-]*)+)"


def words_to_number(text: str) -> Optional[float]:
    text = text.strip().lower()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    total, current, seen = 0.0, 0.0, False
    for tok in re.split(r"[\s-]+", text):
        if tok == "and" or not tok:
            continue
        if tok == "hundred":
            current = (current or 1) * 100
            seen = True
        elif tok == "thousand":
            total += (current or 1) * 1000
            current, seen = 0, True
        elif tok in _UNITS:
            current += _UNITS[tok]
            seen = True
        else:
            return None
    return (total + current) if seen else None


DISH_KEYWORDS = [
    "bisi bele bath", "curd rice", "lemon rice", "veg pulao", "pulao", "biryani", "fried rice", "rice", "sambar",
    "rasam", "dal", "palya", "chapati", "roti", "puri", "paneer", "curry", "payasa", "kheer", "sweets", "jamun",
    "idli", "dosa", "vada", "upma", "chicken", "mutton", "fish", "egg",
]


def _find_category(t: str) -> Optional[str]:
    non_veg = bool(re.search(r"non[\s-]?veg|chicken|mutton|fish|meat|prawn", t))
    egg = bool(re.search(r"\begg", t))
    veg = bool(re.search(r"\bveg(etarian)?\b|\bvegetarian\b|\bsasyahari\b", t)) and not re.search(
        r"non[\s-]?veg(etarian)?", t.replace("non vegetarian", "non-veg").replace("non-vegetarian", "non-veg")
    )
    if non_veg and (veg or egg):
        return "MIXED"
    if non_veg:
        return "NON_VEG"
    if egg and not veg:
        return "EGG"
    if veg:
        return "VEG"
    return None


def _find_storage(t: str) -> Optional[str]:
    if re.search(r"refrigerat|fridge|chilled|cold storage", t):
        return "REFRIGERATED"
    if re.search(r"frozen|freezer", t):
        return "FROZEN"
    if re.search(r"room temperature|kept outside|open air|normal temperature", t):
        return "ROOM_TEMPERATURE"
    if re.search(r"\bhot\b|warm|hot case|chafing|kept heated|being kept hot", t):
        return "HOT_HELD"
    return None


_PORTION_RE = re.compile(
    r"(" + _NUMBER_WORD_RE + r")\s*(?:vegetarian\s+|veg\s+|non[\s-]?veg(?:etarian)?\s+)?"
    r"(?:meal|portion|plate|serving|people|packet|box)"
)


def _find_portions(t: str) -> Optional[int]:
    for m in _PORTION_RE.finditer(t):
        n = words_to_number(m.group(1))
        if n and n >= 1:
            return int(n)
    return None


def _parse_clock(s: str) -> Optional[Tuple[int, int]]:
    s = s.strip().lower().replace(".", "")
    if s in ("midnight",):
        return (0, 0)
    if s in ("noon",):
        return (12, 0)
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", s)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return (h, mi)


def _most_recent_ist(h: int, mi: int, now_utc: datetime) -> datetime:
    local_now = now_utc + timedelta(hours=5, minutes=30)
    cand = local_now.replace(hour=h, minute=mi, second=0, microsecond=0)
    if cand > local_now + timedelta(minutes=5):
        cand -= timedelta(days=1)
    return cand - timedelta(hours=5, minutes=30)


def _next_after(h: int, mi: int, after_utc: datetime) -> datetime:
    local_after = after_utc + timedelta(hours=5, minutes=30)
    cand = local_after.replace(hour=h, minute=mi, second=0, microsecond=0)
    if cand <= local_after:
        cand += timedelta(days=1)
    return cand - timedelta(hours=5, minutes=30)


CLOCK_RE = r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}:\d{2}|midnight|noon)"


def rule_based_extract(text: str) -> Dict[str, Any]:
    t = " " + text.lower().replace("\n", " ") + " "
    out: Dict[str, Any] = {}
    out["food_category"] = _find_category(t)
    out["storage_condition"] = _find_storage(t)
    out["portions"] = _find_portions(t)

    dishes = [d for d in DISH_KEYWORDS if re.search(r"\b" + re.escape(d) + r"\b", t)]
    # drop substrings already covered by a longer dish ("rice" inside "curd rice")
    dishes = [d for d in dishes if not any(d != o and d in o for o in dishes)]
    out["food_type"] = ", ".join(dishes) if dishes else None

    m = re.search(r"(?:prepared|cooked|made)\s+(?:about\s+)?(" + _NUMBER_WORD_RE + r")\s*(hour|hr|minute|min)s?\s+ago", t)
    if m:
        n = words_to_number(m.group(1))
        if n is not None:
            out["prepared_hours_ago"] = n / 60 if m.group(2).startswith("min") else n
    m = re.search(r"(?:prepared|cooked|made)\s+(?:at|around|by)\s+" + CLOCK_RE, t)
    if m:
        out["prepared_at_local_time"] = m.group(1)

    m = re.search(r"within\s+(?:the\s+next\s+)?(" + _NUMBER_WORD_RE + r")\s*(hour|hr|minute|min)s?", t)
    if m:
        n = words_to_number(m.group(1))
        if n is not None:
            out["pickup_within_hours"] = n / 60 if m.group(2).startswith("min") else n
    m = re.search(r"(?:before|by|until|till)\s+" + CLOCK_RE, t)
    if m:
        out["pickup_deadline_local_time"] = m.group(1)

    for area in sorted(BENGALURU_AREAS, key=len, reverse=True):
        if area in t:
            out["location"] = display_area(area)
            break
    return out


def _clean(v: Any) -> Any:
    if isinstance(v, str) and v.strip().lower() in ("", "null", "none", "unknown", "n/a"):
        return None
    return v


def build_draft(raw: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Normalise raw extracted values (from LLM or rules) into listing draft fields."""
    now = now or utcnow()
    raw = {k: _clean(v) for k, v in raw.items()}
    draft: Dict[str, Any] = {}
    notes: List[str] = []

    cat = raw.get("food_category")
    draft["food_category"] = cat if cat in ("VEG", "NON_VEG", "EGG", "MIXED") else None
    st = raw.get("storage_condition")
    draft["storage_condition"] = st if st in ("HOT_HELD", "REFRIGERATED", "ROOM_TEMPERATURE", "FROZEN") else None
    try:
        portions = int(raw["portions"]) if raw.get("portions") is not None else None
        draft["portions_reported"] = portions if portions and portions > 0 else None
    except (TypeError, ValueError):
        draft["portions_reported"] = None
    draft["food_type"] = raw.get("food_type")
    draft["allergens"] = raw.get("allergens")

    prepared: Optional[datetime] = None
    try:
        if raw.get("prepared_hours_ago") is not None:
            prepared = now - timedelta(hours=float(raw["prepared_hours_ago"]))
            notes.append(f"Preparation time computed as {raw['prepared_hours_ago']} h before the report.")
    except (TypeError, ValueError):
        pass
    if prepared is None and raw.get("prepared_at_local_time"):
        hm = _parse_clock(str(raw["prepared_at_local_time"]))
        if hm:
            prepared = _most_recent_ist(hm[0], hm[1], now)
    draft["prepared_at"] = prepared

    deadline: Optional[datetime] = None
    try:
        if raw.get("pickup_within_hours") is not None:
            deadline = now + timedelta(hours=float(raw["pickup_within_hours"]))
            notes.append(f"Pickup deadline computed as {raw['pickup_within_hours']} h after the report.")
    except (TypeError, ValueError):
        pass
    if deadline is None and raw.get("pickup_deadline_local_time"):
        hm = _parse_clock(str(raw["pickup_deadline_local_time"]))
        if hm:
            deadline = _next_after(hm[0], hm[1], prepared or now)
    draft["pickup_deadline"] = deadline

    loc = raw.get("location")
    draft["area"] = loc
    if loc and loc.lower() in BENGALURU_AREAS:
        lat, lng = BENGALURU_AREAS[loc.lower()]
        draft["latitude"], draft["longitude"] = lat, lng
        notes.append(f"Map pin pre-filled at the approximate centre of {loc}; please drag it to the exact pickup point.")
    else:
        draft["latitude"] = draft["longitude"] = None

    venue = raw.get("venue_name")
    if venue:
        draft["title"] = f"Surplus food from {venue}"
    elif draft.get("food_type"):
        draft["title"] = f"Surplus {draft['food_type']}"
    else:
        draft["title"] = None

    required = ["food_type", "food_category", "portions_reported", "prepared_at", "pickup_deadline", "storage_condition", "area"]
    missing = [k for k in required if not draft.get(k)]
    return {"draft": draft, "missing_fields": missing, "notes": notes}


def to_utc_or_none(dt: Optional[datetime]) -> Optional[datetime]:
    return to_naive_utc(dt) if dt else None
