"""灾种注册表。

统一描述选题要求的八类气象灾害。`IMPLEMENTED` 表示已完成数据接入、
风险研判与发布闭环；`FRAMEWORK` 表示复用同一预警框架的扩展设计，
阈值与数据源为规划示意，尚未接入数据。
"""

from __future__ import annotations

HAZARD_STATUS_IMPLEMENTED = "IMPLEMENTED"
HAZARD_STATUS_FRAMEWORK = "FRAMEWORK"
TYPHOON_PROXIMITY_KM = 200.0  # 项目教学距离，不是业务预警标准。
SNOW_24H_THRESHOLD_CM = 10.0  # 项目教学阈值，不是官方雪灾预警标准。

# 订阅里表示「不限灾种」的哨兵值；不能用 NULL，MySQL 唯一索引不把 NULL 视为相等
ALL_HAZARDS = "*"

def _planned(code: str, name: str, indicator: str, unit: str, data_sources: list[str]) -> dict:
    return {
        "code": code, "name": name, "status": HAZARD_STATUS_FRAMEWORK,
        "indicator": indicator, "unit": unit, "data_sources": data_sources, "thresholds": [],
        "judgement": "待按验收表实现，不输出风险结论",
        "note": "当前仅登记，不能创建此灾种预警；终期仍需实现。",
    }


HAZARDS: list[dict] = [
    {
        "code": "RAINSTORM",
        "name": "暴雨",
        "status": HAZARD_STATUS_IMPLEMENTED,
        "indicator": "24 小时累计降水",
        "unit": "mm",
        "thresholds": [
            {"code": "MODERATE", "label": "中雨", "value": 10.0},
            {"code": "HEAVY", "label": "大雨", "value": 25.0},
            {"code": "STORM", "label": "暴雨", "value": 50.0},
        ],
        "data_sources": [
            "Open-Meteo Previous Runs（ECMWF / GFS / ICON / GEM）",
            "Open-Meteo ERA5（代理标签，非站点实测）",
        ],
        "judgement": "四模式 24 小时累计降水等权融合后与阈值比较",
        "note": "已完成端到端闭环与量化对比（F1 0.7462→0.7900）",
    },
    {
        "code": "TYPHOON",
        "name": "台风",
        "status": HAZARD_STATUS_IMPLEMENTED,
        "indicator": "签发后 24 小时内离散预报点的最小距离",
        "unit": "km",
        "thresholds": [{"code": "PROXIMITY", "label": "教学接近 ≤", "value": TYPHOON_PROXIMITY_KM}],
        "data_sources": ["香港天文台天鸽航运预报（香港科技大学存档）", "香港天文台事后位置表（仅核对）"],
        "judgement": "预报点到城市代表点的球面最小距离；不推断风圈与灾损",
        "note": "已接入一份可追溯历史案例和共用预警闭环，未做统计精度验证。",
    },
    {
        "code": "SNOW_DISASTER",
        "name": "雪灾",
        "status": HAZARD_STATUS_IMPLEMENTED,
        "indicator": "24 小时累计预报降雪",
        "unit": "cm",
        "thresholds": [{"code": "SNOW_24H", "label": "教学触发 ≥", "value": SNOW_24H_THRESHOLD_CM}],
        "data_sources": ["NOAA HRRR 原业务归档 / ECMWF IFS HRES（教学对照）", "NOAA NCEI 地面站天气编码（仅事后核验）"],
        "judgement": "24 个逐时降雪量相加，气温仅作解释；缺测不判风险。",
        "note": "新奥尔良原业务预报达标可制单；济南正反例只回放。站码核对过程，不验证累计量或灾损。",
    },
    _planned("THUNDERSTORM", "雷电", "6 小时雷暴伴随雷电风险", "风险提示", ["已签发雷暴预报信号", "雷暴或闪电记录"]),
    _planned("DROUGHT", "干旱", "未来 7 天少雨持续风险", "天", ["签发前历史降水", "未来 7 天降水预报"]),
    _planned("HEATWAVE", "高温", "未来 24 小时最高气温", "°C", ["逐时气温预报"]),
    _planned("LOW_TEMPERATURE", "低温", "未来 24 小时最低气温", "°C", ["逐时气温预报"]),
    _planned("WIND_HAIL", "风雹", "未来 6 小时阵风及冰雹风险", "m/s / 风险提示", ["阵风预报", "明确的预报冰雹信号"]),
]


def hazard_summary() -> dict:
    implemented = [h for h in HAZARDS if h["status"] == HAZARD_STATUS_IMPLEMENTED]
    return {
        "total": len(HAZARDS),
        "implemented": len(implemented),
        "framework": len(HAZARDS) - len(implemented),
    }
