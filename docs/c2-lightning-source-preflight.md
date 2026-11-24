# C2 雷电：圣路易斯候选数据预核对

**2026-11-24 查验。** 本文件仅核对数据链路，未实现雷电判定、正式流程或通过验收。当前已验收的代码仍以雪灾检查点为准。

## 预测：窗口前形成的原业务档案

- NOAA NCEP [HRRR 公共档案](https://registry.opendata.aws/noaa-hrrr-pds/)，`2025-03-14 18:00 UTC` 起报；固定 6 小时研判窗 `(2025-03-15 00:00, 06:00] UTC`，取 `f07`–`f12` 逐小时有效时次。KSTL 站 `38.75246, −90.37342`，最近格点 `38.740802, −90.373666`（约 1.30 km）。
- 用 [f10 GRIB2 索引](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20250314/conus/hrrr.t18z.wrfsfcf10.grib2.idx) 与同一路径的其他步长按 `Range` 获取 `LTNG`。核对 6 个原文件的 `Last-Modified`：3 月 14 日 **19:00:12–19:08:29 UTC**，均早于预测窗。解码确认起报、步长、瞬时值及 [GRIB2 0/17/192](https://www.nco.ncep.noaa.gov/pmb/docs/grib2/grib2_doc/grib2_table4-2-0-17.shtml)。`LTNG` 无量纲，不是百分比、闪电计数、落点或实况。
- 2025-03-15 01:00–06:00 UTC，6 个逐时值实取为 **0.00、0.06、0.08、0.09、0.00、0.00**。模式在 02:00、03:00、04:00 有信号；只表示这些离散预报时次，不推定信号连续。

## 未触发对照：同站下一窗口

- `2025-03-15 00:00 UTC` 批次的 [f12 索引](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20250315/conus/hrrr.t00z.wrfsfcf12.grib2.idx) 与其 `f07`–`f11` 同样取 `LTNG`。文件的 `Last-Modified` 在 **01:00:32–01:06:24 UTC**；晚于起报、早于 `(06:00, 12:00] UTC` 研判窗。07:00–12:00 的六个近站格点值均为 0。两窗各距起报 6 小时起算，可用相同规则切换演示。
- 06:12 METAR 的 `TSE06` 指上一轮雷暴结束，不能当作对照窗仍有雷暴的当时码；随后抽样未报告雷暴。档案与模式都不是整窗无雷保证。

## 事后旁证与下一步

- 站点 [KSTL METAR/SPECI 历史查询](https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=STL&data=metar&year1=2025&month1=3&day1=15&year2=2025&month2=3&day2=16&tz=Etc%2FUTC&format=onlycomma&latlon=yes&report_type=3&report_type=4)（Iowa State IEM 保管）。01:46 UTC 有雷暴及闪电备注，02:33 UTC 同时报出含雷暴的降雨及持续闪电备注，05:51 UTC 仍报雷暴。可引用 [FAA METAR/SPECI 观测说明](https://www.faa.gov/documentLibrary/media/Order/JO_7900.5E_with_Change_1.pdf) 解释编码。仅验证站点附近在窗内报告了雷暴和闪电；无传感器落点，不声称判断了落点、逐时命中或模型精度。
- 下一步明确教学阈值、逐时采样边界及缺测行为，先写失败测试，再接入页面和正式流程。预测输入与站点报告分文件、分 API 字段，复用 `0008` 结构化证据与 B 角色流程，不新增独立审批系统。
