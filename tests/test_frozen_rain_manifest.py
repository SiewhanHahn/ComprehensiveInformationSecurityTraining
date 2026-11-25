"""Offline contract for the frozen 2026 rain sample (no VM, network or DB)."""
import csv
import io
import json
from pathlib import Path

import pytest

from backend.verify_frozen_rain import verify, verify_files


ROOT = Path(__file__).resolve().parents[1] / "data/results"


def inputs():
    rows = list(csv.DictReader(io.StringIO((ROOT / "rain-v1-city-days.csv").read_text(encoding="utf-8"))))
    return rows, json.loads((ROOT / "pooled.json").read_bytes())


def test_frozen_city_day_denominator_and_confusions():
    rows, snapshot = inputs()
    results = verify(rows, snapshot)
    assert results == {10: (0.7462, 0.79), 25: (0.6, 0.6498)}


def test_duplicate_day_cannot_replace_another_day_even_when_counts_match():
    rows, snapshot = inputs()
    rows[1]["utc_date"] = rows[0]["utc_date"]
    with pytest.raises(ValueError, match="duplicate"):
        verify(rows, snapshot)


def test_changed_forecast_class_fails_verification():
    rows, snapshot = inputs()
    rows[0]["fusion"] = "25" if rows[0]["fusion"] == "0" else "0"
    with pytest.raises(ValueError):
        verify(rows, snapshot)


def test_missing_threshold_in_snapshot_is_not_success():
    rows, snapshot = inputs()
    with pytest.raises(ValueError, match="threshold"):
        verify(rows, snapshot[:1])


def test_manifest_identity_rejects_date_swap_even_if_counts_match(tmp_path):
    path = ROOT / "rain-v1-city-days.csv"
    # CRLF checkouts are valid; changing even one date with identical bins is not.
    canonical = path.read_bytes().replace(b"\r\n", b"\n")
    copied = tmp_path / path.name
    copied.write_bytes(canonical.replace(b"\n", b"\r\n"))
    (tmp_path / "pooled.json").write_bytes((ROOT / "pooled.json").read_bytes())
    assert verify_files(tmp_path)[0] == 2403
    copied.write_bytes(canonical.replace(b"2026-01-01", b"2026-01-21", 1))
    with pytest.raises(ValueError, match="checksum"):
        verify_files(tmp_path)
