"""按签发时刻一致的固定提前量，采集历史预报与 ERA5 代理标签。

数据源：
  - previous-runs-api：`*_previous_dayN` 表示"在有效时刻前 N*24 小时签发的预报"，
    因此用它模拟"预警时刻可见的信息"，不会看到未来。
  - archive-api (ERA5)：事后再分析，仅作代理标签，不是站点实测。

依赖：仅标准库 + numpy（环境未安装 pandas/requests/sklearn）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"

PREV_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# 默认提前量：24 小时。改这里即可切换预警提前量。
LEAD_DAYS = 1

FORECAST_VARS = [
    "precipitation",
    "relative_humidity_2m",
    "cape",
    "temperature_2m",
    "dew_point_2m",
    "wind_speed_10m",
    "pressure_msl",
]


def lead_var(name: str, lead_days: int = LEAD_DAYS) -> str:
    """把变量名转成 previous-runs 的固定提前量字段名。"""
    return f"{name}_previous_day{lead_days}"


def _fetch_json(url: str, retries: int = 4, pause: float = 3.0) -> dict:
    """带重试的 GET；对 429/5xx 退避重试，避免把限速当成数据缺失。"""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            last_err = err
            if err.code in (429, 500, 502, 503, 504):
                time.sleep(pause * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as err:
            last_err = err
            time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"请求失败：{url}") from last_err


def _cached(url: str, tag: str) -> dict:
    """按 URL 哈希缓存响应，保证复跑结果一致且减少接口调用。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    path = CACHE_DIR / f"{tag}_{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    payload = _fetch_json(url)
    path.write_text(json.dumps(payload), encoding="utf-8")
    time.sleep(0.5)  # 轻微节流，尊重接口限速
    return payload


def _month_chunks(start: str, end: str, chunk_days: int = 180):
    """把长区间切成若干段，避免单次响应过大或超时。"""
    from datetime import date, timedelta

    cur = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    while cur < stop:
        nxt = min(cur + timedelta(days=chunk_days), stop)
        yield cur.isoformat(), nxt.isoformat()
        cur = nxt


def fetch_forecast(
    lat: float,
    lon: float,
    start: str,
    end: str,
    lead_days: int = LEAD_DAYS,
    chunk_days: int = 180,
) -> dict:
    """采集固定提前量的历史预报，返回 {time: [...], <var>: [...]}。"""
    variables = [lead_var(v, lead_days) for v in FORECAST_VARS]
    merged: dict[str, list] = {}
    for c_start, c_end in _month_chunks(start, end, chunk_days):
        query = urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": c_start,
                "end_date": c_end,
                "hourly": ",".join(variables),
                "timezone": "UTC",
            }
        )
        payload = _cached(f"{PREV_RUNS_URL}?{query}", f"fc_lead{lead_days}")
        hourly = payload.get("hourly", {})
        for key, values in hourly.items():
            merged.setdefault(key, []).extend(values)
    return merged


def fetch_label(lat: float, lon: float, start: str, end: str, chunk_days: int = 180) -> dict:
    """采集 ERA5 降水作为代理标签，返回 {time: [...], precipitation: [...]}。"""
    merged: dict[str, list] = {}
    for c_start, c_end in _month_chunks(start, end, chunk_days):
        query = urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": c_start,
                "end_date": c_end,
                "hourly": "precipitation",
                "models": "era5",
                "timezone": "UTC",
            }
        )
        payload = _cached(f"{ARCHIVE_URL}?{query}", "label_era5")
        hourly = payload.get("hourly", {})
        for key, values in hourly.items():
            merged.setdefault(key, []).extend(values)
    return merged


def fetch_precip_models(
    lat: float,
    lon: float,
    start: str,
    end: str,
    models: list[str],
    lead_days: int = LEAD_DAYS,
    chunk_days: int = 180,
) -> dict:
    """采集多个数值预报模式在同一提前量下的降水预报。

    返回 {model: {"time": [...], "precip": [...]}}，用于多源融合对比。
    指定 models 时接口把模式名作为字段后缀返回。
    """
    var = lead_var("precipitation", lead_days)
    merged: dict[str, dict[str, list]] = {m: {"time": [], "precip": []} for m in models}
    for c_start, c_end in _month_chunks(start, end, chunk_days):
        query = urllib.parse.urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": c_start,
                "end_date": c_end,
                "hourly": var,
                "models": ",".join(models),
                "timezone": "UTC",
            }
        )
        payload = _cached(f"{PREV_RUNS_URL}?{query}", "fc_multi")
        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        for m in models:
            key = f"{var}_{m}"
            if key in hourly:
                merged[m]["time"].extend(times)
                merged[m]["precip"].extend(hourly[key])
    return merged


def build_dataset(lat: float, lon: float, start: str, end: str, lead_days: int = LEAD_DAYS) -> dict:
    """把预报特征与标签按 UTC 时间对齐；只保留两侧都有效的小时。"""
    forecast = fetch_forecast(lat, lon, start, end, lead_days)
    label = fetch_label(lat, lon, start, end)

    label_by_time = dict(zip(label.get("time", []), label.get("precipitation", [])))
    rows = []
    for idx, ts in enumerate(forecast.get("time", [])):
        observed = label_by_time.get(ts)
        if observed is None:
            continue
        row = {"time": ts, "label_precip": observed}
        for var in FORECAST_VARS:
            key = lead_var(var, lead_days)
            series = forecast.get(key)
            row[var] = series[idx] if series and idx < len(series) else None
        rows.append(row)

    return {
        "meta": {
            "latitude": lat,
            "longitude": lon,
            "start": start,
            "end": end,
            "lead_days": lead_days,
            "label_source": "ERA5 reanalysis (proxy, not station observation)",
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="采集固定提前量历史预报与 ERA5 代理标签")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--lead-days", type=int, default=LEAD_DAYS)
    parser.add_argument("--out", required=True, help="输出 JSON 路径")
    args = parser.parse_args()

    data = build_dataset(args.lat, args.lon, args.start, args.end, args.lead_days)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"已写出 {len(data['rows'])} 条对齐样本 -> {out}")


if __name__ == "__main__":
    main()
