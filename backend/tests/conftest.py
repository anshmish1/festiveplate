"""Test configuration.

By default tests run against a temporary SQLite file. Set TEST_DATABASE_URL to a
PostgreSQL URL to run the same suite (including the concurrency test) on Postgres.
"""
from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="festiveplate-test-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["JWT_SECRET"] = "test-secret-not-for-production-use-0123456789"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["RATE_LIMIT_DEFAULT_PER_MINUTE"] = "100000"
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "100000"
os.environ["RATE_LIMIT_AI_PER_MINUTE"] = "100000"
for k in ("SARVAM_API_KEY", "FLAGSMITH_ENVIRONMENT_KEY", "NUDGEBEE_ENABLED"):
    os.environ.pop(k, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import limiter  # noqa: E402
from app.seed import DEMO_PASSWORD, DOMAIN, seed  # noqa: E402
from app.services.flags import flag_service  # noqa: E402
from app.services.monitoring import metrics  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    limiter.reset()
    flag_service.reset()
    metrics.reset()
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(client: TestClient, local_part: str) -> dict:
    r = client.post("/api/auth/login", json={"email": f"{local_part}@{DOMAIN}", "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def as_user(client):
    cache: dict = {}

    def _get(local_part: str) -> dict:
        if local_part not in cache:
            cache[local_part] = login(client, local_part)
        return cache[local_part]

    return _get
