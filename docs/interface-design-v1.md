# 接口设计说明书 V1

## 1. 范围与约定

本文定义 MVP（暴雨端到端 + 七类扩展框架）的 HTTP 接口。接口契约以当前代码和运行中的 OpenAPI 文档为准；实现状态与运行验证状态分开记录，未运行验证的行为不表述为实测通过。

- Base URL：除健康检查外，其余路径均以 `/api/v1` 为前缀；健康检查为 `/health`、`/health/db`、`/health/redis`。
- 数据格式：`application/json`；业务时间按 UTC 存储，前端按北京时间展示。
- 认证：服务端 Session。登录成功后返回 `HttpOnly`、`SameSite` Cookie 与可读的 `ww_csrf` Cookie；浏览器不读取或保存密码。
- 授权：服务端按角色检查，前端隐藏按钮不作为权限控制。
- 分页：用户管理与审计接口支持 `page`（从 1 开始）、`page_size`（默认 20，最大 100），用户接口返回 `items`、`total`、`page`、`page_size`；审计接口返回当前页数组（当前未做总数统计）。
- 错误格式：

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "当前角色无权执行该操作",
    "request_id": "optional-request-id"
  }
}
```

- 通用错误码：`400 INVALID_PARAMETER`、`401 UNAUTHENTICATED`、`403 FORBIDDEN`、`404 NOT_FOUND`、`409 INVALID_STATE`、`422 VALIDATION_ERROR`、`429 LOGIN_RATE_LIMITED`、`503 DEPENDENCY_UNAVAILABLE`。
- 所有业务接口（含未匹配路由的 404 和请求体校验失败的 422）由 `backend/app/main.py` 全局异常处理统一输出上述结构；`request_id` 与响应头 `X-Request-ID` 一致。422 不返回字段级明细，只返回 `VALIDATION_ERROR`。`/health/db`、`/health/redis` 失败时同样走该结构（`503 DEPENDENCY_UNAVAILABLE`）。
- 所有状态变更接口校验 CSRF Token（开发环境可关闭，生产式演示必须开启）。

## 2. 认证

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/auth/login` | 公开 | 用户名/密码登录，设置 Session Cookie |
| POST | `/auth/logout` | 已登录 | 删除服务端 Session 并清除 Cookie |
| GET | `/auth/me` | 已登录 | 返回当前用户、角色和会话状态 |

登录请求：

```json
{"username": "analyst_demo", "password": "由本地配置提供"}
```

登录成功：

```json
{"user": {"id": "public-id", "username": "analyst_demo", "roles": ["ANALYST"]}}
```

登录失败统一返回 `401 INVALID_CREDENTIALS`，不区分用户名不存在、密码错误或账号已锁定（锁定期间即使密码正确也返回该码，不泄露锁定状态）。仅当密码正确时才区分账号状态：停用返回 `401 ACCOUNT_DISABLED`。同一来源 IP 连续失败达到阈值（`IP_LOGIN_ATTEMPTS`，默认 20 次 / 60 秒）后返回 `429 LOGIN_RATE_LIMITED`；单账号连续失败达到 `MAX_LOGIN_ATTEMPTS`（默认 5 次）则临时锁定 `LOCKOUT_SECONDS`（默认 300 秒）。Session 同时受空闲 TTL（`SESSION_TTL_SECONDS`）与绝对 TTL（`SESSION_ABSOLUTE_TTL_SECONDS`）约束，超过绝对时长即使持续活跃也需重新登录。

## 2.1 用户管理（FR-02）

以下接口挂载在 `/api/v1` 下，仅 `ADMIN` 可调用；服务端再次检查当前账号启用状态和实时角色，前端隐藏按钮不构成授权。写操作必须带 `X-CSRF-Token`，其值与登录响应 `csrf_token`/非 HttpOnly `ww_csrf` Cookie 一致；缺失或不匹配返回 `403 CSRF`。

| 方法 | 路径 | 输入边界与说明 |
| --- | --- | --- |
| GET | `/users?page=1&page_size=20` | `page >= 1`，`1 <= page_size <= 100`；返回分页用户、启用状态和按代码排序的角色 |
| POST | `/users` | `username`：3–64 位，仅 ASCII 字母、数字、`_`、`.`、`-`；`display_name`：去首尾空白后 1–100 字符；`password`：8–128 字符且不能全为空白；`roles`：1–4 个不重复的 `ADMIN/ANALYST/REVIEWER/VIEWER`；重名返回 `409 USERNAME_EXISTS` |
| PATCH | `/users/{user_id}/status` | `is_active` 必须为严格布尔值；不能停用当前登录账号；停用活动中的最后一个管理员返回 `409 LAST_ADMIN_REQUIRED` |
| PUT | `/users/{user_id}/roles` | `roles` 至少一个、最多四个且去重；不能移除当前登录账号的 `ADMIN`；不能移除活动中的最后一个管理员 |
| POST | `/users/{user_id}/reset-password` | `password`：8–128 字符且不能全为空白；重置密码不注销已有 Session |

用户响应仅包含 `id`、`username`、`display_name`、`is_active`、`roles`，不包含密码或密码哈希。创建返回 `201`，启停/角色更新返回 `200`，密码重置返回空响应 `204`。角色输入去重并按代码排序。

用户不存在返回 `404 NOT_FOUND`，非管理员返回 `403 FORBIDDEN`。创建或更新角色时，若请求的任一角色在 `roles` 参考表中缺失（seed 不完整），返回 `503 DEPENDENCY_UNAVAILABLE` 并整体回滚，不会创建缺少角色的账号，也不会只授予部分角色。停用只改变 `User.is_active`：已有 Session 不被删除，但下次鉴权被拒绝；重新启用后，仍未过期的原 Session 可继续使用。Session 存储在 Redis，TTL 到期后需重新登录；API 重启不会主动删除 Redis 中仍未过期的 Session（是否能恢复取决于 Redis 持久性/可用性）。

## 3. 城市与历史回放

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/cities` | 已登录 | 返回九城代码与名称 |
| GET | `/replay` | 已登录 | 按城市、日期、阈值查询回放 |

`GET /replay?city_code=WUHAN&date=2026-06-18&threshold_code=HEAVY` 响应示例：

```json
{
  "replay_id": "public-id",
  "city": {"code": "WUHAN", "name": "武汉"},
  "valid_date": "2026-06-18",
  "threshold": {"code": "HEAVY", "threshold_mm": 25, "level": "YELLOW"},
  "models": [
    {"model": "ECMWF", "precipitation_mm": 28.4},
    {"model": "GFS", "precipitation_mm": 26.1},
    {"model": "ICON", "precipitation_mm": 30.2},
    {"model": "GEM", "precipitation_mm": 27.8}
  ],
  "fused_mm": 28.125,
  "baseline_mm": 28.4,
  "proxy_label_mm": 31.0,
  "risk_level": "YELLOW",
  "data_status": "COMPLETE",
  "source": {"dataset_version": "2026-09-30", "cached_at": "2026-10-01T00:00:00Z"}
}
```

缺少必需模式时返回 `data_status: "PARTIAL"`，不得伪造完整融合值或正式预警。

> `replay_id` 由每次计算生成，不持久化，因此不提供按 id 再查的接口；需要复现时以「城市 + 日期 + 阈值」为输入重新计算。

## 4. 实验指标

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/metrics/experiments` | VIEWER 及以上 | 列出冻结的实验版本 |
| GET | `/metrics/experiments/{version}` | VIEWER 及以上 | 返回基线/融合指标、样本量和限制说明 |

响应必须包含：测试年份、样本量、正类数、阈值、标签来源（ERA5 代理标签）、基线/融合的精确率、召回率、误报率、F1、AUC、自举区间。主结果固定为 10mm/24h 九城合并 F1 `0.7462 → 0.7900`。

## 5. 预警流转

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/warnings` | ANALYST/ADMIN | 基于回放结果创建草稿 |
| GET | `/warnings` | 已登录 | 列表；支持 `?status=` 筛选；普通用户只返回已发布内容 |
| GET | `/warnings/{public_id}` | 已登录 | 详情（含融合追溯）与可执行动作 |
| PATCH | `/warnings/{public_id}` | ANALYST/ADMIN（本人草稿） | 修改未提交草稿 |
| POST | `/warnings/{public_id}/submit` | ANALYST/ADMIN（本人） | 提交审核，状态 `PENDING_REVIEW` |
| POST | `/warnings/{public_id}/review` | REVIEWER/ADMIN | 批准/驳回，必须填写意见；不能审批自己创建的预警 |
| POST | `/warnings/{public_id}/publish` | REVIEWER/ADMIN | 只有 `APPROVED` 可发布 |
| POST | `/warnings/{public_id}/withdraw` | REVIEWER/ADMIN | `PUBLISHED` 可撤回 |
| POST | `/warnings/{public_id}/feedback` | ANALYST/ADMIN | 追加响应/反馈，不修改已发布内容 |
| GET | `/warnings/{public_id}/feedback` | 已登录 | 查询反馈与响应记录 |

`status` 允许值：`DRAFT`、`PENDING_REVIEW`、`APPROVED`、`PUBLISHED`、`WITHDRAWN`、`REJECTED`；非法值返回 `400 INVALID_PARAMETER`。

状态转换固定为：

```text
DRAFT -> PENDING_REVIEW -> APPROVED -> PUBLISHED -> WITHDRAWN
                        -> REJECTED -> PENDING_REVIEW（重新提交）
```

非法状态跳转返回 `409 INVALID_STATE`；越权返回 `403 FORBIDDEN`；自审返回 `403 SELF_REVIEW_FORBIDDEN`。

草稿请求示例：

```json
{
  "city_code": "WUHAN",
  "valid_date": "2026-06-18",
  "threshold_code": "HEAVY",
  "title": "武汉 24 小时强降水风险提示",
  "area_text": "武汉市",
  "impact_text": "低洼路段可能积水",
  "reasoning_text": "四模式融合 28.1mm，达到 25mm/24h 教学阈值"
}
```

创建时后端会重新执行同一回放计算并落库，不直接信任前端传入的融合值；`PARTIAL` 数据返回 `409 PARTIAL_DATA`；COMPLETE 但融合值未达到所选阈值（`risk_level` 为空）返回 `409 THRESHOLD_NOT_REACHED`。

`GET /warnings/{public_id}` 返回 `WarningDetailOut`，在列表字段基础上追加融合追溯（对外 API 只增不改，列表接口仍为 `WarningOut`）：

```json
{
  "...": "与列表字段一致（public_id/status/title/fused_mm/risk_level 等）",
  "baseline_mm": 32.7,
  "proxy_label_mm": 29.6,
  "dataset_version": "2026-09-30.2",
  "models": [
    {"model": "ECMWF", "precipitation_mm": 32.7},
    {"model": "GFS", "precipitation_mm": 30.7},
    {"model": "ICON", "precipitation_mm": 19.6},
    {"model": "GEM", "precipitation_mm": 35.5}
  ]
}
```

`models` 为创建预警时写入 `fusion_inputs` 的四模式输入；早期未记录输入明细的预警 `models` 为空数组，其余追溯字段可能为 `null`。`baseline_mm` 为 ECMWF 基线，`proxy_label_mm` 为 ERA5 代理标签（仅评估用，不参与预警判定）。`POST /warnings` 与 `GET /warnings` 仍返回不含追溯字段的 `WarningOut`。

阈值口径固定为：`MODERATE=10mm/BLUE`、`HEAVY=25mm/YELLOW`、`STORM=50mm/ORANGE`，与 `backend/app/seed.py` 一致。

## 6. 监测、灾种、审计与健康检查

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/monitor/status` | 已登录 | 数据源、数据集、记录量、覆盖完整性（历史快照） |
| GET | `/hazards` | 已登录 | 八类灾种注册表与实现状态汇总 |
| GET | `/audit-logs?page=&page_size=` | ADMIN | 按时间倒序分页；只读，不提供删除/修改 |
| GET | `/health` | 公开 | 进程存活 |
| GET | `/health/db` | 公开 | 数据库连通性；不可用时返回 503，不泄露 DSN |
| GET | `/health/redis` | 公开 | Redis 连通性；不可用时返回 503 |

审计记录至少覆盖登录成功/失败、登出、用户/角色变更、数据导入、融合运行、草稿创建/修改、提交、审批、发布、撤回、反馈和权限拒绝。用户管理成功操作使用 `USER_CREATE`、`USER_STATUS_CHANGE`、`USER_ROLES_CHANGE`、`USER_PASSWORD_RESET`；资源类型为 `USER`，并记录管理员、原因、请求 ID 和客户端 IP。

## 7. 前端页面映射

| 页面 | 使用接口 |
| --- | --- |
| 登录页 | `/auth/login`、`/auth/me` |
| 总览页 | `/cities`、`/warnings`、`/metrics/experiments` |
| 数据监测页 | `/monitor/status` |
| 历史回放页 | `/cities`、`/replay` |
| 指标对比页 | `/metrics/experiments`、`/metrics/experiments/{version}` |
| 预警管理页 | `GET /warnings?status=`、`POST /warnings`、`/submit` |
| 预警详情页 | `GET /warnings/{public_id}`、`/feedback`、`/submit`、`/review`、`/publish`、`/withdraw` |
| 审核工作台 | `GET /warnings?status=PENDING_REVIEW`、`?status=APPROVED`、`/review`、`/publish` |
| 灾种覆盖页 | `/hazards` |
| 审计页 | `/audit-logs` |
| 用户管理页（ADMIN） | `/users` 路由；`GET/POST /users`、`PUT /users/{user_id}/roles`、`PATCH /users/{user_id}/status`、`POST /users/{user_id}/reset-password` |

上述预警路径中的 `{public_id}` 为不可猜测的公开标识，不接受数据库自增主键。浏览器通过同源反向代理或受控 API 地址访问；Cookie 请求仅允许可信来源。

## 8. 实现状态

用户管理路由、Pydantic 输入边界、服务端 ADMIN/RBAC、CSRF 中间件、USER_* 审计调用、`/users` 前端路由与页面已落在代码中；本文不替代运行验证，接口联调、停用/重启 Session 语义和浏览器流程的实测结果由 `docs/test-report-v1.md` 记录。其余接口的实现/验证状态同样以代码和测试报告分别核对。
