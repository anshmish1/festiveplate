"""Unit tests: food-safety screening, voice extraction, surplus prediction."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.services.extraction import build_draft, rule_based_extract, words_to_number
from app.services.prediction import predict_surplus
from app.services.safety import screen
from app.services.voice import demo_report

NOW = datetime(2026, 11, 25, 16, 30)  # 10 PM IST


def _screen(**kw):
    base = dict(prepared_at=NOW - timedelta(hours=1), pickup_deadline=NOW + timedelta(hours=3),
                storage_condition="HOT_HELD", food_category="VEG", allergens="none", now=NOW)
    base.update(kw)
    return screen(**base)


def test_safe_listing_is_eligible_not_certified():
    r = _screen()
    assert r.result == "ELIGIBLE"
    assert r.blocking == []


def test_missing_storage_is_flagged():
    r = _screen(storage_condition=None)
    assert r.result == "FLAGGED"
    assert any(i.code == "MISSING_STORAGE_INFO" for i in r.issues)


def test_expired_deadline_is_flagged():
    r = _screen(pickup_deadline=NOW - timedelta(minutes=1))
    assert r.result == "FLAGGED"
    assert any(i.code == "DEADLINE_PASSED" for i in r.issues)


def test_room_temperature_over_two_hours_is_flagged():
    r = _screen(storage_condition="ROOM_TEMPERATURE", prepared_at=NOW - timedelta(hours=1), pickup_deadline=NOW + timedelta(hours=2))
    assert r.result == "FLAGGED"
    assert any(i.code == "DEADLINE_BEYOND_SAFE_HOLD" for i in r.issues)


def test_already_beyond_hold_time_is_flagged():
    r = _screen(storage_condition="HOT_HELD", prepared_at=NOW - timedelta(hours=7), pickup_deadline=NOW + timedelta(minutes=50))
    assert any(i.code == "HOLD_TIME_EXCEEDED" for i in r.issues)


def test_prepared_in_future_is_flagged():
    assert _screen(prepared_at=NOW + timedelta(hours=1)).result == "FLAGGED"


def test_missing_allergens_is_only_a_warning():
    r = _screen(allergens=None)
    assert r.result == "ELIGIBLE"
    assert any(i.code == "ALLERGENS_NOT_DECLARED" and i.severity == "WARNING" for i in r.issues)


def test_words_to_number():
    assert words_to_number("one hundred and fifty") == 150
    assert words_to_number("eighty") == 80
    assert words_to_number("banana") is None


def test_demo_kannada_report_extracts_scenario_fields():
    out = demo_report("kn")
    assert out["simulated"] is True and "DEMO" in out["mode"]
    d = out["draft"]
    assert d["portions_reported"] == 150
    assert d["food_category"] == "VEG"
    assert d["storage_condition"] == "HOT_HELD"
    assert d["area"] == "Electronic City"
    assert d["pickup_deadline"] > d["prepared_at"]
    assert out["missing_fields"] == []


def test_extraction_never_guesses_missing_values():
    out = build_draft(rule_based_extract("We have some leftover food, please come."))
    assert out["draft"]["portions_reported"] is None
    assert out["draft"]["storage_condition"] is None
    assert "portions_reported" in out["missing_fields"]


def test_absolute_times_resolved_in_ist():
    raw = rule_based_extract("80 non veg plates of chicken biryani cooked at 8 pm, refrigerated, pick up before 11 pm in HSR Layout")
    out = build_draft(raw, now=NOW)  # NOW = 10 PM IST
    d = out["draft"]
    assert d["food_category"] == "NON_VEG"
    assert d["storage_condition"] == "REFRIGERATED"
    assert d["prepared_at"] == datetime(2026, 11, 25, 14, 30)  # 8 PM IST
    assert d["pickup_deadline"] == datetime(2026, 11, 25, 17, 30)  # 11 PM IST


def test_prediction_is_labelled_and_uses_history():
    p = predict_surplus(event_type="WEDDING", planned_servings=1000, expected_attendance=900,
                        historical=[{"planned_servings": 1000, "consumed_servings": 850}, {"planned_servings": 800, "consumed_servings": 720}])
    assert p["is_prediction"] is True and "PREDICTION" in p["label"]
    assert p["method"] == "historical_consumption"
    assert 100 <= p["predicted_surplus_portions"] <= 160
    assert p["range_low"] <= p["predicted_surplus_portions"] <= p["range_high"]


def test_prediction_baseline_lists_assumptions():
    p = predict_surplus(event_type="WEDDING", planned_servings=500, expected_attendance=500)
    assert p["method"] == "baseline_assumptions"
    assert p["predicted_surplus_portions"] == 75
    assert any("Baseline assumption" in a for a in p["assumptions"])
