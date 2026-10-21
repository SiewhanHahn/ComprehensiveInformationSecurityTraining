"""基线 vs 改进方法对比：日尺度 24 小时累计预警，按年份切分。

实验口径（无未来信息泄漏）：
  - 决策时刻为 UTC 日 D；特征全部来自 `previous_day1`，即签发于 D 前 24 小时的预报；
  - 标签为 ERA5 在 D 的 24 小时累计降水是否达到阈值（ERA5 为再分析，仅作代理标签）；
  - 按自然年切分训练/验证/测试，保证每段都覆盖完整雨季。

对比：
  - 基线：业务上常见的做法——对预报 24 小时累计降水直接取固定阈值；
  - 改进：多变量逻辑回归（numpy 实现），阈值在验证年上校准。
两者在同一测试年、同一标签上评估，测试集只评一次。

依赖：仅标准库 + numpy。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from dataset import FEATURES, build_daily_table


# ---------- 指标 ----------

def auc_score(scores: np.ndarray, y: np.ndarray) -> float:
    """秩和法 AUC，并列值取平均秩。"""
    pos, neg = scores[y == 1], scores[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
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


def pr_auc(scores: np.ndarray, y: np.ndarray) -> float:
    """平均精度（PR 曲线下面积），不平衡数据下比 ROC 更能反映可用性。"""
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-scores)
    y_sorted = y[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1 - y_sorted)
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / y.sum()
    recall_prev = np.concatenate([[0.0], recall[:-1]])
    return float(np.sum((recall - recall_prev) * precision))


def confusion(y: np.ndarray, pred: np.ndarray) -> dict:
    return {
        "tp": int(((y == 1) & (pred == 1)).sum()),
        "fp": int(((y == 0) & (pred == 1)).sum()),
        "fn": int(((y == 1) & (pred == 0)).sum()),
        "tn": int(((y == 0) & (pred == 0)).sum()),
    }


def metrics(y: np.ndarray, pred: np.ndarray, scores: np.ndarray | None = None) -> dict:
    c = confusion(y, pred)
    prec = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else 0.0
    rec = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else 0.0
    fpr = c["fp"] / (c["fp"] + c["tn"]) if (c["fp"] + c["tn"]) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    out = {
        "confusion": c,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "fpr": round(fpr, 4),
        "f1": round(f1, 4),
        "positives": int(y.sum()),
        "negatives": int((y == 0).sum()),
    }
    if scores is not None:
        out["auc"] = round(auc_score(scores, y), 4)
        out["pr_auc"] = round(pr_auc(scores, y), 4)
    return out


# ---------- 模型 ----------

def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 2000, lr: float = 0.3) -> dict:
    """带 L2 与类别权重的逻辑回归；标准化参数随模型保存，避免评估期泄漏。"""
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std == 0] = 1.0
    Z = np.hstack([np.ones((len(X), 1)), (X - mean) / std])

    n, d = Z.shape
    w = np.zeros(d)
    pos, neg = max(y.sum(), 1.0), max((1 - y).sum(), 1.0)
    weights = np.where(y == 1, 0.5 * n / pos, 0.5 * n / neg)

    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Z @ w, -30, 30)))
        grad = Z.T @ ((p - y) * weights) / n
        grad[1:] += l2 * w[1:] / n
        w -= lr * grad
    return {"w": w, "mean": mean, "std": std}


def predict_logistic(model: dict, X: np.ndarray) -> np.ndarray:
    Z = np.hstack([np.ones((len(X), 1)), (X - model["mean"]) / model["std"]])
    return 1.0 / (1.0 + np.exp(-np.clip(Z @ model["w"], -30, 30)))


def best_threshold(scores: np.ndarray, y: np.ndarray) -> float:
    """在验证集上按 F1 选阈值；候选覆盖全部唯一分数，避免分位数范围漏掉最优点。"""
    if y.sum() == 0:
        return float(np.median(scores))
    candidates = np.unique(scores)
    best, best_f1 = float(candidates[0]), -1.0
    for thr in candidates:
        pred = (scores >= thr).astype(float)
        c = confusion(y, pred)
        if c["tp"] == 0:
            continue
        prec = c["tp"] / (c["tp"] + c["fp"])
        rec = c["tp"] / (c["tp"] + c["fn"])
        f1 = 2 * prec * rec / (prec + rec)
        if f1 > best_f1:
            best, best_f1 = float(thr), f1
    return best


# ---------- 主流程 ----------

def run(site, lat, lon, start, end, threshold, lead_days, train_years, val_years, test_years):
    table = build_daily_table(lat, lon, start, end, lead_days)
    days, X, label = table["days"], table["X"], table["label_mm_24h"]
    if len(days) == 0:
        return {"site": site, "error": "无完整日样本"}

    y = (label >= threshold).astype(float)
    years = np.array([d[:4] for d in days])

    tr = np.isin(years, train_years)
    va = np.isin(years, val_years)
    te = np.isin(years, test_years)
    if y[tr].sum() == 0 or y[va].sum() == 0 or y[te].sum() == 0:
        return {
            "site": site,
            "error": "某个切分中没有正类，需调整切分或阈值",
            "year_positive_counts": {
                yr: int(y[years == yr].sum()) for yr in sorted(set(years))
            },
        }

    # 基线：业务固定阈值法——预报 24 小时累计 >= 阈值即发布预警
    fc_idx = FEATURES.index("fc_sum")
    base_pred_te = (X[te, fc_idx] >= threshold).astype(float)

    # 改进：多变量逻辑回归，阈值在验证年校准
    model = fit_logistic(X[tr], y[tr])
    val_scores = predict_logistic(model, X[va])
    thr = best_threshold(val_scores, y[va])
    te_scores = predict_logistic(model, X[te])
    imp_pred_te = (te_scores >= thr).astype(float)

    base_m = metrics(y[te], base_pred_te, X[te, fc_idx])
    imp_m = metrics(y[te], imp_pred_te, te_scores)

    # 特征重要性（标准化后权重绝对值），便于报告解释
    weights = {f: round(float(w), 4) for f, w in zip(FEATURES, model["w"][1:])}

    return {
        "site": site,
        "period": {"start": start, "end": end},
        "lead_days": lead_days,
        "target": f"ERA5 24h 累计降水 >= {threshold:g}mm",
        "split": {"train": train_years, "val": val_years, "test": test_years},
        "counts": {
            "total_days": int(len(days)),
            "train": int(tr.sum()), "val": int(va.sum()), "test": int(te.sum()),
            "test_positives": int(y[te].sum()),
        },
        "test_period": {"from": days[int(np.argmax(te))], "to": days[len(days) - 1 - int(np.argmax(te[::-1]))]},
        "baseline": {**base_m, "rule": f"fc_sum >= {threshold:g}mm"},
        "improved": {**imp_m, "calibrated_threshold": round(float(thr), 4)},
        "delta": {
            "f1_points": round((imp_m["f1"] - base_m["f1"]) * 100, 2),
            "recall_points": round((imp_m["recall"] - base_m["recall"]) * 100, 2),
            "fpr_points": round((imp_m["fpr"] - base_m["fpr"]) * 100, 2),
        },
        "feature_weights": weights,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="日尺度预警：基线 vs 改进")
    parser.add_argument("--site", required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--threshold", type=float, default=25.0, help="24 小时累计阈值 mm")
    parser.add_argument("--lead-days", type=int, default=1)
    parser.add_argument("--train-years", default="2024")
    parser.add_argument("--val-years", default="2025")
    parser.add_argument("--test-years", default="2026")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    result = run(
        args.site, args.lat, args.lon, args.start, args.end, args.threshold, args.lead_days,
        args.train_years.split(","), args.val_years.split(","), args.test_years.split(","),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.out and "error" not in result:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写出 -> {out}")


if __name__ == "__main__":
    main()
