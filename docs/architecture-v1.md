# 系统架构设计说明书 V1

## 1. 架构目标

系统采用 B/S 架构，面向课程演示和历史数据回放。目标是在 Ubuntu 26.04 LTS 虚拟机上的 Docker Compose 单机环境中完成气象预报融合、风险研判、预警审批发布和安全审计，同时保留可解释、可追溯和可复现能力。

系统不直接承担真实应急发布职责。外部气象 API 是数据输入源，不是业务系统的持久化层；外部服务不可用时，系统应优先使用本地已导入的数据，并明确展示数据状态。

当前仓库已包含可运行的 FastAPI + Vue 3 + MySQL + Redis 系统：登录/RBAC/会话/CSRF、融合回放、指标对比、预警审批发布、反馈、审计与数据监测均已实现，并通过 Docker Compose 部署验证。本节描述实际架构，未实现部分单独标注。

### 1.1 实现状态与里程碑

| 阶段 | 范围 | 当前状态 | 完成标志 |
| --- | --- | --- | --- |
| M0 基础设施 | Ubuntu VM、Docker CE、Compose、Python 3.14.4 | 已完成 | `docker version`、`docker compose version` 正常 |
| M1 数据与认证 | MySQL/Redis、Alembic、seed、登录/角色/会话 | 已完成 | 可登录，角色权限和审计生效 |
| M2 融合与回放 | 导入冻结的预报/标签数据，融合计算、回放 API 和页面 | 已完成 | 输入四模式可得到融合结果与指标页面 |
| M3 预警闭环 | 草稿、提交、审批、发布、撤回、反馈、审计 | 已完成 | 一条预警完成全状态流转并留痕 |
| M4 前端 | 登录、监测、回放、指标、预警、审核、灾种、审计页面 | 已完成 | 浏览器完成演示脚本 |
| M5 测试与交付 | 自动化/手工测试、测试报告、README、压缩包 | 进行中 | `docs/test-report-v1.md` 持续补充实测证据 |

交付口径为“暴雨端到端 + 七类扩展框架”，详见 `docs/requirements-v1.md` §1.4。M0~M4 已完成，M5 持续补充测试证据。

## 2. 技术选型

| 层次 | 选型 | 选择理由 |
| --- | --- | --- |
| 主机 | Ubuntu 26.04 LTS，Docker Engine + Docker Compose 插件 | 统一 Linux 容器开发、运行环境 |
| 浏览器 | Vue 3 + Vite | 适合快速构建状态清晰的业务页面；已实现全部页面 |
| 前端容器 | 独立前端 Dockerfile + 静态 Web 服务 | 与 API 镜像分离构建和部署 |
| HTTP API | FastAPI + Uvicorn，基于 Ubuntu 26.04 的 Python 3.14.4 容器 | Python 生态可复用现有融合和评估脚本 |
| ORM | SQLAlchemy 2.x | 支持 MySQL 8.4、事务和类型化模型 |
| 驱动 | PyMySQL | 纯 Python MySQL 驱动，容器内无需本机编译型驱动 |
| 数据库 | MySQL 8.4 容器 | 持久化业务数据、实验快照和审计记录 |
| 缓存 | Redis 8.10.2 容器 | 可重建缓存/短期状态；不作为权威持久化存储 |
| 迁移 | Alembic 一次性 Compose 服务 | 管理结构版本，避免应用运行时自动建表 |
| 数据处理 | Python + NumPy | 复用现有多模式融合实现 |
| 身份认证 | 服务端 Session（HttpOnly Cookie），会话存 Redis | MVP 可撤销会话；MySQL 保存用户与角色，Redis 只存会话/缓存 |

## 3. 逻辑架构

```text
┌──────────────────────────────┐
│ 浏览器：登录、回放、预警、审计 │
└──────────────┬───────────────┘
               │ HTTPS/JSON（本机课程演示可使用 HTTP）
┌──────────────▼───────────────┐
│ frontend 容器：Vue 静态资源    │
└──────────────┬───────────────┘
               │ 私有 Compose 网络
┌──────────────▼───────────────┐
│ api 容器：FastAPI              │
│ 认证 / RBAC / 参数校验 / 错误处理│
└───────┬───────────┬──────────┘
        │           │
┌───────▼───────┐ ┌─▼────────────┐
│ mysql 容器    │ │ redis 容器   │
│ 权威持久化数据 │ │ 可重建缓存   │
└───────────────┘ └──────────────┘
        ▲
┌───────┴───────────────┐
│ migrate / seed 一次性任务│
└───────────────────────┘

外部数据：Open-Meteo / ERA5 / NOAA GHCN-Daily
本地研究输入：JSON 缓存与实验结果（不等同 Redis）
```

## 4. 模块边界

### 4.1 API 层

只负责路由、认证依赖、请求模型、响应模型和 HTTP 错误码。API 层不得直接拼接 SQL，也不得直接执行外部下载。

### 4.2 数据服务

负责导入批次、数据来源、模式预报记录、代理标签和真实观测记录。导入流程先校验，再在事务中写入；不把外部 API 响应直接当作可信输入。当前实现见 `backend/app/services/ingest.py`：逐条校验城市/模式/日期/数值及重复、乱序，每处问题写入 `dataset_issues` 且对应记录不入库；含问题的数据集标记 `PARTIAL`（仍可回放，但不能创建正式预警），导入按数据集版本幂等。

### 4.3 融合服务

读取同一城市、同一有效时间和同一提前量的四模式数据，执行等权平均，并生成算法版本、权重、参与输入和输出结果。缺少必需模式时返回数据不完整，不生成正式预警结果。融合使用的原始预报写入 `fusion_inputs`，预警详情据此回溯四模式输入、ECMWF 基线与 ERA5 代理标签（`WarningDetailOut`）。

### 4.4 预警服务

负责阈值计算、草稿创建、提交审核、批准、驳回、发布和撤回。状态转换必须检查当前状态和操作者权限；状态变更与审计写入同一事务。

### 4.5 审计服务

提供追加式写入和管理员查询。业务 API 不提供更新或删除审计日志的能力。审计记录不得保存密码、令牌或完整外部密钥。

### 4.6 Redis 缓存与会话边界

Redis 保存可重建、可过期的缓存，以及服务端 Session。业务事实、预报/观测记录、审批结果和审计日志必须持久化到 MySQL；清空 Redis 只应导致会话失效和缓存重建，不得丢失权威业务数据。

MVP 认证采用服务端 Session：Session ID 放在 `HttpOnly`、`SameSite` Cookie 中，服务端从 Redis 读取会话；本地 HTTP 演示可临时关闭 `Secure`，对外访问必须启用 HTTPS。状态变更接口需要 CSRF 防护（SameSite 配合 CSRF token）。当前 API 已在读写 Redis 会话：登录写入、鉴权读取并滑动过期；Redis 不可用时返回 503。

### 4.7 API 与前端页面边界

MVP API 分组（详细请求/响应和错误码见 `docs/interface-design-v1.md`）：

| 分组 | 代表端点 | 允许角色 |
| --- | --- | --- |
| 认证 | `POST /auth/login`、`POST /auth/logout`、`GET /auth/me` | 全体/已登录 |
| 数据回放 | `GET /cities`、`GET /replay` | VIEWER 及以上 |
| 数据监测 | `GET /monitor/status` | 已登录 |
| 灾种注册 | `GET /hazards` | 已登录 |
| 实验指标 | `GET /metrics/experiments`、`GET /metrics/experiments/{version}` | VIEWER 及以上 |
| 预警查询 | `GET /warnings`、`GET /warnings?status=`、`GET /warnings/{public_id}` | 已登录（VIEWER 仅已发布） |
| 预警草稿 | `POST /warnings`、`PATCH /warnings/{public_id}`、`POST /warnings/{public_id}/submit` | ANALYST/ADMIN |
| 审核发布 | `POST /warnings/{public_id}/review`、`POST /warnings/{public_id}/publish`、`POST /warnings/{public_id}/withdraw` | REVIEWER/ADMIN |
| 反馈 | `POST /warnings/{public_id}/feedback`、`GET /warnings/{public_id}/feedback` | ANALYST/ADMIN |
| 审计 | `GET /audit-logs?page=&page_size=` | ADMIN |
| 健康检查 | `GET /health`、`GET /health/db`、`GET /health/redis` | 无需认证 |

前端页面清单：

| 页面 | 核心内容 | 主要角色 |
| --- | --- | --- |
| 登录页 | 账号密码登录、错误提示 | 全体 |
| 总览页 | 关键指标摘要、最近预警、数据状态入口 | 全体 |
| 数据监测页 | 数据源、数据集版本、导入时间、记录量、完整性 | 全体 |
| 历史回放页 | 城市/日期/阈值选择，四模式输入、融合值、标签对照、研判进度 | VIEWER 及以上 |
| 指标对比页 | 基线 vs 融合的混淆矩阵、F1、误报率、自举区间 | VIEWER 及以上 |
| 预警管理页 | 草稿创建、状态筛选、预警列表 | ANALYST/ADMIN（列表全体） |
| 预警详情页 | 闭环进度、影响范围、研判依据、提交/审批/发布/撤回、反馈 | 按角色 |
| 审核工作台 | 待审核、待发布列表与快捷批准/发布 | REVIEWER/ADMIN |
| 灾种覆盖页 | 八类灾种、实现状态、指标与数据源 | 全体 |
| 审计页 | 登录、数据导入、状态变更和权限拒绝记录 | ADMIN |

前端容器通过同源反向代理或明确的 API Base URL 调用后端；生产式部署应避免把数据库/Redis 暴露给浏览器。跨域仅在开发期按白名单开启，并允许携带 Session Cookie。

### 4.8 闭环阶段映射

| 闭环阶段 | 系统落点 |
| --- | --- |
| 监测 | 数据源/导入批次、数据状态与缓存时间 |
| 预测 | 四模式预报对齐、等权融合、算法版本 |
| 研判 | 历史回放、阈值判断、分析员草稿与研判依据 |
| 预警 | `warning_results`、教学风险等级、数据完整性状态 |
| 发布 | 审核员批准、发布、撤回及状态机校验 |
| 响应 | 已发布预警的响应状态与处理备注 |
| 反馈 | 追加式反馈记录、审计与后续改进参考（MVP 不自动回训） |

## 5. 核心数据流

### 5.1 数据导入

```text
外部 API / 本地缓存
  → 解析与字段校验
  → 导入批次记录
  → forecast_records / observation_records
  → dataset_issues（逐条质量问题，问题记录不入库）
  → 数据质量状态（READY / PARTIAL）
```

### 5.2 融合回放

```text
城市 + 日期 + lead_time
  → 查询四模式 forecast_records
  → 校验完整性
  → 写入 fusion_runs 与 fusion_inputs
  → 计算 ensemble_value
  → 生成 warning_results
```

### 5.3 预警发布

```text
warning DRAFT
  → PENDING_REVIEW（分析员）
  → APPROVED / REJECTED（审核员）
  → PUBLISHED（审核员，批准后发布）
  → WITHDRAWN（审核员）
```

任何状态变更都必须：

1. 校验当前状态是否允许转换；
2. 校验角色和“创建者不能审批自己的预警”；
3. 更新业务记录；
4. 写入 audit_logs；
5. 在同一 MySQL 事务中提交。

## 6. 安全边界

- 浏览器提交的角色、用户 ID、预警状态和审核人 ID 全部视为不可信，服务端从会话和数据库读取。
- 所有写 API 使用 Pydantic 参数校验和 ORM 参数绑定。
- MySQL 应用账号只拥有目标数据库必要权限，不使用 root。
- 数据库连接密码和应用密钥由受控环境变量或 Docker secrets 注入。
- MySQL 与 Redis 默认只在 Compose 私有网络内可达，不发布宿主机端口。
- 外部 API 的错误、超时、空响应和非法数值转为数据源异常状态。
- 日志和响应不暴露 SQL、堆栈、密码摘要和密钥。

## 7. 部署拓扑

目标部署在 Ubuntu 26.04 LTS VM，Docker Engine 由主机提供，服务由 Docker Compose 插件编排：

```text
Ubuntu VM（SSH 管理；项目目录 ~/Projects/ComprehensiveInformationSecurityTraining）
└── Docker Compose 私有网络
    ├── frontend：前端静态资源服务
    ├── api：FastAPI / Uvicorn，Ubuntu 26.04 基础镜像内的 Python 3.14.4
    ├── migrate：Alembic 一次性迁移任务
    ├── seed：可选、幂等参考数据初始化任务
    ├── mysql：MySQL 8.4，命名卷持久化
    └── redis：Redis 8.10.2，可重建缓存，不作权威数据源
```

目标一键入口为 `docker compose up --build -d`。Compose 应按数据库健康 → 迁移 → seed → API 健康的顺序启动；前端仅在所需 API 配置就绪后提供访问。API 通过服务名 `mysql` 连接数据库，并在 Session 集成完成后通过 `redis:6379` 访问会话存储。MySQL/Redis 不默认映射到宿主机；对外仅开放明确需要的前端/API 演示入口，并优先绑定回环地址。

详细实施、配置、秘密、备份和验收规划见 [Ubuntu Docker Compose 部署规划 V2](docker-deployment-plan.md)。`Dockerfile` 与 `compose.yaml` 已创建，一键启动、健康检查与持久化已在 VM 上验证。

## 8. 运行与恢复

- 使用 Alembic 执行结构迁移。
- 使用独立应用账号运行服务。
- 通过 `mysqldump` 进行逻辑备份和恢复演示。
- 恢复后检查外键、角色、预警状态和审计时间线。
- Redis 可清空重建，不承担 MySQL 业务事实的备份职责。
- 实验结果 JSON 作为可复现输入快照保存；MySQL 保存导入批次、算法版本和业务引用。

## 9. 架构验收

- 关闭外部 API 后，已导入数据仍可完成历史回放。
- 数据库不可用时 `/health/db` 明确失败，业务接口不伪造成功。
- 未登录、越权和非法状态跳转被服务端拒绝。
- 预警状态与对应审计记录原子提交。
- 四模式输入、融合配置、结果和预警能够通过主键追溯。
- Compose 一键构建启动前端、API、MySQL、Redis；迁移失败时 API 不健康或不启动。
- Redis 重启/清空后可重建缓存，MySQL 权威业务数据保持完整。
- Session 登录、角色权限、CSRF 防护和审计记录通过测试并留存证据。
- `docs/test-report-v1.md` 记录 AT-01~06 的实测结果；交付压缩包包含 README、Compose、Dockerfile、文档和冻结指标快照。

上述验收已在 2026-10-20/21 的实测中执行，证据与命令见 `docs/test-report-v1.md`；未执行项（如 MySQL 备份恢复、浏览器逐页截图）在该报告中单独标注。
