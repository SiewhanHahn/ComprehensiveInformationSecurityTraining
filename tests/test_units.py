import json
from pathlib import Path

from backend.app.cities import CITIES, DEFAULT_MODELS
from backend.app.deps import CurrentUser
from backend.app.services.warnings import is_viewer_only
from backend.app.security import hash_password, new_public_id, verify_password
from backend.app.services.metrics import get_experiment, list_experiments

ROOT = Path(__file__).resolve().parent.parent


def test_password_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong", hashed)


def test_public_id_is_unguessable_length():
    ids = {new_public_id() for _ in range(100)}
    assert all(len(i) == 26 for i in ids)
    assert len(ids) == 100


def test_nine_cities_and_four_models():
    assert len(CITIES) == 9
    assert len(DEFAULT_MODELS) == 4


def test_frozen_metrics_main_result():
    detail = get_experiment("10mm")
    assert detail is not None
    assert detail.n == 2403
    assert detail.positives == 406
    assert detail.baseline.f1 == 0.7462
    assert detail.fusion.f1 == 0.79
    assert detail.delta_f1 == 4.38
    assert detail.bootstrap_interval == [1.57, 7.29]


def test_experiment_list_has_10_and_25():
    versions = {e.version for e in list_experiments()}
    assert {"10mm", "25mm"}.issubset(versions)


def test_offline_sample_structure():
    data = json.loads((ROOT / "data/sample/replay_sample.json").read_text(encoding="utf-8"))
    assert data["days"], "sample must not be empty"
    for day in data["days"]:
        assert day["city_code"] in CITIES
        assert day["valid_date"]
        assert set(day["models"]).issubset(set(DEFAULT_MODELS))
        assert day["proxy_label_mm"] is not None
    assert any(d["proxy_label_mm"] >= 25 for d in data["days"])
    assert any(d["proxy_label_mm"] < 10 for d in data["days"])


def test_viewer_only():
    assert is_viewer_only(CurrentUser(1, "v", ["VIEWER"]))
    assert not is_viewer_only(CurrentUser(2, "a", ["ANALYST"]))
    assert not is_viewer_only(CurrentUser(3, "va", ["VIEWER", "ANALYST"]))
    assert not is_viewer_only(CurrentUser(4, "admin", ["ADMIN"]))
    assert not is_viewer_only(CurrentUser(5, "r", ["REVIEWER"]))
