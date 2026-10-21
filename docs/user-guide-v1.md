# 用户操作与答辩演示说明 V1

## 1. 状态

已在 Ubuntu 26.04 VM 上完成容器化部署与实测（2026-10-20）。以下步骤与当前 `compose.yaml` 一致；测试证据见 `docs/test-report-v1.md`。

## 2. 启动与停止

前置条件：Ubuntu 26.04 VM 已安装 Docker CE 与 Compose 插件，项目目录为 `~/Projects/ComprehensiveInformationSecurityTraining`。

```bash
cd ~/Projects/ComprehensiveInformationSecurityTraining
cp .env.example .env
# 编辑 .env，设置本地随机密码和 APP_SECRET_KEY；不要把 .env 提交
docker compose up --build -d
docker compose ps
```

首次启动会依次执行 MySQL/Redis 健康检查、Alembic 迁移、seed（导入离线样本、创建演示账号）和 API 启动。

验证：

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/health/db
curl http://127.0.0.1:8080/health/redis
```

访问 `http://127.0.0.1:8080`。若从宿主机访问 VM，使用 SSH 隧道：

```bash
ssh -L 18080:127.0.0.1:8080 shawn@192.168.100.128
# 浏览器打开 http://127.0.0.1:18080
```

停止：

```bash
docker compose down
```

不要使用 `docker compose down -v`，除非确认要删除 MySQL 数据卷。

## 3. 演示账号

演示账号由 seed 按 `.env` 中的 `DEMO_*_PASSWORD` 创建，密码不写死在代码和文档中。当前部署中已验证的账号：

| 账号 | 角色 | 用途 |
| --- | --- | --- |
| analyst_demo | ANALYST | 创建并提交预警草稿 |
| reviewer_demo | REVIEWER | 审批、发布、撤回 |
| viewer_demo | VIEWER | 查看已发布预警和指标 |
| admin_demo | ADMIN | 用户/角色管理与审计查询 |

## 4. 答辩演示流程

1. 分析员登录，打开“历史回放”，选择长沙、2024-03-27、25mm/24h。
2. 展示 ECMWF/GFS/ICON/GEM 四模式输入和等权融合值（29.6mm）。
3. 展示融合结果、风险等级、ERA5 代理标签和数据来源；说明 ERA5 不是站点实测。
4. 打开指标对比页：F1 `0.7462 → 0.7900`（+4.38 点），误报率 `0.0651 → 0.0521`，自举区间 `[+1.57, +7.29]`。
5. 分析员创建预警草稿并提交审核。
6. 切换审核员批准并发布；展示只有 APPROVED 能 PUBLISHED。
7. 切换普通用户查看已发布预警；尝试越权操作，展示 403 和审计记录。
8. 添加响应/反馈，展示只追加、不覆盖已发布内容。
9. 展示长沙 2024-02-06 缺 GEM 模式时 `PARTIAL`、不生成风险等级。
10. 说明交付边界：暴雨端到端已实现并测试；其余七类为复用框架的扩展设计，不声称已完成同等验证。

## 5. 常见故障

| 现象 | 检查 |
| --- | --- |
| `permission denied /var/run/docker.sock` | 确认 `shawn` 在 `docker` 组并重新登录 |
| 镜像拉取失败 | 检查 `daemon.json` 镜像加速器可用性；必要时换可信源并固定摘要 |
| MySQL 不健康 | `docker compose logs mysql`；检查 `.env` 密码和卷状态 |
| API 503 | 检查 `/health/db`、MySQL 网络和迁移日志 |
| 登录后立刻失效 | 检查 Redis 是否运行、Session 过期时间和 Cookie 配置 |

## 6. 提交前检查

- README 与本文步骤一致，且能在干净环境启动。
- 演示账号密码不在压缩包和文档中。
- 测试报告 `docs/test-report-v1.md` 已填写实测证据。
- 压缩包不含 `.env`、`.venv`、全量 `data/cache/`、容器卷和 SSH 密钥。
