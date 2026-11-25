"""Auth, admin, feature flags, AI demo mode, monitoring."""
from __future__ import annotations

from app.seed import DOMAIN


def test_register_ngo_is_pending_and_admin_can_verify(client, as_user):
    r = client.post("/api/auth/register", json={
        "email": f"new.ngo@{DOMAIN}", "password": "Secret123", "full_name": "Test NGO Admin", "role": "NGO",
        "ngo": {"organization_name": "Test Kitchen (DEMO)", "registration_number": "TEST-001", "contact_person": "Test Person",
                "address": "Somewhere in Electronic City", "area": "Electronic City", "latitude": 12.85, "longitude": 77.66},
    })
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    prof = client.get("/api/ngo/profile", headers=h).json()
    assert prof["verification_status"] == "PENDING"
    assert client.get("/api/ngo/listings/available", headers=h).status_code == 403
    r = client.post(f"/api/admin/ngos/{prof['id']}/verify", json={"decision": "VERIFIED", "notes": "Docs checked"}, headers=as_user("admin"))
    assert r.status_code == 200 and r.json()["verification_status"] == "VERIFIED"
    assert client.get("/api/ngo/listings/available", headers=h).status_code == 200


def test_register_validation(client):
    r = client.post("/api/auth/register", json={"email": "x@example.com", "password": "short", "full_name": "X", "role": "DONOR"})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"email": "admin2@example.com", "password": "Secret123", "full_name": "Sneaky", "role": "ADMIN"})
    assert r.status_code == 422  # admin cannot self-register


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": f"admin@{DOMAIN}", "password": "nope-nope1"})
    assert r.status_code == 401


def test_role_enforcement(client, as_user):
    assert client.get("/api/admin/users", headers=as_user("shubha.mantapa")).status_code == 403
    assert client.get("/api/admin/users", headers=as_user("admin")).status_code == 200


def test_deactivated_user_blocked(client, as_user):
    h = as_user("udupi.grand")
    users = client.get("/api/admin/users?q=udupi", headers=as_user("admin")).json()
    client.patch(f"/api/admin/users/{users[0]['id']}", json={"is_active": False}, headers=as_user("admin"))
    assert client.get("/api/me", headers=h).status_code == 401


def test_flags_safe_defaults_without_flagsmith(client, as_user):
    r = client.get("/api/admin/flags", headers=as_user("admin")).json()
    assert r["connection"]["configured"] is False and r["connection"]["connected"] is False
    by_name = {f["name"]: f for f in r["flags"]}
    assert set(by_name) == {"voice_reporting", "surplus_prediction", "emergency_matching", "multilingual_notifications", "impact_dashboard"}
    assert all(f["source"] == "default" for f in r["flags"])


def test_flag_override_disables_feature_and_is_audited(client, as_user):
    admin = as_user("admin")
    r = client.put("/api/admin/flags/voice_reporting/override", json={"enabled": False, "reason": "demo"}, headers=admin)
    assert r.status_code == 200
    assert client.post("/api/ai/voice/demo?language=kn", headers=as_user("shubha.mantapa")).status_code == 403
    flags = client.get("/api/admin/flags", headers=admin).json()
    assert flags["audit"][0]["flag_name"] == "voice_reporting" and flags["audit"][0]["source"] == "local_override"
    client.delete("/api/admin/flags/voice_reporting/override", headers=admin)
    assert client.post("/api/ai/voice/demo?language=kn", headers=as_user("shubha.mantapa")).status_code == 200


def test_voice_transcribe_demo_mode_is_labelled(client, as_user):
    r = client.post("/api/ai/voice/transcribe", data={"language": "kn"},
                    files={"audio": ("a.webm", b"\x1aE\xdf\xa3fake-webm", "audio/webm")}, headers=as_user("shubha.mantapa"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulated"] is True and "DEMO" in body["mode"]
    assert body["draft"]["portions_reported"] == 150


def test_translate_unavailable_without_key(client, as_user):
    r = client.post("/api/ai/translate", json={"text": "hello", "source": "en", "target": "kn"}, headers=as_user("admin"))
    assert r.status_code == 503


def test_predict_endpoint(client, as_user):
    r = client.post("/api/ai/predict-surplus", json={"planned_servings": 600, "expected_attendance": 550}, headers=as_user("shubha.mantapa"))
    assert r.status_code == 200 and r.json()["is_prediction"] is True


def test_system_health_reports_nudgebee_not_connected(client, as_user):
    client.get("/health")
    r = client.get("/api/admin/system/health", headers=as_user("admin")).json()
    assert r["integrations"]["nudgebee"]["state"] == "NOT_CONFIGURED"
    assert r["integrations"]["nudgebee"]["live"] is False
    assert all(i["simulated"] for i in r["simulated_ai_insights"])
    assert r["backend"]["database_ok"] is True
    assert r["integrations"]["sarvam"]["configured"] is False


def test_metrics_endpoint(client):
    client.get("/health")
    body = client.get("/metrics").text
    assert "festiveplate_http_requests_total" in body


def test_public_impact_has_no_personal_data(client):
    r = client.get("/api/impact/public").json()
    assert r["enabled"] is True and r["includes_demo_data"] is True
    assert set(r) == {"enabled", "includes_demo_data", "delivered_portions", "completed_donations", "verified_ngos", "collected_portions"}


def test_audit_log_written(client, as_user):
    client.get("/api/me", headers=as_user("admin"))
    logs = client.get("/api/admin/audit-logs", headers=as_user("admin")).json()
    assert any(l["action"] == "LOGIN" for l in logs)
