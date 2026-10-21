"""统计候选地区的预报覆盖与暴雨事件数，用于选地区、提前量与阈值。

先看覆盖再建模：如果某地区逐月缺测率高或事件太少，直接换地区/提前量，
不要进入建模阶段。
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np

from ingest import LEAD_DAYS, build_dataset

# ERA5 逐小时降水的判暴雨阈值（mm/h）与 24 小时累计阈值（mm/24h）
HOURLY_THRESHOLDS = [5.0, 10.0, 20.0]
DAILY_THRESHOLDS = [25.0, 50.0, 100.0]


def _nan_if_none(values: list) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in values], dtype=float)


def _rolling_24h(values: np.ndarray) -> np.ndarray:
    """24 小时累计；窗口不足或含缺测的位置记为 nan。"""
    out = np.full(values.shape, np.nan)
    for i in range(len(values) - 23):
        window = values[i : i + 24]
        if np.isnan(window).any():
            continue
        out[i] = window.sum()
    return out


def analyse(lat: float, lon: float, start: str, end: str, lead_days: int = LEAD_DAYS) -> dict:
    data = build_dataset(lat, lon, start, end, lead_days)
    rows = data["rows"]
    if not rows:
        return {"meta": data["meta"], "months": {}, "total_rows": 0}

    times = [r["time"] for r in rows]
    fc = _nan_if_none([r["precipitation"] for r in rows])
    lb = _nan_if_none([r["label_precip"] for r in rows])
    fc_valid = ~np.isnan(fc)
    lb_valid = ~np.isnan(lb)

    label_24h = _rolling_24h(lb)
    fc_24h = _rolling_24h(fc)

    by_month: dict[str, dict] = defaultdict(lambda: {"hours": 0, "fc_valid": 0, "label_valid": 0, "paired": 0, "hourly_events": {}, "daily_events": {}})
    for i, ts in enumerate(times):
        month = ts[:7]
        rec = by_month[month]
        rec["hours"] += 1
        rec["fc_valid"] += int(fc_valid[i])
        rec["label_valid"] += int(lb_valid[i])
        rec["paired"] += int(fc_valid[i] and lb_valid[i])
        for thr in HOURLY_THRESHOLDS:
            key = f"{thr:g}mm/h"
            rec["hourly_events"][key] = rec["hourly_events"].get(key, 0) + int(lb_valid[i] and lb[i] >= thr)
        for thr in DAILY_THRESHOLDS:
            key = f"{thr:g}mm/24h"
            hit = (not np.isnan(label_24h[i])) and label_24h[i] >= thr
            rec["daily_events"][key] = rec["daily_events"].get(key, 0) + int(hit)

    summary = {
        "paired_hours": int((fc_valid & lb_valid).sum()),
        "fc_missing_pct": round(100.0 * (1 - fc_valid.mean()), 2) if len(fc) else None,
        "label_missing_pct": round(100.0 * (1 - lb_valid.mean()), 2) if len(lb) else None,
        "hourly_events": {f"{t:g}mm/h": int(np.nansum((lb >= t) & lb_valid)) for t in HOURLY_THRESHOLDS},
        "daily_events": {f"{t:g}mm/24h": int(np.nansum((label_24h >= t))) for t in DAILY_THRESHOLDS},
        "fc24h_max": round(float(np.nanmax(fc_24h)), 1) if not np.isnan(fc_24h).all() else None,
        "label24h_max": round(float(np.nanmax(label_24h)), 1) if not np.isnan(label_24h).all() else None,
    }
    return {"meta": data["meta"], "months": dict(sorted(by_month.items())), "total_rows": len(rows), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="候选地区覆盖与事件统计")
    parser.add_argument("--site", action="append", required=True, help="name:lat:lon，可重复")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--lead-days", type=int, default=LEAD_DAYS)
    parser.add_argument("--months", action="store_true", help="额外打印逐月明细")
    args = parser.parse_args()

    for spec in args.site:
        name, lat, lon = spec.split(":")
        result = analyse(float(lat), float(lon), args.start, args.end, args.lead_days)
        print(f"\n=== {name} ({lat},{lon}) lead={args.lead_days}d ===")
        if not result.get("total_rows"):
            print("  无对齐样本（该地区/时段可能未归档）")
            continue
        s = result["summary"]
        print(f"  对齐小时={s['paired_hours']}  预报缺测={s['fc_missing_pct']}%  标签缺测={s['label_missing_pct']}%")
        print(f"  预报24h最大={s['fc24h_max']}mm  标签24h最大={s['label24h_max']}mm")
        print(f"  逐小时事件: {s['hourly_events']}")
        print(f"  24h累计事件: {s['daily_events']}")
        if args.months:
            for month, rec in result["months"].items():
                print(f"    {month}: hours={rec['hours']} fc_valid={rec['fc_valid']} label_valid={rec['label_valid']} paired={rec['paired']} events={rec['daily_events']}")


if __name__ == "__main__":
    main()
