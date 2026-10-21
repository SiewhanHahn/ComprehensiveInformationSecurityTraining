"""多站点合并评估：提高统计功效，并给出固定的基线协议。

为什么合并：
  单站点测试年正类只有 11~18 个，ΔF1 的自举区间都跨 0，无法单独下结论。
  把多个站点同一时段的样本合并后，正类数量显著增加，结论更稳健。

固定协议（避免"每站挑最好单模式"的选择偏差）：
  - 基线：ECMWF IFS 单模式预报 24 小时累计取固定阈值；
  - 改进：ECMWF/GFS/ICON/GEM 四模式等权融合后取同一阈值；
  - 两方案在同一批样本上评估。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from evaluate import metrics
from fusion import DEFAULT_MODELS, _f1, bootstrap_delta_f1, build_fusion_table

SITES = [
    ("武汉", 30.5928, 114.3055),
    ("广州", 23.1291, 113.2644),
    ("香港", 22.3193, 114.1694),
    ("上海", 31.2304, 121.4737),
    ("杭州", 30.2741, 120.1551),
    ("长沙", 28.2282, 112.9388),
    ("南昌", 28.6820, 115.8579),
    ("南宁", 22.8170, 108.3665),
    ("郑州", 34.7466, 113.6254),
]
BASE_MODEL = "ecmwf_ifs025"


def collect(sites, start, end, test_years, models):
    """汇总各站点测试年的日样本。"""
    ys, base_scores, fusion_scores, site_tags = [], [], [], []
    for name, lat, lon in sites:
        table = build_fusion_table(lat, lon, start, end, models)
        days, X, label = table["days"], table["X"], table["label_mm_24h"]
        years = np.array([d[:4] for d in days])
        mask = np.isin(years, test_years)
        if mask.sum() == 0:
            continue
        j = models.index(BASE_MODEL)
        ys.append(label[mask])
        base_scores.append(X[mask, j])
        fusion_scores.append(X[mask].mean(axis=1))
        site_tags.extend([name] * int(mask.sum()))
    return (
        np.concatenate(ys),
        np.concatenate(base_scores),
        np.concatenate(fusion_scores),
        np.array(site_tags),
    )


def run(sites, start, end, threshold, test_years, models):
    label, base_scores, fusion_scores, tags = collect(sites, start, end, test_years, models)
    y = (label >= threshold).astype(float)

    base_pred = (base_scores >= threshold).astype(float)
    fusion_pred = (fusion_scores >= threshold).astype(float)

    per_site = {}
    for name in sorted(set(tags)):
        m = tags == name
        per_site[name] = {
            "n": int(m.sum()),
            "positives": int(y[m].sum()),
            "baseline_f1": round(_f1(y[m], base_pred[m]), 4),
            "fusion_f1": round(_f1(y[m], fusion_pred[m]), 4),
        }

    return {
        "sites": [s[0] for s in sites],
        "threshold_mm_24h": threshold,
        "test_years": test_years,
        "models": models,
        "baseline_protocol": f"single:{BASE_MODEL}",
        "fusion_protocol": "fusion:mean",
        "pooled": {
            "n": int(len(y)),
            "positives": int(y.sum()),
            "baseline": metrics(y, base_pred, base_scores),
            "fusion": metrics(y, fusion_pred, fusion_scores),
        },
        "delta_f1_points": round((_f1(y, fusion_pred) - _f1(y, base_pred)) * 100, 2),
        "bootstrap": bootstrap_delta_f1(y, base_scores, fusion_scores, threshold),
        "per_site": per_site,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="多站点合并评估")
    parser.add_argument("--start", default="2024-02-01")
    parser.add_argument("--end", default="2026-09-30")
    parser.add_argument("--thresholds", default="10,25")
    parser.add_argument("--test-years", default="2026")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    outputs = []
    for thr in [float(t) for t in args.thresholds.split(",")]:
        result = run(SITES, args.start, args.end, thr, args.test_years.split(","), args.models.split(","))
        outputs.append(result)
        p = result["pooled"]
        b = result["bootstrap"]
        print(f"\n=== 合并评估  阈值 {thr:g}mm/24h  测试年 {args.test_years} ===")
        print(f"  样本 n={p['n']}  正类={p['positives']}")
        print(f"  基线({result['baseline_protocol']}): F1={p['baseline']['f1']} 精确率={p['baseline']['precision']} 召回={p['baseline']['recall']} 误报率={p['baseline']['fpr']} AUC={p['baseline']['auc']}")
        print(f"  融合({result['fusion_protocol']}): F1={p['fusion']['f1']} 精确率={p['fusion']['precision']} 召回={p['fusion']['recall']} 误报率={p['fusion']['fpr']} AUC={p['fusion']['auc']}")
        print(f"  ΔF1={result['delta_f1_points']:+.2f} 点  95%区间=[{b['ci95_low']}, {b['ci95_high']}]  P(提升)={b['prob_improve']}")
        for name, rec in result["per_site"].items():
            print(f"    {name}: n={rec['n']} 正类={rec['positives']} 基线F1={rec['baseline_f1']} 融合F1={rec['fusion_f1']}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写出 -> {out}")


if __name__ == "__main__":
    main()
