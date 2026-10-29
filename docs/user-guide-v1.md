# 用户操作与答辩演示说明 V1

## 1. 状态

本文说明当前代码中的使用方式；部署、接口和浏览器流程是否运行验证，以 `docs/test-report-v1.md` 的后续证据为准，不在本文预先声称实测通过。

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

## 4.1 管理员用户管理

管理员登录后访问前端 `/users`。页面提供账号创建、分页列表、角色编辑、启用/停用和密码重置；所有写操作由服务端 `ADMIN`/RBAC 和 CSRF 校验保护，前端隐藏按钮不替代服务端授权。

- 创建：用户名为 3–64 位 ASCII 字母、数字、`_`、`.`、`-`；显示名称去首尾空白后 1–100 字符；密码 8–128 字符且不能全为空白；至少选择一个角色。
- 角色：可选 `ADMIN`、`ANALYST`、`REVIEWER`、`VIEWER`，至少保留一个；不能移除当前登录账号的 `ADMIN`，也不能停用活动中的最后一个管理员。
- 停用：不能停用当前登录账号。停用不会删除已有 Session，但该账号下一次鉴权会被拒绝；重新启用后，尚未过期且 Redis 仍保留的 Session 可恢复使用。
- 重置密码：只提交新密码，不回显旧密码；不会注销已有 Session。Session TTL 到期仍需重新登录；API 重启不会主动删除 Redis 中尚未过期的 Session，能否恢复取决于 Redis 持久性和可用性。
- 操作会产生 `USER_CREATE`、`USER_STATUS_CHANGE`、`USER_ROLES_CHANGE` 或 `USER_PASSWORD_RESET` 审计记录；审计详情由管理员在审计页查看。

如果接口返回 `403`，先确认当前账号仍启用并具有 `ADMIN` 角色，同时发送登录后获得的 CSRF Token；`409` 通常表示用户名重复、最后管理员保护或自我保护规则。

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
