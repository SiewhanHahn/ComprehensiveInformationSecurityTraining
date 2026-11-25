"""Offline verification of the frozen v1 city-day set and threshold metrics (stdlib only)."""
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path


RESULTS = Path(__file__).resolve().parents[1] / "data/results"
MANIFEST_SHA256 = "7455dda89c8cd400d03c346287deeb58356d8b09fe253768c025fa3658f020ec"
FIELDS = ("city", "utc_date", "ecmwf", "fusion", "era5")
THRESHOLDS = (10, 25)


def verify(rows, snapshot):
    """Recount pooled outcomes; input bins are the highest reached threshold, not rainfall."""
    city_days = set()
    sites = Counter()
    counts = {(t, src): Counter(tp=0, fp=0, fn=0, tn=0) for t in THRESHOLDS for src in ("ecmwf", "fusion")}
    for row in rows:
        if set(row) != set(FIELDS) or any(row[k] not in {"0", "10", "25"} for k in FIELDS[2:]):
            raise ValueError("invalid manifest row")
        key = row["city"], row["utc_date"]
        if key in city_days:
            raise ValueError(f"duplicate city-day: {key}")
        city_days.add(key)
        sites[row["city"]] += 1
        for (threshold, src), matrix in counts.items():
            obs, pred = int(row["era5"]) >= threshold, int(row[src]) >= threshold
            cell = ("tp" if obs else "fp") if pred else ("fn" if obs else "tn")
            matrix[cell] += 1

    if len(snapshot) != 2 or {item["threshold_mm_24h"] for item in snapshot} != set(THRESHOLDS):
        raise ValueError("unexpected frozen thresholds")
    results = {}
    for item in snapshot:
        t = int(item["threshold_mm_24h"])
        pool = item["pooled"]
        if len(city_days) != pool["n"] or dict(sites) != {k: v["n"] for k, v in item["per_site"].items()}:
            raise ValueError(f"{t} mm: city-day coverage differs")
        scores = []
        for src, method in (("ecmwf", "baseline"), ("fusion", "fusion")):
            m = counts[t, src]
            f1 = round(2 * m["tp"] / (2 * m["tp"] + m["fp"] + m["fn"]), 4)
            if dict(m) != pool[method]["confusion"] or f1 != pool[method]["f1"] or m["tp"] + m["fn"] != pool["positives"]:
                raise ValueError(f"{t} mm {method}: confusion, positives or F1 differs")
            scores.append(f1)
        results[t] = tuple(scores)
    return results


def verify_files(directory=RESULTS):
    # Ignore checkout newline conversion, but not altered dates, grades, ordering or headers.
    manifest = (directory / "rain-v1-city-days.csv").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(manifest).hexdigest() != MANIFEST_SHA256:
        raise ValueError("frozen city-day manifest checksum mismatch")
    rows = list(csv.DictReader(io.StringIO(manifest.decode("utf-8"))))
    return len(rows), verify(rows, json.loads((directory / "pooled.json").read_bytes()))


def main():
    n, results = verify_files()
    for t, (base, fused) in results.items():
        print(f"v1: {n} city-days | {t} mm | confusion OK | F1 {base:.4f} -> {fused:.4f}")


if __name__ == "__main__":
    main()
