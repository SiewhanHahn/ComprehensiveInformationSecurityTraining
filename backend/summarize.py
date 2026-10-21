"""把 data/results 下的融合评估结果汇总成报告可用的对照表。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results"


def load_all() -> list[dict]:
    out = []
    for path in sorted(RESULTS.glob("*_fusion_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "error" in data:
            continue
        data["_file"] = path.name
        out.append(data)
    return out


def main() -> None:
    runs = load_all()
    if not runs:
        print("没有可汇总的结果，请先运行 fusion.py")
        return

    header = f"{'站点':<6}{'阈值':>6}{'正类':>6}{'最优单模式F1':>14}{'融合F1':>10}{'ΔF1':>8}{'单模式AUC':>11}{'融合AUC':>10}"
    print(header)
    print("-" * len(header))

    for r in sorted(runs, key=lambda x: (x["site"], float(x["target"].split(">=")[1].replace("mm", "")))):
        thr = r["target"].split(">=")[1].replace("mm", "").strip()
        single = r["results"][r["best_single"]]
        fusion = r["results"][r["best_fusion"]]
        print(
            f"{r['site']:<6}{thr:>6}{r['counts']['test_positives']:>6}"
            f"{single['f1']:>14.4f}{fusion['f1']:>10.4f}"
            f"{r['delta_vs_best_single_f1_points']:>+8.2f}"
            f"{single['auc']:>11.4f}{fusion['auc']:>10.4f}"
        )

    print("\n说明：ΔF1 = 融合F1 − 最优单模式F1（百分点）。基线取所有单模式中 F1 最高者，")
    print("因此结果是对比'最好的单模式'而非默认模式，避免高估融合收益。")


if __name__ == "__main__":
    main()
