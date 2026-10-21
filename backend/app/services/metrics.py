import json
from pathlib import Path
from threading import Lock

from ..schemas import ExperimentDetail, ExperimentListItem, MetricBundle

POOLED_PATH = Path("data/results/pooled.json")

LABEL_NOTE = (
    "标签为 ERA5 再分析日累计降水（代理标签，非站点实测）；"
    "教学风险等级不代表国家气象台官方预警信号。"
)

_cache_lock = Lock()
_cache_mtime: float | None = None
_cache_data: list[dict] | None = None


def _load() -> list[dict]:
    """解析并缓存 pooled.json，文件 mtime 变化时才重新读取。"""
    global _cache_mtime, _cache_data
    if not POOLED_PATH.exists():
        return []
    mtime = POOLED_PATH.stat().st_mtime
    with _cache_lock:
        if _cache_data is None or _cache_mtime != mtime:
            with POOLED_PATH.open("r", encoding="utf-8") as f:
                _cache_data = json.load(f)
            _cache_mtime = mtime
        return _cache_data


def _version(threshold: float) -> str:
    return f"{int(threshold)}mm"


def list_experiments() -> list[ExperimentListItem]:
    result = []
    for item in _load():
        pooled = item["pooled"]
        result.append(
            ExperimentListItem(
                version=_version(item["threshold_mm_24h"]),
                threshold_mm=item["threshold_mm_24h"],
                test_years=item["test_years"],
                n=pooled["n"],
                positives=pooled["positives"],
                delta_f1=item.get("delta_f1_points"),
            )
        )
    return result


def get_experiment(version: str) -> ExperimentDetail | None:
    for item in _load():
        if _version(item["threshold_mm_24h"]) != version:
            continue
        pooled = item["pooled"]
        b = pooled["baseline"]
        f = pooled["fusion"]
        boot = item.get("bootstrap", {})

        def bundle(m: dict) -> MetricBundle:
            c = m["confusion"]
            return MetricBundle(
                precision=m["precision"],
                recall=m["recall"],
                fpr=m["fpr"],
                f1=m["f1"],
                auc=m["auc"],
                tp=c["tp"],
                fp=c["fp"],
                fn=c["fn"],
                tn=c["tn"],
            )

        return ExperimentDetail(
            version=_version(item["threshold_mm_24h"]),
            threshold_mm=item["threshold_mm_24h"],
            test_years=item["test_years"],
            sites=item["sites"],
            n=pooled["n"],
            positives=pooled["positives"],
            baseline=bundle(b),
            fusion=bundle(f),
            delta_f1=item.get("delta_f1_points", 0.0),
            bootstrap_interval=[boot.get("ci95_low", 0.0), boot.get("ci95_high", 0.0)],
            p_improve=boot.get("prob_improve", 0.0),
            label_note=LABEL_NOTE,
        )
    return None
