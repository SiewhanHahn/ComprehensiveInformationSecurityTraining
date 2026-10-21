"""用 GHCN-Daily 站点观测替换 ERA5 标签做独立交叉验证。

注意：GHCN-Daily 的 PRCP 是站点日累计，观测日界线可能与 Open-Meteo UTC 日界线不同。
因此本脚本只作为独立历史交叉验证，不把结果并入主实验；报告中必须标注这一时间口径限制。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from fusion import DEFAULT_MODELS, _f1, build_fusion_table, metrics
from ghcn_daily import fetch_station


def ghcn_label_by_date(station: str, start: str, end: str) -> dict[str, float]:
    rows = fetch_station(station)
    return {
        row["date"]: row["prcp_mm"]
        for row in rows
        if start <= row["date"] <= end
    }


def evaluate_station(
    site: str,
    station: str,
    lat: float,
    lon: float,
    start: str,
    end: str,
    threshold: float,
    models: list[str],
) -> dict:
    table = build_fusion_table(lat, lon, start, end, models)
    ghcn = ghcn_label_by_date(station, start, end)
    days = table["days"]
    X = table["X"]
    common_idx = [i for i, day in enumerate(days) if day in ghcn]
    if not common_idx:
        return {"site": site, "station": station, "error": "没有共同日期"}

    obs = np.array([ghcn[days[i]] for i in common_idx], dtype=float)
    features = X[common_idx]
    y = (obs >= threshold).astype(float)
    base_idx = models.index("ecmwf_ifs025")
    base_scores = features[:, base_idx]
    fusion_scores = features.mean(axis=1)
    base_pred = (base_scores >= threshold).astype(float)
    fusion_pred = (fusion_scores >= threshold).astype(float)

    years = [days[i][:4] for i in common_idx]
    return {
        "site": site,
        "station": station,
        "period": {"from": days[common_idx[0]], "to": days[common_idx[-1]]},
        "threshold_mm_per_day": threshold,
        "models": models,
        "label": "NOAA GHCN-Daily PRCP station observation",
        "counts": {
            "common_days": len(common_idx),
            "positives": int(y.sum()),
            "years": {year: years.count(year) for year in sorted(set(years))},
        },
        "baseline": metrics(y, base_pred, base_scores),
        "fusion": metrics(y, fusion_pred, fusion_scores),
        "delta_f1_points": round((_f1(y, fusion_pred) - _f1(y, base_pred)) * 100, 2),
        "notes": [
            "GHCN PRCP 为站点日累计，日界线可能与 Open-Meteo UTC 日累计不同。",
            "结果用于独立历史交叉验证，不替换 ERA5 主实验标签。",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="GHCN 真实观测交叉验证")
    parser.add_argument("--site", default="长沙")
    parser.add_argument("--station", default="CHM00057687")
    parser.add_argument("--lat", type=float, default=28.2282)
    parser.add_argument("--lon", type=float, default=112.9388)
    parser.add_argument("--start", default="2024-02-01")
    parser.add_argument("--end", default="2026-09-30")
    parser.add_argument("--thresholds", default="10,25")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    results = [
        evaluate_station(
            args.site, args.station, args.lat, args.lon, args.start, args.end,
            float(threshold), DEFAULT_MODELS,
        )
        for threshold in args.thresholds.split(",")
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写出 -> {out}")


if __name__ == "__main__":
    main()
