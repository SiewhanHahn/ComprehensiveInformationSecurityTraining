from datetime import date


CITIES: dict[str, str] = {
    "WUHAN": "武汉",
    "GUANGZHOU": "广州",
    "HONGKONG": "香港",
    "SHANGHAI": "上海",
    "HANGZHOU": "杭州",
    "CHANGSHA": "长沙",
    "NANCHANG": "南昌",
    "NANNING": "南宁",
    "ZHENGZHOU": "郑州",
}

# The rainfall experiment and /cities stay fixed to the original nine cities.
WARNING_CITIES = {**CITIES, "NEW_ORLEANS": "新奥尔良"}

# 订阅里表示「不限城市」的哨兵值；不能用 NULL，MySQL 唯一索引不把 NULL 视为相等
ALL_CITIES: str = ""

MODEL_DISPLAY: dict[str, str] = {
    "ecmwf_ifs025": "ECMWF",
    "gfs_global": "GFS",
    "icon_global": "ICON",
    "gem_global": "GEM",
}

DEFAULT_MODELS: list[str] = ["ecmwf_ifs025", "gfs_global", "icon_global", "gem_global"]

# 协议固定提前量（见 docs/data-and-method.md）：24 小时
LEAD_HOURS: int = 24

# 历史样本协议日期范围，两端均包含在内。
PROTOCOL_START_DATE = date(2024, 2, 1)
PROTOCOL_END_DATE = date(2026, 9, 30)
