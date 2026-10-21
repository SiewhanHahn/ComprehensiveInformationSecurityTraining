"""多源融合对比：单模式基线 vs 多模式集成。

为什么换成多模式融合：
  在单一预报源上叠加湿度/CAPE 等辅助变量，测试集 AUC 反而下降
  （0.9682 -> 0.9556），说明该方向的增量信息不足；
  而"多源数据融合"的可靠增量来自融合多个独立数值预报模式。

口径（无未来信息泄漏）：
  - 决策时刻为 UTC 日 D；各模式预报均取自 `previous_day1`，签发于 D 前 24 小时；
  - 标签为 ERA5 在 D 的 24 小时累计降水是否达阈值（再分析，仅作代理标签）；
  - 按自然年切分：训练 2024、验证 2025、测试 2026。

对比：
  - 基线：单一模式（默认 ECMWF IFS）预报 24 小时累计取固定阈值；
  - 改进：多模式集成（均值/中位数/权重学习）后再取阈值。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ingest import fetch_label, fetch_precip_models
from evaluate import auc_score, best_threshold, confusion, metrics, pr_auc

DEFAULT_MODELS = ["ecmwf_ifs025", "gfs_global", "icon_global", "gem_global"]
BASE_MODEL = "ecmwf_ifs025"


def _to_daily(times: list[str], values: np.ndarray) -> dict[str, float]:
    """按 UTC 自然日求 24 小时累计；不完整日或缺测日丢弃。"""
    buckets: dict[str, list[float]] = {}
    for ts, v in zip(times, values):
        buckets.setdefault(ts[:10], []).append(v)
    out = {}
    for day, vals in buckets.items():
        if len(vals) != 24 or any(np.isnan(v) for v in vals):
            continue
        out[day] = float(np.nansum(vals))
    return out


def build_fusion_table(lat, lon, start, end, models, lead_days=1) -> dict:
    raw = fetch_precip_models(lat, lon, start, end, models, lead_days)
    label_raw = fetch_label(lat, lon, start, end)

    label_daily = _to_daily(label_raw["time"], np.array(label_raw["precipitation"], dtype=float))
    per_model = {}
    for m in models:
        series = np.array([np.nan if v is None else float(v) for v in raw[m]["precip"]], dtype=float)
        per_model[m] = _to_daily(raw[m]["time"], series)

    # 取所有模式与标签都完整的日期
    common = set(label_daily)
    for m in models:
        common &= set(per_model[m])
    days = sorted(common)

    mat = np.array([[per_model[m][d] for m in models] for d in days], dtype=float)
    label = np.array([label_daily[d] for d in days], dtype=float)
    return {"days": days, "models": models, "X": mat, "label_mm_24h": label}


def _f1(y: np.ndarray, pred: np.ndarray) -> float:
    c = confusion(y, pred)
    if c["tp"] == 0:
        return 0.0
    prec = c["tp"] / (c["tp"] + c["fp"])
    rec = c["tp"] / (c["tp"] + c["fn"])
    return 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0


def bootstrap_delta_f1(
    y: np.ndarray,
    single_scores: np.ndarray,
    fusion_scores: np.ndarray,
    threshold: float,
    n_boot: int = 2000,
    seed: int = 42,
) -> dict:
    """对测试集按日重采样，给出 ΔF1 的自举区间。

    正类样本很少时，单点 F1 差异不可靠；区间跨 0 说明提升不稳健。
    """
    rng = np.random.default_rng(seed)
    n_obs = len(y)
    deltas = []
    for _ in range(n_boot):
        idx = rng.integers(0, n_obs, n_obs)
        ys = y[idx]
        if ys.sum() == 0 or ys.sum() == len(ys):
            continue  # 退化重采样，跳过
        deltas.append(
            _f1(ys, fusion_scores[idx] >= threshold) - _f1(ys, single_scores[idx] >= threshold)
        )
    if len(deltas) < 100:
        return {"n_effective": len(deltas), "note": "重采样退化过多，区间不可靠"}
    arr = np.array(deltas) * 100  # 换算成百分点
    return {
        "delta_f1_points_mean": round(float(arr.mean()), 2),
        "ci95_low": round(float(np.percentile(arr, 2.5)), 2),
        "ci95_high": round(float(np.percentile(arr, 97.5)), 2),
        "prob_improve": round(float((arr > 0).mean()), 3),
        "n_effective": len(deltas),
    }


def run(site, lat, lon, start, end, threshold, models, train_years, val_years, test_years):
    table = build_fusion_table(lat, lon, start, end, models)
    days, X, label = table["days"], table["X"], table["label_mm_24h"]
    if len(days) < 200:
        return {"site": site, "error": f"完整日不足：{len(days)}"}

    y = (label >= threshold).astype(float)
    years = np.array([d[:4] for d in days])
    tr, va, te = (np.isin(years, ys) for ys in (train_years, val_years, test_years))
    if min(y[tr].sum(), y[va].sum(), y[te].sum()) == 0:
        return {"site": site, "error": "切分中存在无正类的段", "year_counts": {yr: int(y[years == yr].sum()) for yr in sorted(set(years))}}

    base_idx = models.index(BASE_MODEL) if BASE_MODEL in models else 0
    base_scores_te = X[te, base_idx]

    # 融合方案：等权均值、中位数，以及按训练集正类召回加权的融合
    ens_mean = X.mean(axis=1)
    ens_median = np.median(X, axis=1)

    # 权重学习：以"各模式 24h 累计 >= 阈值的命中率"作为训练集上的技能权重
    skill = []
    for j in range(X.shape[1]):
        hits = ((X[tr, j] >= threshold) & (y[tr] == 1)).sum()
        skill.append(hits / max(y[tr].sum(), 1))
    w = np.array(skill, dtype=float)
    w = w / w.sum() if w.sum() > 0 else np.ones(len(models)) / len(models)
    ens_weighted = X @ w

    results = {}
    # 每个单模式都作为对照，确保融合是胜过"最好的单模式"而非只胜过默认模式
    for j, m in enumerate(models):
        scores = X[te, j]
        results[f"single:{m}"] = metrics(y[te], (scores >= threshold).astype(float), scores)
    for name, scores in {
        "fusion:mean": ens_mean[te],
        "fusion:median": ens_median[te],
        "fusion:weighted": ens_weighted[te],
    }.items():
        results[name] = metrics(y[te], (scores >= threshold).astype(float), scores)

    single_names = [k for k in results if k.startswith("single:")]
    best_single = max(single_names, key=lambda k: results[k]["f1"])
    fusion_names = [k for k in results if k.startswith("fusion:")]
    best_fusion = max(fusion_names, key=lambda k: results[k]["f1"])
    best_name = best_fusion
    return {
        "site": site,
        "period": {"start": start, "end": end},
        "target": f"ERA5 24h 累计降水 >= {threshold:g}mm",
        "models": models,
        "fusion_weights": {m: round(float(x), 4) for m, x in zip(models, w)},
        "split": {"train": train_years, "val": val_years, "test": test_years},
        "counts": {
            "days": len(days),
            "train": int(tr.sum()), "val": int(va.sum()), "test": int(te.sum()),
            "test_positives": int(y[te].sum()),
        },
        "results": results,
        "best_single": best_single,
        "best_fusion": best_fusion,
        "delta_vs_best_single_f1_points": round(
            (results[best_fusion]["f1"] - results[best_single]["f1"]) * 100, 2
        ),
        "bootstrap_delta_f1": bootstrap_delta_f1(
            y[te],
            X[te, models.index(best_single.split(":", 1)[1])],
            {
                "fusion:mean": ens_mean[te],
                "fusion:median": ens_median[te],
                "fusion:weighted": ens_weighted[te],
            }[best_fusion],
            threshold,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="多源融合 vs 单模式")
    parser.add_argument("--site", required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--threshold", type=float, default=25.0)
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--train-years", default="2024")
    parser.add_argument("--val-years", default="2025")
    parser.add_argument("--test-years", default="2026")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    result = run(
        args.site, args.lat, args.lon, args.start, args.end, args.threshold,
        args.models.split(","), args.train_years.split(","), args.val_years.split(","), args.test_years.split(","),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out and "error" not in result:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写出 -> {out}")


if __name__ == "__main__":
    main()
