"""灾种注册表。

统一描述选题要求的八类气象灾害。`IMPLEMENTED` 表示已完成数据接入、
风险研判与发布闭环；`BASIC` 为可运行的教学试算，不生成预警；`FRAMEWORK` 为扩展设计，
阈值与数据源为规划示意，尚未接入数据。
"""

from __future__ import annotations

HAZARD_STATUS_IMPLEMENTED = "IMPLEMENTED"
HAZARD_STATUS_FRAMEWORK = "FRAMEWORK"
HAZARD_STATUS_BASIC = "BASIC"
TYPHOON_PROXIMITY_KM = 200.0  # 项目教学距离，不是业务预警标准。
SNOW_24H_THRESHOLD_CM = 10.0  # 项目教学阈值，不是官方雪灾预警标准。
LIGHTNING_LTNG_THRESHOLD = 0.05  # 固定教学界线，不是官方信号或概率。

DROUGHT_DRY_DAY_BELOW_MM = 1.0
DROUGHT_STREAK_THRESHOLD_DAYS = 14
HEAT_THRESHOLD_C = 35.0  # Teaching thresholds; not official warning rules.
COLD_THRESHOLD_C = 0.0
WIND_GUST_THRESHOLD_MPS = 17.0

# 订阅里表示「不限灾种」的哨兵值；不能用 NULL，MySQL 唯一索引不把 NULL 视为相等
ALL_HAZARDS = "*"


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
    {
        "code": "THUNDERSTORM",
        "name": "雷电",
        "status": HAZARD_STATUS_IMPLEMENTED,
        "indicator": "6 小时最大 LTNG",
        "unit": "无量纲",
        "thresholds": [{"code": "LIGHTNING_LTNG", "label": "教学触发 ≥", "value": LIGHTNING_LTNG_THRESHOLD}],
        "data_sources": ["NOAA HRRR 原业务归档", "KSTL METAR/SPECI（仅事后核验）"],
        "judgement": "比较 6 个小时的瞬时 LTNG 最大值，并列出达标时次；缺测无法判断。",
        "note": "圣路易斯归档两窗对照。LTNG 不是概率或闪电计数，站点报告不验证落点。",
    },
    {
        "code": "DROUGHT",
        "name": "干旱",
        "status": HAZARD_STATUS_BASIC,
        "indicator": "第 7 天末连续少雨日数",
        "unit": "天",
        "thresholds": [{"code": "DRY_STREAK", "label": "教学持续 ≥", "value": DROUGHT_STREAK_THRESHOLD_DAYS}],
        "data_sources": ["人工输入：签发前连续少雨日数与未来 7 天逐日预报降水"],
        "judgement": "日总降水 < 1.00 mm 延续少雨日数；达到 1.00 mm 则清零。",
        "note": "示例可编辑；缺测无法判断。不创建预警，不用来推断土壤墒情或灾损。",
    },
    {
        "code": "HEATWAVE",
        "name": "高温",
        "status": HAZARD_STATUS_BASIC,
        "indicator": "未来 24 小时最高气温",
        "unit": "°C",
        "thresholds": [{"code": "HEAT_MAX", "label": "教学高温 ≥", "value": HEAT_THRESHOLD_C}],
        "data_sources": ["用户自填逐时气温预报（内置教学示例）"],
        "judgement": "24 个 UTC 整点气温的最大值及达到教学线的时次；有缺测则无法判断",
        "note": "教学试算，不是实时预报或官方高温预警；不生成预警草稿。",
    },
    {
        "code": "LOW_TEMPERATURE",
        "name": "低温",
        "status": HAZARD_STATUS_BASIC,
        "indicator": "未来 24 小时最低气温",
        "unit": "°C",
        "thresholds": [{"code": "COLD_MIN", "label": "教学低温 ≤", "value": COLD_THRESHOLD_C}],
        "data_sources": ["用户自填逐时气温预报（内置教学示例）"],
        "judgement": "24 个 UTC 整点气温的最小值及低于或等于教学线的时次；有缺测则无法判断",
        "note": "不是寒潮预报，也不会生成或发布预警。",
    },
    {
        "code": "WIND_HAIL",
        "name": "风雹",
        "status": HAZARD_STATUS_BASIC,
        "indicator": "未来 6 小时阵风最大值和独立冰雹信号",
        "unit": "m/s 与信号",
        "thresholds": [{"code": "GUST_MAX", "label": "阵风教学线 ≥", "value": WIND_GUST_THRESHOLD_MPS}],
        "data_sources": ["用户自填逐时阵风预报", "用户自填明确雹信号（有 / 无 / 缺测）"],
        "judgement": "分别判断阵风达线与冰雹信号，不从阵风推断冰雹；分量缺测单独标未知",
        "note": "分量阈值试算，不生成预警草稿，不是官方风雹预警。",
    },
]


def hazard_summary() -> dict:
    return {
        "total": len(HAZARDS),
        "implemented": sum(h["status"] == HAZARD_STATUS_IMPLEMENTED for h in HAZARDS),
        "basic": sum(h["status"] == HAZARD_STATUS_BASIC for h in HAZARDS),
        "framework": sum(h["status"] == HAZARD_STATUS_FRAMEWORK for h in HAZARDS),
    }
