"""诊断脚本：判断固定提前量预报在不同目标定义下是否具备可用技能。

用途：在选定目标与阈值之前先看 AUC 与正类数，避免把"无技能"当成"提升"。
"""

from __future__ import annotations

import argparse

import numpy as np

from ingest import build_dataset


def auc(scores: np.ndarray, y: np.ndarray) -> float:
    """秩和法计算 AUC；样本含并列值时用平均秩。"""
    pos, neg = scores[y == 1], scores[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order), dtype=float)
    ranks[order] = np.arange(1, len(order) + 1)
    # 平均秩处理并列
    allv = np.concatenate([pos, neg])
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    avg = np.zeros(len(counts))
    start = 0
    for i, c in enumerate(counts):
        avg[i] = (start + 1 + start + c) / 2
        start += c
    ranks = avg[inv]
    r_pos = ranks[: len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def aggregate_daily(times: list[str], values: dict[str, np.ndarray]) -> tuple[list[str], dict[str, np.ndarray]]:
    """把逐小时序列按 UTC 自然日聚合；任一小时缺测则当日记为缺测。"""
    days: dict[str, list[int]] = {}
    for i, ts in enumerate(times):
        days.setdefault(ts[:10], []).append(i)

    out_days, out_vals = [], {k: [] for k in values}
    for day in sorted(days):
        idx = days[day]
        if len(idx) != 24:  # 首尾不完整日直接丢弃
            continue
        ok = True
        for key, series in values.items():
            window = series[idx]
            if np.isnan(window).any():
                ok = False
                break
        if not ok:
            continue
        out_days.append(day)
        for key, series in values.items():
            out_vals[key].append(float(series[idx].sum() if key.endswith("_sum") else series[idx].mean()))
    return out_days, {k: np.array(v, dtype=float) for k, v in out_vals.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="固定提前量预报的技能探测")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--lead-days", type=int, default=1)
    args = parser.parse_args()

    data = build_dataset(args.lat, args.lon, args.start, args.end, args.lead_days)
    rows = data["rows"]
    times = [r["time"] for r in rows]
    fc = np.array([np.nan if r["precipitation"] is None else r["precipitation"] for r in rows], dtype=float)
    lb = np.array([np.nan if r["label_precip"] is None else r["label_precip"] for r in rows], dtype=float)
    ok = ~np.isnan(fc) & ~np.isnan(lb)
    times = [t for t, k in zip(times, ok) if k]
    fc, lb = fc[ok], lb[ok]

    print(f"有效小时={len(fc)}")

    print("\n[小时目标] 预报小时降水 vs ERA5 小时降水")
    for thr in (2.0, 5.0, 10.0):
        y = (lb >= thr).astype(float)
        print(f"  阈值 {thr:>4}mm/h  正类={int(y.sum()):>5}  AUC={auc(fc, y):.3f}")

    print("\n[24小时累计目标] 预报日累计 vs ERA5 日累计")
    days, agg = aggregate_daily(times, {"fc_sum": fc, "label_sum": lb})
    fcd, lbd = agg["fc_sum"], agg["label_sum"]
    print(f"  完整日数={len(days)}")
    for thr in (10.0, 25.0, 50.0, 100.0):
        y = (lbd >= thr).astype(float)
        print(f"  阈值 {thr:>5}mm/24h 正类={int(y.sum()):>4}  AUC={auc(fcd, y):.3f}")

    print("\n[逐年事件数] 用于确认按年份切分后每段都有正类")
    for year in sorted({d[:4] for d in days}):
        idx = [i for i, d in enumerate(days) if d.startswith(year)]
        sub = lbd[idx]
        counts = {f"{t:g}mm": int((sub >= t).sum()) for t in (10.0, 25.0, 50.0)}
        print(f"  {year}: 天数={len(idx):>4} 事件={counts}")

    print("\n[参考] 日累计相关性")
    print(f"  pearson(fc_sum,label_sum)={np.corrcoef(fcd, lbd)[0,1]:.3f}")
    print(f"  pearson(fc,label)小时={np.corrcoef(fc, lb)[0,1]:.3f}")


if __name__ == "__main__":
    main()
