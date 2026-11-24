# C2 雪灾：原业务数据与历史对照的来源核对

**核对时间：2026-11-24（UTC）。** 这是历史教学案例，不是实时预报、官方信号或统计精度验证。

## 可制单案例：2025-01-21 新奥尔良

- 预报用 NOAA NCEP [HRRR CONUS 原业务 GRIB2 公共档案](https://registry.opendata.aws/noaa-hrrr-pds/)，起报 **2025-01-20 18:00 UTC**，取 3 km 网格距机场站最近的格点 `29.997934, −90.285677`（约 0.77 km）。核对 `f12`–`f36` 文件内 GRIB 初始化与预报步长；[f36 索引](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20250120/conus/hrrr.t18z.wrfsfcf36.grib2.idx)与同路径各步长原文件可重查。原文件 HTTP `Last-Modified` 介于 1 月 20 日 **19:06:20–19:34:56 UTC**，均早于 1 月 21 日 **06:00 UTC** 的研判起点。有档案时间证据，不将起报时间冒称签发或投递时间。
- [NCEP GRIB2 参数表](https://www.nco.ncep.noaa.gov/pmb/docs/grib2/grib2_doc/grib2_table4-2-0-1.shtml)中 `0/1/29 ASNOW` 为米制累计降雪。把从起报累计的米值换算为厘米，保留 0.01 cm 后用相邻步长差得到逐时新增量；同点 2 米气温由 K 转为 °C。`f13` 至 `f36` 的 24 小时和为 **20.19 cm**（`f36 0.20194 m − f12 0 m`），最低温 **−2.4 °C**，达到 **10.00 cm** 教学阈值。[提取记录](evidence/c2-snow-hrrr-extract.csv)保留原数值、UTC 档案时间、索引字节范围，可用 `Range` 对照 GRIB，不随项目分发 GRIB 原文件。
- 事后独立使用 [NOAA NCEI ISD 新奥尔良机场站 72231012916](https://noaa-global-hourly-pds.s3.amazonaws.com/2025/72231012916.csv)，站坐标 `29.99755, −90.27772`。同窗 `(1 月 21 日 06:00, 1 月 22 日 06:00] UTC` 中，取起点之后、终点以内 `FM-12/MW1` 的 5 条有效记录；18:00、21:00 UTC 的 `75,1` 表示观测时连续强降雪。只确认降雪现象，不拿站码、总降水或地面积雪深度验证 20.19 cm；缺码不补零、不进入正式预警快照。

## 只回放对照：2025-03-02 与 2025-03-04 济南

- Open-Meteo [Single Runs API](https://open-meteo.com/en/docs/single-runs-api)，ECMWF IFS HRES `ecmwf_ifs`。查询点取 NOAA 济南国家站 `36.6833333°N, 116.9833333°E`；API 返回所用模式网格 `36.66081°N, 117.011795°E`，距站约 3.6 km。服务端记录请求点与模式网格；不把网格值称为站点实测。
- 批次起报是模式初始化，并不是公开接口发布时间。回放以起报后 **12 小时**为保守研判时刻：参考 ECMWF [Set I 直出场分发日程](https://www.ecmwf.int/en/forecasts/datasets/set-i) 中 12 UTC 批次前 90 小时产品约 17:45–18:12 UTC 分发。ECMWF [49R1 升级记录](https://confluence.ecmwf.int/display/FCST/Implementation+of+IFS+Cycle+49r1)显示该周期于 2024-11-12 开始业务运行。Single Runs 以初始化时间查询，该 API 的长档期包含早期 hindcasts，且未附本案例逐条原始发布回执；不能证明 API 在当日何时对公众上线。回放固定起报批次，不引入后续起报、事后观测或实时 API 结果。12 小时是回放假设，不是这两个档案点值的已证实可用时刻；两个济南案例均不能制单。
- [预报变量定义](https://open-meteo.com/en/docs)：每个 `snowfall` 值是标签时刻**前一小时**的模式降雪量（`cm`），`temperature_2m` 是该时次的 2 米气温（`°C`）。例如 03:00 的 0.14 cm 对应 02:00–03:00。取 24 个 `(起点, 终点]` 标签相加，不把降水水当量或 `snow_depth` 相加。

| 案例 | 模式起报 UTC | 研判窗口 UTC（接受小时末标签） | 计算结果 |
|---|---|---|---|
| 正例 [原查询](https://single-runs-api.open-meteo.com/v1/forecast?latitude=36.6833333&longitude=116.9833333&models=ecmwf_ifs&run=2025-03-01T12%3A00&hourly=snowfall,temperature_2m&timezone=UTC&forecast_days=3) | 2025-03-01 12:00 | 03-02 00:00 至 03-03 00:00 | 12.74 cm；最低 −4.1 °C；首末有雪小时覆盖 02:00–14:00 UTC |
| 对照 [原查询](https://single-runs-api.open-meteo.com/v1/forecast?latitude=36.6833333&longitude=116.9833333&models=ecmwf_ifs&run=2025-03-03T12%3A00&hourly=snowfall,temperature_2m&timezone=UTC&forecast_days=3) | 2025-03-03 12:00 | 03-04 00:00 至 03-05 00:00 | 0.00 cm；最低 −4.4 °C；气温低但没有预报降雪 |

10.00 cm/24 h 是项目自定教学触发线，等于触发；温度仅为上下文，不二次换算或推断降雪。不尝试用缺测的 `Previous Runs snowfall_previous_day1` 替代本批次。

## 核验：独立地面天气编码

- NOAA NCEI [Integrated Surface Database](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)，[济南年度 CSV 镜像](https://noaa-global-hourly-pds.s3.amazonaws.com/2025/54823099999.csv)，站 `54823099999`（区站号 `54823`），`JINAN TSINAN, CH`。选择 `FM-12`，只取同一窗口内非空的 `MW1` 天气码及其质量码；[ISD 格式说明](https://www.ncei.noaa.gov/data/global-hourly/doc/isd-format-document.pdf)、[WMO 天气编码](https://codes.wmo.int/bufr4/codeflag/0-20-003)。
- 正例每 3 小时一条（窗口内 8 条）：3 月 2 日 **06:00 UTC / 14:00 北京时间**的 `74,1` 为观测时有间歇性强降雪；09:00、12:00 UTC 的 `70,1` 为间歇性小雪。对照窗口 8 条 `00,1` 未记录降雪；离散样本没有覆盖每分钟，不能证明整窗无雪。只作事件/降雪时段的定性旁证，**不验证 12.74 cm 或 10 cm 阈值的准确性**。`AJ1` 地面积雪深度、`AA1` 总降水不作新增降雪参考。
- 仓库只保留各窗口的预报字段、档案提取记录和站码摘录，未分发原始数据文件。预报摘录来自 Open-Meteo（[数据许可与归因](https://github.com/open-meteo/open-meteo#data-license)，CC BY 4.0；底层模型 ECMWF），原站码来自 NOAA NCEI；分别注明来源，不因项目代码选择许可证而改变。
