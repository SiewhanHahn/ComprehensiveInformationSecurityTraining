# 气象灾害预测与预警系统

基于多源数据融合的气象灾害预测与预警教学演示系统（B/S 架构）。以**暴雨（强降水）**完成端到端闭环与量化对比，其余七类灾种复用同一预警框架作为扩展设计。

- 后端：FastAPI + SQLAlchemy + PyMySQL + Redis（服务端 Session）+ MySQL 8.4
- 前端：Vue 3 + Vite，Nginx 反代 `/api` 到后端
- 编排：Docker Compose，一条命令启动 frontend / api / mysql / redis

## 一键启动

```bash
cp .env.example .env
# 编辑 .env：把各占位符换成本机随机值（可用 `openssl rand -hex 32` 生成）
docker compose up --build -d
docker compose ps
```

访问 `http://127.0.0.1:8080`。

- `/health`、`/health/db`、`/health/redis` 用于健康检查。
- 前端服务绑定 `127.0.0.1:8080`；MySQL 与 Redis 不暴露宿主机端口。

## 演示账号

演示账号由 `seed` 服务按 `.env` 中的 `DEMO_*_PASSWORD` 创建，密码不写死在代码或文档中。角色：

- `admin_demo`（管理员，审计查询）
- `analyst_demo`（分析员，创建/提交草稿）
- `reviewer_demo`（审核员，审批/发布/撤回）
- `viewer_demo`（普通查看，只读已发布内容）

## 版本选择

完整路线、各档交付物与取用方式见 `docs/roadmap-v1.md`。

- 最新稳定版：`main`
- 答辩演示推荐：`v0.2.0-phase-a`（A 阶段验收后）
- 回退到当前已验证快照：`v0.1.0-mvp`

```bash
git fetch --tags
git tag -l
git switch --detach v0.2.0-phase-a   # 只读查看某个版本
git switch main                       # 回到最新稳定版
```

## 量化结果（冻结指标）

九城合并 · 测试年 2026 · n=2403 · 10mm/24h：

| 指标 | 基线 ECMWF | 四模式融合 |
| --- | --- | --- |
| F1 | 0.7462 | **0.7900（+4.38 点）** |
| 误报率 | 6.51% | 5.21% |
| AUC | 0.9586 | 0.9720 |

自举 95% 区间 `[+1.57, +7.29]`，P(提升)=0.998。标签为 ERA5 再分析代理标签（非站点实测）；教学风险等级不代表国家气象台官方预警信号。

## 停止

```bash
docker compose down
```

不要使用 `docker compose down -v`（会删除 MySQL 数据卷）。备份恢复见 `docs/docker-deployment-plan.md`。

## 目录

- `backend/` FastAPI 应用与研究脚本
- `frontend/` Vue 3 前端
- `data/sample/replay_sample.json` 最小离线回放样本
- `data/results/pooled.json` 冻结实验指标
- `docs/` 需求、架构、数据库、接口、测试与演示文档

详细说明见 `docs/user-guide-v1.md` 与 `docs/architecture-v1.md`。
