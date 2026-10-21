"""构建日尺度建模表：固定提前量预报的 24 小时累计 vs ERA5 代理标签。

为什么用日尺度而不是小时尺度：
  ERA5 逐小时降水在 0.25° 网格上被平滑，短时强降水极值基本消失
  （武汉 2024-02~2026-09 中 >=20mm/h 仅 3 次），无法作为小时极值标签；
  而 24 小时累计与预报的相关性达到 0.83，才是可用的尺度。
"""

from __future__ import annotations

import numpy as np

from ingest import LEAD_DAYS, build_dataset

# 日尺度特征：预报 24 小时累计及其逐小时形态 + 同签发时刻的辅助变量
FEATURES = [
    "fc_sum",     # 预报 24 小时累计降水
    "fc_max",     # 预报单小时最大降水
    "rh_mean",    # 相对湿度
    "cape_mean",  # 对流有效位能
    "dew_mean",   # 露点
    "wind_mean",  # 风速
    "p_mean",     # 海平面气压
    "t_mean",     # 气温
]

HOURLY_TO_DAILY = {
    "precipitation": ("fc_sum", "sum"),
    "relative_humidity_2m": ("rh_mean", "mean"),
    "cape": ("cape_mean", "mean"),
    "dew_point_2m": ("dew_mean", "mean"),
    "wind_speed_10m": ("wind_mean", "mean"),
    "pressure_msl": ("p_mean", "mean"),
    "temperature_2m": ("t_mean", "mean"),
}


def _num(v):
    return np.nan if v is None else float(v)


def build_daily_table(lat: float, lon: float, start: str, end: str, lead_days: int = LEAD_DAYS) -> dict:
    """按 UTC 自然日聚合；任一小时缺测即丢弃该日，保证日累计完整。"""
    data = build_dataset(lat, lon, start, end, lead_days)
    rows = data["rows"]

    by_day: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        by_day.setdefault(r["time"][:10], []).append(i)

    days, feats, labels = [], [], []
    for day in sorted(by_day):
        idx = by_day[day]
        if len(idx) != 24:  # 首尾不完整日
            continue

        values = {}
        complete = True
        for src, (_, _) in HOURLY_TO_DAILY.items():
            series = np.array([_num(rows[i].get(src)) for i in idx], dtype=float)
            if np.isnan(series).any():
                complete = False
                break
            values[src] = series

        label_series = np.array([_num(rows[i].get("label_precip")) for i in idx], dtype=float)
        if not complete or np.isnan(label_series).any():
            continue

        row = {}
        for src, (name, how) in HOURLY_TO_DAILY.items():
            row[name] = float(values[src].sum() if how == "sum" else values[src].mean())
        row["fc_max"] = float(values["precipitation"].max())

        days.append(day)
        feats.append([row[f] for f in FEATURES])
        labels.append(float(label_series.sum()))

    return {
        "meta": {**data["meta"], "resolution": "daily", "features": FEATURES},
        "days": days,
        "X": np.array(feats, dtype=float),
        "label_mm_24h": np.array(labels, dtype=float),
    }
