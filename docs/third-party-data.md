# 第三方资料与发布范围

- **项目代码**：只对项目中有权发布的代码选定根目录 `LICENSE`。开源许可证不替代下列来源的归因、许可及服务条件。项目负责人确认前不做最终推送。
- **降水与样本**：Open-Meteo Previous Runs（ECMWF / GFS / ICON / GEM）和 ERA5 参考值。见[数据口径](data-and-method.md#2-数据来源与许可)与 `frontend/public/trial/nanjing-source.json`；附归因，区分服务使用条件和数据许可，不能把 ERA5 当作站点真值。
- **历史风险案例**：香港天文台天鸽公报与事后位置表、NOAA HRRR 与 NCEI 站点数据、METAR/SPECI 记录。项目仅保留演练所需的结构化数值及出处，不分发公报全文或原始 GRIB。各份来源条件分别见[台风](c2-typhoon-source-check.md)、[雪灾](c2-snow-source-preflight.md)、[雷电](c2-lightning-source-preflight.md)。
- **行政区划底图**：历史标签中的 `frontend/src/assets/china.json` 与 [DataV.GeoAtlas 的省级边界响应](https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json)按 JSON 内容一致；可下载不等于已确认可捆绑再分发。新源码包和应用镜像移除此底图，改为九城记录条形图。旧检查点仅作版本追溯，不作为此次源码包，也不重写历史。若以后重新引入地图，须先核对来源、使用范围和分发条件。
- **依赖与镜像**：Vue、ECharts、FastAPI 等依赖按各自条款；预构建镜像内的软件及通知保留自身许可。镜像及气象样本不是项目代码许可证的覆盖对象；课程交付源代码、配套镜像和报告分开存放。
