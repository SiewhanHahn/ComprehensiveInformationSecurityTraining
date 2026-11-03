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
