"""下载并检查 NOAA GHCN-Daily 真实站点观测。

用途：作为 ERA5 代理标签的独立历史交叉验证，不替换主实验标签。
PRCP 原始单位为 0.1 mm；缺测通常为 9999 或空值。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "observations"
BASE = "https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access"


def fetch_station(station: str) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{station}.csv"
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        url = f"{BASE}/{station}.csv"
        with urllib.request.urlopen(url, timeout=90) as response:
            text = response.read().decode("utf-8")
        path.write_text(text, encoding="utf-8")
        time.sleep(0.5)

    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        raw = (row.get("PRCP") or "").strip()
        try:
            tenths_mm = int(raw)
        except ValueError:
            continue
        if tenths_mm == 9999:
            continue
        rows.append({
            "station": row.get("STATION"),
            "date": row.get("DATE"),
            "lat": float(row["LATITUDE"]),
            "lon": float(row["LONGITUDE"]),
            "name": row.get("NAME"),
            "prcp_mm": tenths_mm / 10.0,
            "attributes": row.get("PRCP_ATTRIBUTES", ""),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="GHCN-Daily 真实降水观测检查")
    parser.add_argument("--station", action="append", required=True, help="例如 CHM00057687")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    result = []
    for station in args.station:
        rows = fetch_station(station)
        if args.start:
            rows = [r for r in rows if r["date"] >= args.start]
        if args.end:
            rows = [r for r in rows if r["date"] <= args.end]
        positives = sum(r["prcp_mm"] >= 25.0 for r in rows)
        result.append({
            "station": station,
            "rows": len(rows),
            "first_date": rows[0]["date"] if rows else None,
            "last_date": rows[-1]["date"] if rows else None,
            "positive_25mm_days": positives,
            "max_prcp_mm": max((r["prcp_mm"] for r in rows), default=None),
            "sample": rows[:2],
        })

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
