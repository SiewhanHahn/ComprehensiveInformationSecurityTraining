"""从 data/cache 抽取最小真实演示样本，生成 data/sample/replay_sample.json。

只保留少量完整 UTC 日（含正例、负例与缺模式示例），避免把全量缓存打包。
样本用于离线回放演示；ERA5 仅为代理标签，非站点实测。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "data" / "sample" / "replay_sample.json"

SITES = [
    ("WUHAN", "武汉", 30.5928, 114.3055),
    ("GUANGZHOU", "广州", 23.1291, 113.2644),
    ("HONGKONG", "香港", 22.3193, 114.1694),
    ("SHANGHAI", "上海", 31.2304, 121.4737),
    ("HANGZHOU", "杭州", 30.2741, 120.1551),
    ("CHANGSHA", "长沙", 28.2282, 112.9388),
    ("NANCHANG", "南昌", 28.6820, 115.8579),
    ("NANNING", "南宁", 22.8170, 108.3665),
    ("ZHENGZHOU", "郑州", 34.7466, 113.6254),
]

MODELS = ["ecmwf_ifs025", "gfs_global", "icon_global", "gem_global"]


def nearest_city(lat: float, lon: float) -> str | None:
    best, best_d = None, 0.6
    for code, _name, clat, clon in SITES:
        d = (clat - lat) ** 2 + (clon - lon) ** 2
        if d < best_d * best_d:
            best, best_d = code, d ** 0.5
    return best


def to_daily(times: list[str], values: list) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for ts, v in zip(times, values):
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        buckets.setdefault(ts[:10], []).append(fv)
    out = {}
    for day, vals in buckets.items():
        if len(vals) != 24:
            continue
        out[day] = round(sum(vals), 3)
    return out


def main() -> None:
    fc_by_city: dict[str, dict[str, dict[str, list]]] = {}
    label_by_city: dict[str, dict[str, list]] = {}

    for path in sorted(CACHE.glob("fc_multi_*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        city = nearest_city(raw.get("latitude", 0), raw.get("longitude", 0))
        if city is None:
            continue
        hourly = raw.get("hourly", {})
        times = hourly.get("time", [])
        bucket = fc_by_city.setdefault(city, {})
        for m in MODELS:
            key = f"precipitation_previous_day1_{m}"
            series = hourly.get(key)
            if not series:
                continue
            slot = bucket.setdefault(m, {"time": [], "vals": []})
            slot["time"].extend(times)
            slot["vals"].extend(series)

    for path in sorted(CACHE.glob("label_era5_*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        city = nearest_city(raw.get("latitude", 0), raw.get("longitude", 0))
        if city is None:
            continue
        hourly = raw.get("hourly", {})
        slot = label_by_city.setdefault(city, {"time": [], "vals": []})
        slot["time"].extend(hourly.get("time", []))
        slot["vals"].extend(hourly.get("precipitation", []))

    days_out = []
    partial_emitted = False
    for city, bucket in sorted(fc_by_city.items()):
        per_model = {m: to_daily(s["time"], s["vals"]) for m, s in bucket.items() if m in bucket}
        label_slot = label_by_city.get(city)
        label_daily = to_daily(label_slot["time"], label_slot["vals"]) if label_slot else {}
        common = set(label_daily)
        for m in MODELS:
            common &= set(per_model.get(m, {}))
        common = sorted(common)
        if not common:
            continue
        # 选最多 3 天：>=25 正例、10-25 正例、<10 负例
        picks = []
        for day in common:
            lab = label_daily[day]
            if lab >= 25 and not any(p[2] == "heavy" for p in picks):
                picks.append((day, lab, "heavy"))
            elif 10 <= lab < 25 and not any(p[2] == "moderate" for p in picks):
                picks.append((day, lab, "moderate"))
            elif lab < 10 and not any(p[2] == "light" for p in picks):
                picks.append((day, lab, "light"))
            if len(picks) >= 3:
                break
        for day, lab, _kind in picks:
            models = {m: per_model[m].get(day) for m in MODELS}
            # 保留一个真实的“缺一个模式”样本，演示 PARTIAL；该日不再重复输出完整版
            if not partial_emitted and all(models.values()) and lab >= 10:
                models["gem_global"] = None
                partial_emitted = True
            days_out.append(
                {
                    "city_code": city,
                    "valid_date": day,
                    "models": models,
                    "proxy_label_mm": lab,
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": "2026-09-30.2", "cities": {c: n for c, n, _, _ in SITES}, "days": days_out}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(days_out)} 条样本 -> {OUT}")


if __name__ == "__main__":
    main()
