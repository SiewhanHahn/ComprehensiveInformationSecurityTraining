"""灾种注册表。

统一描述选题要求的八类气象灾害。`IMPLEMENTED` 表示已完成端到端数据接入、
融合研判与发布闭环；`FRAMEWORK` 表示复用同一预警框架的扩展设计，
阈值与数据源为规划示意，尚未接入数据。
"""

from __future__ import annotations

HAZARD_STATUS_IMPLEMENTED = "IMPLEMENTED"
HAZARD_STATUS_FRAMEWORK = "FRAMEWORK"

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
        "status": HAZARD_STATUS_FRAMEWORK,
        "indicator": "最大风速 / 阵风",
        "unit": "m/s",
        "thresholds": [
            {"code": "BLUE", "label": "热带风暴", "value": 17.2},
            {"code": "YELLOW", "label": "强热带风暴", "value": 24.5},
            {"code": "ORANGE", "label": "台风", "value": 32.7},
        ],
        "data_sources": ["台风路径与风圈预报", "地面自动站风速"],
        "judgement": "路径、最大风速与影响范围综合判定",
        "note": "扩展框架：需接入台风路径与风圈数据",
    },
    {
        "code": "HEATWAVE",
        "name": "高温",
        "status": HAZARD_STATUS_FRAMEWORK,
        "indicator": "日最高气温",
        "unit": "°C",
        "thresholds": [
            {"code": "YELLOW", "label": "高温", "value": 35.0},
            {"code": "ORANGE", "label": "强高温", "value": 37.0},
            {"code": "RED", "label": "特强高温", "value": 40.0},
        ],
        "data_sources": ["Open-Meteo temperature_2m_max", "站点日最高气温"],
        "judgement": "日最高气温阈值与持续日数",
        "note": "扩展框架：数据变量已明确，尚未接入",
    },
    {
        "code": "DROUGHT",
        "name": "干旱",
        "status": HAZARD_STATUS_FRAMEWORK,
        "indicator": "连续无有效降水日 / SPI",
        "unit": "天",
        "thresholds": [
            {"code": "YELLOW", "label": "轻旱", "value": 10.0},
            {"code": "ORANGE", "label": "中旱", "value": 20.0},
            {"code": "RED", "label": "重旱", "value": 30.0},
        ],
        "data_sources": ["多模式累计降水", "土壤湿度再分析"],
        "judgement": "连续无有效降水日数与标准化降水指数",
        "note": "扩展框架：需补土壤湿度与更长统计窗口",
    },
    {
        "code": "THUNDERSTORM",
        "name": "雷电",
        "status": HAZARD_STATUS_FRAMEWORK,
        "indicator": "对流有效位能 / 闪电密度",
        "unit": "J/kg",
        "thresholds": [
            {"code": "YELLOW", "label": "较易发生", "value": 1000.0},
            {"code": "ORANGE", "label": "易发生", "value": 2500.0},
            {"code": "RED", "label": "极易发生", "value": 4000.0},
        ],
        "data_sources": ["Open-Meteo CAPE", "闪电定位资料"],
        "judgement": "CAPE、抬升指数与闪电频次",
        "note": "扩展框架：多变量融合需单独建模",
    },
    {
        "code": "FOG",
        "name": "大雾",
        "status": HAZARD_STATUS_FRAMEWORK,
        "indicator": "能见度",
        "unit": "m",
        "thresholds": [
            {"code": "YELLOW", "label": "大雾", "value": 1000.0},
            {"code": "ORANGE", "label": "浓雾", "value": 500.0},
            {"code": "RED", "label": "强浓雾", "value": 200.0},
        ],
        "data_sources": ["Open-Meteo visibility", "站点能见度观测"],
        "judgement": "能见度阈值与持续时间",
        "note": "扩展框架：单变量阈值，接入成本较低",
    },
    {
        "code": "FLASH_FLOOD",
        "name": "山洪",
        "status": HAZARD_STATUS_FRAMEWORK,
        "indicator": "面雨量 / 致灾阈值",
        "unit": "mm",
        "thresholds": [
            {"code": "YELLOW", "label": "注意", "value": 50.0},
            {"code": "ORANGE", "label": "警戒", "value": 100.0},
            {"code": "RED", "label": "危险", "value": 150.0},
        ],
        "data_sources": ["多模式流域面雨量", "地形与汇流参数"],
        "judgement": "面雨量结合地形、坡度与汇流时间",
        "note": "扩展框架：需 GIS 地形与流域数据",
    },
    {
        "code": "URBAN_WATERLOGGING",
        "name": "城市内涝",
        "status": HAZARD_STATUS_FRAMEWORK,
        "indicator": "小时雨强 / 积水风险",
        "unit": "mm/h",
        "thresholds": [
            {"code": "YELLOW", "label": "注意", "value": 20.0},
            {"code": "ORANGE", "label": "警戒", "value": 30.0},
            {"code": "RED", "label": "危险", "value": 50.0},
        ],
        "data_sources": ["短时强降水预报", "管网排水能力与下垫面"],
        "judgement": "小时雨强结合管网能力与不透水面比例",
        "note": "扩展框架：需城市管网与下垫面数据",
    },
]


def hazard_summary() -> dict:
    implemented = [h for h in HAZARDS if h["status"] == HAZARD_STATUS_IMPLEMENTED]
    return {
        "total": len(HAZARDS),
        "implemented": len(implemented),
        "framework": len(HAZARDS) - len(implemented),
    }
