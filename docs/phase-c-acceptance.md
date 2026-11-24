# 历史暴雨演示验收：来源、指标与离线换站（非八灾种 C 终验）

**验收日期：2026-11-24。** 测试对象为 `c8b4182` 基线上的 C 工作区改动，不是 `main` 或发布标签。没有重算或调参九城冻结结果，没有增加灾种或数据库迁移。

## 这次实际运行了什么

| 环境 | 检查 | 结果 |
| --- | --- | --- |
| Ubuntu VM，独立 MySQL/Redis 与 Compose 项目 | 构建启动、三项健康检查；启用 `RUN_INTEGRATION=1` 并传入四个演示账号变量运行 `/app/tests` | 139 个 pytest 用例通过，无跳过；3 条依赖/旧代码弃用警告。包含登录、审批发布、任务、反馈、审计和新试算。 |
| Windows，项目锁定依赖 | `node --test tests/test_frontend_review.mjs`；`npm --prefix frontend run build` | 14 个检查通过；生产构建通过。地图/ECharts 包仍有 Vite 体积提示。 |
| Edge/Chromium → SSH 隧道 → VM Nginx | 浏览器只允许访问同源。查看 10/25 mm、长沙手算、从网页下载并重传南京文件、改用缺列文件 | 七条均能显示；10-03 融合 5.9 mm，ERA5 5.4 mm；错误指出第 1 行 `models.gem_global`，旧结果消失。无外站请求。 |
| 最终 Nginx/API 镜像 | 同源真实 HTTP 下载文件并 POST；请求超限数据 | 七条成功，响应 `Cache-Control: no-store`；超过 256 KiB 返回 413 JSON。 |

服务端以外网不可达的内部网络连接 API、调度器、MySQL 和 Redis；Nginx 另接只向 VM 回环地址发布端口的入口网络。这里只验证了**运行时不依赖外网**；首次构建或重新获取气象资料仍可能需要联网。未把整台 VM 或宿主机的网卡断开。

## 仅作历史记录

本节只记载旧 `raintrial-c-y1v36l` 实例（VM 回环端口 `18080`）。不要在此实例执行全量测试：集成夹具会改动业务数据、审计日志及 Redis 状态。本次 C1 应使用[新版本指引与独立 QA](c1-rain-handoff.md)。以下截图均为先前工作区的历史证据，不是新提交的实测截图。

**答辩证据：** [来源与九城对照截图](evidence/phase-c/metrics.png) · [南京七日试算截图](evidence/phase-c/nanjing.png) · [南京数据来源清单](../frontend/public/trial/nanjing-source.json)。南京一周只证明可换城市、日期和文件；不作暴雨能力或额外 F1 提升的证据。
