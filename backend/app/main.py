from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .database import SessionLocal
from .ratelimit import client_ip, limiter
from .routers import admin, ai, auth, listings, me, ngo, public, volunteer
from .services import lifecycle
from .services.monitoring import configure_logging, metrics, record_incident

configure_logging()
log = logging.getLogger("festiveplate.api")


async def _expiry_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            with SessionLocal() as db:
                n = lifecycle.expire_overdue(db)
                if n:
                    log.info("expired listings", extra={"fields": {"count": n}})
        except Exception:  # keep the loop alive; error is logged
            log.exception("expiry loop failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_expiry_loop())
    log.info("FestivePlate API started", extra={"fields": {"env": get_settings().app_env}})
    yield
    task.cancel()


app = FastAPI(
    title="FestivePlate API",
    version="1.0.0",
    description=(
        "AI-powered food surplus prediction, rescue and redistribution for Bengaluru. "
        "Food-safety checks are automated *screening*, never certification. "
        "Sarvam / Flagsmith / NudgeBee integrations report their real connection state; "
        "anything simulated is labelled as such."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def observe(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    s = get_settings()
    if request.url.path.startswith("/api/") and not limiter.hit(f"global:{client_ip(request)}", s.rate_limit_default_per_minute):
        return JSONResponse({"detail": "Too many requests"}, status_code=429)
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as exc:
        status_code = 500
        log.exception("unhandled error", extra={"fields": {"request_id": rid, "path": request.url.path}})
        response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
        try:
            with SessionLocal() as db:
                record_incident(db, fingerprint=f"api-500:{request.method}:{request.url.path}"[:200], category="API_ERROR",
                                severity="HIGH", title=f"500 on {request.method} {request.url.path}",
                                details={"request_id": rid, "error": f"{type(exc).__name__}: {exc}"[:300]})
        except Exception:
            log.exception("failed to record incident")
    elapsed = time.perf_counter() - start
    route = request.scope.get("route")
    route_path = getattr(route, "path", None) or ("unmatched" if status_code == 404 else request.url.path)
    metrics.observe(request.method, route_path, status_code, elapsed)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    log.info("request", extra={"fields": {"request_id": rid, "method": request.method, "route": route_path,
                                          "status": status_code, "ms": round(elapsed * 1000, 1)}})
    return response


for r in (auth.router, me.router, listings.router, ngo.router, volunteer.router, admin.router, ai.router, public.router):
    app.include_router(r)
