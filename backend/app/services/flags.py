"""Feature flags backed by Flagsmith (REST API), with local admin overrides and safe defaults.

Resolution order for each flag:
  1. Local admin override stored in `feature_flag_overrides` (explicitly labelled "local_override").
  2. Flagsmith environment flags, if FLAGSMITH_ENVIRONMENT_KEY is set and the last fetch succeeded.
  3. Safe default compiled into the app (labelled "default").

The connection state reported to the admin UI is the *real* result of the last
Flagsmith request - it is never reported as connected unless a request succeeded.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import FeatureFlagOverride

log = logging.getLogger("festiveplate.flags")

FLAG_DEFINITIONS: Dict[str, Dict] = {
    "voice_reporting": {"default": True, "description": "Sarvam AI multilingual voice donation reporting"},
    "surplus_prediction": {"default": True, "description": "Predict potential surplus portions for events"},
    "emergency_matching": {
        "default": False,
        "description": "Widen NGO search radius for listings with less than 2 hours to deadline",
    },
    "multilingual_notifications": {
        "default": True,
        "description": "Translate notifications into the recipient's preferred language via Sarvam",
    },
    "impact_dashboard": {"default": True, "description": "AI impact dashboard and public statistics"},
}


@dataclass
class _FlagsmithState:
    flags: Dict[str, bool]
    fetched_at: float
    ok: bool
    error: Optional[str]


class FlagService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Optional[_FlagsmithState] = None

    def reset(self) -> None:
        with self._lock:
            self._state = None

    def _fetch_flagsmith(self) -> _FlagsmithState:
        s = get_settings()
        try:
            resp = httpx.get(
                s.flagsmith_api_url.rstrip("/") + "/flags/",
                headers={"X-Environment-Key": s.flagsmith_environment_key or ""},
                timeout=5.0,
            )
            resp.raise_for_status()
            flags: Dict[str, bool] = {}
            for item in resp.json():
                name = (item.get("feature") or {}).get("name")
                if name:
                    flags[name] = bool(item.get("enabled"))
            return _FlagsmithState(flags=flags, fetched_at=time.time(), ok=True, error=None)
        except Exception as exc:  # network errors, 4xx/5xx, malformed JSON
            log.warning("Flagsmith fetch failed: %s", exc)
            return _FlagsmithState(flags={}, fetched_at=time.time(), ok=False, error=str(exc)[:300])

    def _flagsmith(self) -> Optional[_FlagsmithState]:
        s = get_settings()
        if not s.flagsmith_configured:
            return None
        with self._lock:
            if self._state is None or time.time() - self._state.fetched_at > s.flagsmith_cache_seconds:
                self._state = self._fetch_flagsmith()
            return self._state

    def evaluate_all(self, db: Session) -> List[Dict]:
        overrides = {o.flag_name: o for o in db.query(FeatureFlagOverride).all()}
        fs = self._flagsmith()
        out = []
        for name, meta in FLAG_DEFINITIONS.items():
            flagsmith_value = fs.flags.get(name) if (fs and fs.ok) else None
            if name in overrides:
                enabled, source = overrides[name].enabled, "local_override"
            elif flagsmith_value is not None:
                enabled, source = flagsmith_value, "flagsmith"
            else:
                enabled, source = meta["default"], "default"
            out.append(
                {
                    "name": name,
                    "description": meta["description"],
                    "enabled": enabled,
                    "source": source,
                    "default": meta["default"],
                    "flagsmith_value": flagsmith_value,
                    "local_override": overrides[name].enabled if name in overrides else None,
                }
            )
        return out

    def is_enabled(self, db: Session, name: str) -> bool:
        for f in self.evaluate_all(db):
            if f["name"] == name:
                return bool(f["enabled"])
        raise KeyError(name)

    def enabled_map(self, db: Session) -> Dict[str, bool]:
        return {f["name"]: f["enabled"] for f in self.evaluate_all(db)}

    def connection_status(self) -> Dict:
        s = get_settings()
        if not s.flagsmith_configured:
            return {
                "configured": False,
                "connected": False,
                "message": "FLAGSMITH_ENVIRONMENT_KEY not set - using safe defaults and local overrides only.",
            }
        fs = self._flagsmith()
        assert fs is not None
        return {
            "configured": True,
            "connected": fs.ok,
            "api_url": s.flagsmith_api_url,
            "last_fetched_at": fs.fetched_at,
            "flags_received": sorted(fs.flags.keys()),
            "message": "Connected to Flagsmith" if fs.ok else f"Flagsmith unreachable - using safe defaults ({fs.error})",
        }


flag_service = FlagService()
