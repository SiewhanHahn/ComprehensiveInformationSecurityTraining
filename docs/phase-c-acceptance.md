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

## 现场入口与复跑

本次部署目录为 VM 的 `~/Projects/raintrial-c-Y1V36l/src`，项目名 `raintrial-c-y1v36l`。**VM 内打开 `http://127.0.0.1:18080`**，使用已有演示账号。B 版仍在 VM 的 `127.0.0.1:8080`，数据库卷分开。VM 地址可能因 DHCP 改变；宿主机隧道示例见[用户指南](user-guide-v1.md#defense)。

```bash
# 在本次 VM 演示目录中（新部署请使用自己的项目名）
export COMPOSE_PROJECT_NAME=raintrial-c-y1v36l COMPOSE_FILE=compose.yaml:compose.defense.yaml
docker compose ps
set -a; . ./.env; set +a
docker compose exec -T -e RUN_INTEGRATION=1 -e DEMO_ADMIN_PASSWORD -e DEMO_ANALYST_PASSWORD \
  -e DEMO_REVIEWER_PASSWORD -e DEMO_VIEWER_PASSWORD api python -m pytest -q -p no:cacheprovider /app/tests
```

可选浏览器回归：在能访问演示入口的工作站安装 `playwright`，运行 `python -m playwright install chromium`，或把 `CHROMIUM_PATH` 指向现有 Chrome/Edge；运行 `python tests/browser_defense.py --url http://127.0.0.1:18080`，按提示输入演示分析员密码。使用宿主机隧道时换为本地转发端口。

**答辩证据：** [来源与九城对照截图](evidence/phase-c/metrics.png) · [南京七日试算截图](evidence/phase-c/nanjing.png) · [南京数据来源清单](../frontend/public/trial/nanjing-source.json)。南京一周只证明可换城市、日期和文件；不作暴雨能力或额外 F1 提升的证据。
