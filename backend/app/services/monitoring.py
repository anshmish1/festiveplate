"""Observability: in-process metrics, incident tracking and the NudgeBee adapter.

What is REAL here:
  * request/latency/error counters collected by middleware in this process
  * structured JSON logs written to stdout
  * a Prometheus text endpoint (/metrics) that any scraper can read
  * incidents persisted in `application_incidents` from real errors and failed notifications
  * rule-based incident summaries computed from those real incidents

NudgeBee: NudgeBee is an AI SRE / CloudOps platform that connects to your
Kubernetes cluster via its agent and reads observability data (metrics/logs/events).
FestivePlate exposes Prometheus metrics and JSON logs for that purpose. Optionally,
incidents can be forwarded to a webhook URL you configure (NUDGEBEE_WEBHOOK_URL).
This app can NOT verify a NudgeBee connection from the inside, so it never reports
"connected" - only "not configured", "configured (unverified)" or the real result
of the last webhook delivery.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ApplicationIncident, Notification
from .timegeo import utcnow

log = logging.getLogger("festiveplate.monitoring")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    root = logging.getLogger()
    if any(getattr(h, "_festiveplate", False) for h in root.handlers):
        return
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    h._festiveplate = True  # type: ignore[attr-defined]
    root.handlers = [h]
    root.setLevel(logging.INFO)


class Metrics:
    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = threading.Lock()
        self.requests: Dict[Tuple[str, str, int], int] = defaultdict(int)
        self.latency_sum: Dict[str, float] = defaultdict(float)
        self.latency_count: Dict[str, int] = defaultdict(int)
        self.recent_errors: Deque[Dict[str, Any]] = deque(maxlen=50)
        self.integration_calls: Dict[Tuple[str, str], int] = defaultdict(int)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self.requests[(method, route, status)] += 1
            self.latency_sum[route] += seconds
            self.latency_count[route] += 1
            if status >= 500:
                self.recent_errors.append({"route": route, "method": method, "status": status, "at": time.time()})

    def integration(self, name: str, outcome: str) -> None:
        with self._lock:
            self.integration_calls[(name, outcome)] += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            total = sum(self.requests.values())
            errors5 = sum(v for (m, r, s), v in self.requests.items() if s >= 500)
            errors4 = sum(v for (m, r, s), v in self.requests.items() if 400 <= s < 500)
            by_route: Dict[str, Dict[str, Any]] = {}
            for (m, r, s), v in self.requests.items():
                d = by_route.setdefault(f"{m} {r}", {"requests": 0, "errors_5xx": 0, "errors_4xx": 0})
                d["requests"] += v
                if s >= 500:
                    d["errors_5xx"] += v
                elif s >= 400:
                    d["errors_4xx"] += v
            for key, d in by_route.items():
                route = key.split(" ", 1)[1]
                cnt = self.latency_count.get(route) or 1
                d["avg_latency_ms"] = round(self.latency_sum.get(route, 0) / cnt * 1000, 1)
            return {
                "uptime_seconds": round(time.time() - self.started_at),
                "started_at": self.started_at,
                "total_requests": total,
                "errors_5xx": errors5,
                "errors_4xx": errors4,
                "error_rate": round(errors5 / total, 4) if total else 0.0,
                "routes": dict(sorted(by_route.items(), key=lambda kv: -kv[1]["requests"])[:25]),
                "recent_errors": list(self.recent_errors)[-10:],
                "integration_calls": {f"{n}:{o}": v for (n, o), v in self.integration_calls.items()},
            }

    def prometheus(self) -> str:
        lines = [
            "# HELP festiveplate_uptime_seconds Process uptime",
            "# TYPE festiveplate_uptime_seconds gauge",
            f"festiveplate_uptime_seconds {time.time() - self.started_at:.0f}",
            "# HELP festiveplate_http_requests_total HTTP requests",
            "# TYPE festiveplate_http_requests_total counter",
        ]
        with self._lock:
            for (m, r, s), v in self.requests.items():
                lines.append(f'festiveplate_http_requests_total{{method="{m}",route="{r}",status="{s}"}} {v}')
            lines += [
                "# HELP festiveplate_http_request_seconds_sum Total request latency",
                "# TYPE festiveplate_http_request_seconds_sum counter",
            ]
            for r, v in self.latency_sum.items():
                lines.append(f'festiveplate_http_request_seconds_sum{{route="{r}"}} {v:.4f}')
            lines += ["# TYPE festiveplate_integration_calls_total counter"]
            for (n, o), v in self.integration_calls.items():
                lines.append(f'festiveplate_integration_calls_total{{integration="{n}",outcome="{o}"}} {v}')
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        self.__init__()


metrics = Metrics()

_nudgebee_last: Dict[str, Any] = {"delivered": None, "at": None, "error": None}


def nudgebee_status() -> Dict[str, Any]:
    s = get_settings()
    if not s.nudgebee_enabled:
        return {
            "state": "NOT_CONFIGURED",
            "live": False,
            "message": (
                "NudgeBee is not configured. Incident analysis shown in this dashboard is generated locally "
                "from FestivePlate's own data. Any NudgeBee-style AI insight is SIMULATED."
            ),
            "exposed_signals": ["/metrics (Prometheus)", "JSON structured logs on stdout", "/health"],
        }
    return {
        "state": "CONFIGURED_UNVERIFIED",
        "live": False,
        "message": (
            "NUDGEBEE_ENABLED=true. FestivePlate exposes Prometheus metrics and JSON logs for the NudgeBee agent "
            "to collect, but cannot verify from inside the app that NudgeBee is receiving them. Confirm in the "
            "NudgeBee console."
        ),
        "webhook_configured": bool(s.nudgebee_webhook_url),
        "last_webhook_delivery": dict(_nudgebee_last),
        "exposed_signals": ["/metrics (Prometheus)", "JSON structured logs on stdout", "/health"],
    }


def _forward_to_webhook(incident: ApplicationIncident) -> None:
    s = get_settings()
    if not (s.nudgebee_enabled and s.nudgebee_webhook_url):
        return
    headers = {"Content-Type": "application/json"}
    if s.nudgebee_api_key:
        headers["Authorization"] = f"Bearer {s.nudgebee_api_key}"
    body = {
        "source": "festiveplate",
        "title": incident.title,
        "severity": incident.severity,
        "category": incident.category,
        "occurrences": incident.occurrences,
        "details": incident.details,
    }
    try:
        r = httpx.post(s.nudgebee_webhook_url, json=body, headers=headers, timeout=5.0)
        _nudgebee_last.update(delivered=r.status_code < 400, at=time.time(), error=None if r.status_code < 400 else f"HTTP {r.status_code}")
        metrics.integration("nudgebee_webhook", "ok" if r.status_code < 400 else "error")
    except httpx.HTTPError as exc:
        _nudgebee_last.update(delivered=False, at=time.time(), error=str(exc)[:200])
        metrics.integration("nudgebee_webhook", "error")


def record_incident(
    db: Session, *, fingerprint: str, category: str, severity: str, title: str, details: Optional[Dict[str, Any]] = None
) -> ApplicationIncident:
    """Create or bump an OPEN incident with the same fingerprint. Commits."""
    now = utcnow()
    inc = (
        db.query(ApplicationIncident)
        .filter(ApplicationIncident.fingerprint == fingerprint, ApplicationIncident.status == "OPEN")
        .one_or_none()
    )
    if inc:
        inc.occurrences += 1
        inc.last_seen = now
        if details:
            inc.details = {**(inc.details or {}), "latest": details}
    else:
        inc = ApplicationIncident(
            fingerprint=fingerprint[:200], category=category, severity=severity, title=title[:200],
            details={"first": details or {}}, first_seen=now, last_seen=now,
        )
        db.add(inc)
    db.commit()
    log.warning("incident", extra={"fields": {"incident": title, "category": category, "severity": severity}})
    if inc.occurrences == 1 or inc.occurrences % 10 == 0:
        _forward_to_webhook(inc)
    return inc


def incident_summary(db: Session) -> Dict[str, Any]:
    """Deterministic, data-backed summary of open incidents and notification failures."""
    open_incidents: List[ApplicationIncident] = (
        db.query(ApplicationIncident).filter(ApplicationIncident.status == "OPEN").order_by(ApplicationIncident.last_seen.desc()).all()
    )
    failed_notifications = db.query(Notification).filter(Notification.status == "FAILED").count()
    snap = metrics.snapshot()
    lines: List[str] = []
    if not open_incidents and failed_notifications == 0 and snap["errors_5xx"] == 0:
        lines.append("No open incidents. All recorded API requests in this process completed without server errors.")
    else:
        by_cat: Dict[str, int] = defaultdict(int)
        for i in open_incidents:
            by_cat[i.category] += i.occurrences
        if by_cat:
            lines.append(
                f"{len(open_incidents)} open incident(s): "
                + ", ".join(f"{k.replace('_', ' ').lower()} x{v}" for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1]))
                + "."
            )
        if open_incidents:
            top = max(open_incidents, key=lambda i: i.occurrences)
            lines.append(f"Most frequent: '{top.title}' ({top.occurrences} occurrences, severity {top.severity}).")
        if failed_notifications:
            lines.append(
                f"{failed_notifications} notification(s) failed. Check translation provider status and recipient preferences; "
                "the untranslated English message is still delivered in-app when translation fails."
            )
        if snap["errors_5xx"]:
            lines.append(f"{snap['errors_5xx']} server error(s) out of {snap['total_requests']} requests since process start.")
    return {
        "generated_by": "FestivePlate rule-based summariser (local data, not NudgeBee)",
        "summary": " ".join(lines),
        "open_incidents": len(open_incidents),
        "failed_notifications": failed_notifications,
    }


SIMULATED_NUDGEBEE_INSIGHTS = [
    {
        "simulated": True,
        "title": "SIMULATED: Translation latency spike correlated with notification failures",
        "insight": "Example of the kind of root-cause hint an AI SRE tool could provide. Not produced by NudgeBee.",
        "recommendation": "Add retry with backoff on the translation call and alert if failure rate exceeds 5% over 10 minutes.",
    },
    {
        "simulated": True,
        "title": "SIMULATED: Backend pod memory approaching limit during evening peak (8-11 PM)",
        "insight": "Illustrative only - FestivePlate has no live cluster telemetry in demo mode.",
        "recommendation": "Right-size memory requests/limits after observing real usage.",
    },
]
