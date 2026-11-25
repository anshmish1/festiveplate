"""Small in-memory sliding-window rate limiter.

Suitable for a single-instance deployment / hackathon demo. For multi-instance
production deployments, swap the storage for Redis (documented in README).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict

from fastapi import HTTPException, Request, status

from .config import get_settings


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str) -> Callable[[Request], None]:
    def _dep(request: Request) -> None:
        s = get_settings()
        limit = {
            "auth": s.rate_limit_auth_per_minute,
            "ai": s.rate_limit_ai_per_minute,
        }.get(bucket, s.rate_limit_default_per_minute)
        if not limiter.hit(f"{bucket}:{client_ip(request)}", limit):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Please slow down and retry shortly.")

    return _dep
