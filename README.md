# 气象灾害预测与预警系统

基于多源数据融合的气象灾害预测与预警教学演示系统（B/S 架构）。以**暴雨（强降水）**展示端到端闭环和量化对比，以**台风、雪灾和雷电**展示来源可追溯的历史风险判定、事后核对和复用的预警闭环；属于教学演练，不是实时预警。

- 后端：FastAPI + SQLAlchemy + PyMySQL + Redis（服务端 Session）+ MySQL 8.4
- 前端：Vue 3 + Vite，Nginx 反代 `/api` 到后端
- 编排：Docker Compose，一条命令启动 frontend / api / mysql / redis

**终期范围：** 四类重点（暴雨、台风、雪灾、雷电），四类基本预测（干旱、高温、低温、风雹）。当前有四类重点灾种的研判和预警流程；干旱、高温、低温、风雹均可运行基础试算；这不等同于最终交付验收。见[八灾种验收口径](docs/c-eight-hazard-acceptance.md)和[B 最终基线](docs/b-final-acceptance.md)。

**C1 暴雨集成**：从本地验收标签 `checkpoint/c1-rain` 取源码，不从旧演示目录或 `main` 取。先核对页面实际提供的提交号，再展示指标、长沙手算和南京试算。见[当前版本与验收入口](docs/c1-rain-handoff.md)和[演示启动指南](docs/user-guide-v1.md#defense)。

**台风历史演练**：登录后到「数据 → 台风路径」，用同一份天鸽公报换城计算。先选广州看达标，再选上海看未达标。按[来源与口径](docs/c2-typhoon-source-check.md)分开解释预报与事后结果；按[演练步骤](docs/user-guide-v1.md#typhoon)和[C2 版本验收](docs/c2-typhoon-handoff.md)启动，勿覆盖 C1。

**雪灾历史演练**：在「数据 → 雪灾回放」选择新奥尔良原业务预报，20.19 cm 达到 10.00 cm 教学阈值，可以创建演练草稿。济南两个归档对照为 12.74 cm、0.00 cm，仅回放。独立站点天气编码只核对降雪过程，不验证累计量。见[来源与口径](docs/c2-snow-source-preflight.md)和[雪灾检查点验收](docs/evidence/c2-snow-2026-11-24.md)。

**雷电历史演练**：在「数据 → 雷电回放」切换圣路易斯 KSTL 的两个 6 小时窗口。前窗最大 LTNG 0.09、后窗 0.00；教学界线 0.05，只有六时次完整且原档案时间可证的达标案例可创建草稿。LTNG 无量纲；独立站点报告只核对天气现象。见[演练步骤](docs/user-guide-v1.md#lightning)、[来源与口径](docs/c2-lightning-source-preflight.md)和[雷电检查点验收](docs/evidence/c2-lightning-2026-11-24.md)。

**干旱基础预测**：在「数据 → 基础预测」填写连续少雨日数和未来七天降水，现场改值可重算；缺测明确显示无法判断。不保存输入或创建预警。[使用步骤](docs/user-guide-v1.md#basic-forecast)和[实测验收](docs/evidence/c3-drought-2026-11-24.md)。

**高温基础预测**：在「基础预测 → 高温」填 24 个 UTC 整点的气温预报（°C），计算最高值与达到 **35.0 °C** 教学线的时次；缺任一时次为无法判断。初始值仅供教学，不是实时数据，不创建预警。[使用步骤](docs/user-guide-v1.md#basic-forecast)和[实测验收](docs/evidence/c3-heat-2026-11-24.md)。

**低温基础预测**：复用 24 个 UTC 整点的气温表，计算最低值与达到 **≤ 0.0 °C** 教学线的时次；缺测不算。这不是寒潮预报，也不创建预警。[使用步骤](docs/user-guide-v1.md#basic-forecast)和[实测验收](docs/evidence/c3-cold-2026-11-24.md)。

**风雹基础预测**：输入未来 6 个 UTC 整点的阵风和明确雹信号。阵风 **≥ 17.0 m/s** 达教学线；冰雹只依据明确输入。有、无和缺测分别展示，一项缺测不覆盖另一项的结论。[使用步骤](docs/user-guide-v1.md#basic-forecast)和[实测验收](docs/evidence/c3-wind-hail-2026-11-24.md)。

## 代码与第三方资料

项目代码开源许可证待负责人确认，不将第三方资料、软件依赖或基础镜像按项目代码许可证重新授权。来源、归因、可分发范围与历史底图处理见[第三方资料说明](docs/third-party-data.md)。仪表盘使用九城风险条形图，不附行政区划底图。

## 交付包离线启动

使用与源码 SHA 一致的镜像包，按[终验与离线启动说明](docs/offline-delivery.md)在独立 Compose 项目启动。首次构建与现场 `--no-build --pull never` 启动是两件事。见[八灾种技术终验记录](docs/evidence/c-final-2026-11-24.md)；最终许可证及推送另行确认。

## 普通开发启动（非多版本并行演示）

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

`seed` 只在首次创建账号时授予以下默认角色。已有账号以「用户管理」中的授权为准：重跑初始化不会撤销管理员的改动，显式重置演示密码也不会恢复角色。密码由 `.env` 的 `DEMO_*_PASSWORD` 提供。

- `admin_demo`（管理员，用户与角色管理、审计查询）
- `analyst_demo`（分析员，创建/提交草稿）
- `reviewer_demo`（审核员，审批/发布/撤回）
- `viewer_demo`（普通查看，只读已发布内容）

## 版本选择

| 目的 | 取用版本 |
|---|---|
| C3 干旱基础试算（含四类重点） | `checkpoint/c3-drought`（验收标签，不是八灾种终版） |
| C2 雷电集成演示（四类重点） | `checkpoint/c2-lightning`（验收标签，不是八灾种终版） |
| C2 雪灾集成演示（含暴雨、台风） | `checkpoint/c2-snow`（验收标签，不是八灾种终版） |
| C1 暴雨集成演示 | `checkpoint/c1-rain`（本地验收标签，不是八灾种终版） |
| B 最终基线 | `baseline/b-final-2026-11-24`，提交 `be079a3` |
| 历史版本 | `v0.3.0-phase-b` 和 `v0.2.x-phase-a`，不含 C1 |

`git rev-parse 'checkpoint/c1-rain^{commit}'` 用于核对本地标签；没有该标签时，不要把 `main` 或 Phase A 当作替代。见[版本路线](docs/roadmap-v1.md)。

## 量化结果（冻结指标）

九城冻结 v1 · 2026 测试集 · 2,403 个城市日 · 10 mm/24 h。四路预报按各小时提前一天的归档字段取值，再按 UTC 日累计；不是一次起报覆盖次日全天。用 `python backend/verify_frozen_rain.py` 可离线核对样本、混淆矩阵与 F1。

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
