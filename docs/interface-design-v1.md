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

- 通用错误码：`400 INVALID_PARAMETER`、`401 UNAUTHENTICATED`、`403 FORBIDDEN`、`404 NOT_FOUND`、`409 INVALID_STATE`、`409 SUBSCRIPTION_EXISTS`、`422 VALIDATION_ERROR`、`429 LOGIN_RATE_LIMITED`、`500 INTERNAL_ERROR`、`503 DEPENDENCY_UNAVAILABLE`。
- 所有业务接口（含未匹配路由的 404、请求体校验失败的 422，以及**未捕获异常**的 500）由 `backend/app/main.py` 全局异常处理统一输出上述结构；`request_id` 与响应头 `X-Request-ID` 一致。422 不返回字段级明细，只返回 `VALIDATION_ERROR`；500 只返回 `INTERNAL_ERROR`，异常栈写到服务端日志，不返回给客户端。`/health/db`、`/health/redis` 失败时同样走该结构（`503 DEPENDENCY_UNAVAILABLE`）。
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

以下接口挂载在 `/api/v1` 下，仅 `ADMIN` 可调用；服务端再次检查当前账号启用状态和实时角色，前端隐藏按钮不构成授权。写操作必须带 `X-CSRF-Token`，其值与登录响应 `csrf_token`/非 HttpOnly `ww_csrf` Cookie 一致；缺失或不匹配返回 `403 CSRF`。没有会话 Cookie 或 Redis 会话已过期时返回 `401 UNAUTHENTICATED`，不要当作 CSRF 错误处理。

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
| POST | `/warnings/{public_id}/review` | REVIEWER/ADMIN | 批准/驳回，须回传所见提交轮次的 `review_token`；驳回必填意见；不能审批自己创建的预警 |
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

## 5.1 通知与订阅（FR-13 / FR-14）

所有端点只对当前登录用户生效（查看者同样可用），数据按会话用户收敛：列表只返回自己的记录，操作他人记录一律表现为 `404 NOT_FOUND`。

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/notifications?unread_only=&page=&page_size=` | 已登录 | 当前用户通知，按时间倒序；返回 `{items,total,page,page_size}`；`page >= 1`，`1 <= page_size <= 100` |
| GET | `/notifications/unread-count` | 已登录 | 返回 `{"count": n}`；前端只在挂载、切页、标签页回到前台时刷新，**不做定时轮询**（该接口会刷新会话空闲 TTL） |
| POST | `/notifications/{notification_id}/read` | 已登录（本人） | 标记已读，返回 `{"read": true}`；重复标记幂等 |
| POST | `/notifications/read-all` | 已登录 | 全部标为已读，返回 `{"updated": n}` |
| GET | `/subscriptions` | 已登录 | 当前用户订阅列表 |
| POST | `/subscriptions` | 已登录 | 新建订阅，返回 `SubscriptionOut`；重复返回 `409 SUBSCRIPTION_EXISTS` |
| DELETE | `/subscriptions/{subscription_id}` | 已登录（本人） | 取消订阅，返回 `204` 无响应体 |

订阅请求体：

```json
{ "hazard_type": "RAINSTORM", "city_code": "" }
```

`hazard_type` 取 `backend/app/hazards.py` 的八个灾种代码，或 `"*"` 表示全部；`city_code` 取 `backend/app/cities.py` 的九城代码，或 `""` 表示全部。越界取值返回 `422 VALIDATION_ERROR`（用于表达「全部」的哨兵值不是 NULL，原因见 `docs/database-design-v1.md` §3.17）。

通知请求体字段：`id`、`kind`、`title`、`body`、`resource_type`、`resource_id`、`read_at`、`created_at`。`kind` 当前为 `WARNING_PUBLISHED` / `WARNING_WITHDRAWN`；`resource_type='warning'` 时 `resource_id` 是预警的 `public_id`，前端据此跳转详情。已撤回的预警对「仅查看者」不可见（`GET /warnings/{public_id}` 对其返回 404），因此前端只对 `WARNING_PUBLISHED`、或对分析/审核/管理角色才渲染详情链接，避免给出必然打不开的入口。

发布/撤回在业务事务内投递通知。`scheduler` 服务按 `published_at`（发布事件）在最近 `NOTIFICATION_BACKFILL_HOURS` 小时窗口内补投，重复执行不产生重复记录；窗口内被撤回的预警会按「发布 → 撤回」两条顺序补齐，避免订阅者收到一条自己从没见过的撤回通知。

订阅变更写 `SUBSCRIPTION_CREATE` / `SUBSCRIPTION_DELETE` 审计（资源类型 `subscription`）；扫描补投写 `NOTIFICATION_BACKFILL`（`actor_role = SYSTEM`，无用户 ID，只在真的补投了内容时才写）。通知的已读状态属于个人阅读状态，不写审计。

## 5.2 响应任务（FR-15 / FR-16）

任务只对业务角色开放（`ANALYST` / `REVIEWER` / `ADMIN`），查看者访问整个路由返回 `403 FORBIDDEN`。

可见范围分两种。**看板列表**（不带 `warning`）：非管理员只看到指派给自己的任务。**按预警查看**（带 `warning`，详情页用）：能打开该预警的业务角色都能读到它的任务，用于展示负责人、时限与升级情况；但接单与完成始终只允许负责人或 `ADMIN`，别人的任务在动作接口上表现为 `404 NOT_FOUND`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/response-tasks?status=&warning=` | 当前可见任务，按 `due_at` 升序；`status` 取 `PENDING/ACKED/COMPLETED`（非法值 `400 INVALID_PARAMETER`），`warning` 传预警 `public_id` 过滤（不存在 `404`；带该过滤时返回该预警的全部任务） |
| POST | `/response-tasks/{id}/ack` | 接单，`PENDING → ACKED` |
| POST | `/response-tasks/{id}/complete` | 完成，`ACKED → COMPLETED`；未接单或已完成返回 `409 INVALID_STATE` |

完成任务请求体：`{"note": "处置说明"}`，`note` 可选，去首尾空白后 ≤1000 字符。

任务响应字段：`id`、`warning_public_id`、`warning_title`、`assignee`、`status`、`due_at`、`acked_at`、`completed_at`、`escalated_at`、`escalation_level`、`note`、`overdue`、`created_at`。

`overdue` 由服务端按「未完成且 `due_at` 已过」计算，前端不重复判断。「已逾期」不是任务状态：任务状态仍为 `PENDING`/`ACKED`，逾期只体现在 `escalated_at` 与 `overdue` 上。

预警详情页通过 `GET /response-tasks?warning=<public_id>` 取任务，因此 `WarningDetailOut` 不需要扩展。

写操作审计：`RESPONSE_TASK_CREATE`、`RESPONSE_TASK_ACK`、`RESPONSE_TASK_COMPLETE`、`RESPONSE_TASK_CLOSE`（预警撤回时系统自动关闭未完成任务，`actor_role = SYSTEM`）（资源类型 `response_task`），扫描升级写 `RESPONSE_TASK_ESCALATE`（`actor_role = SYSTEM`，只在真的升级了任务时写）。

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
| 通知中心 | `/notifications` 路由；`GET /notifications`、`/notifications/unread-count`、`/notifications/{id}/read`、`/notifications/read-all`、`GET/POST /subscriptions`、`DELETE /subscriptions/{id}`；顶栏铃铛在挂载、切页、标签页回到前台时刷新未读数（不轮询） |
| 任务看板 | `/tasks` 路由（ANALYST/REVIEWER/ADMIN）；`GET /response-tasks`、`/response-tasks/{id}/ack`、`/response-tasks/{id}/complete` |
| 审计页 | `/audit-logs` |
| 用户管理页（ADMIN） | `/users` 路由；`GET/POST /users`、`PUT /users/{user_id}/roles`、`PATCH /users/{user_id}/status`、`POST /users/{user_id}/reset-password` |

上述预警路径中的 `{public_id}` 为不可猜测的公开标识，不接受数据库自增主键。浏览器通过同源反向代理或受控 API 地址访问；Cookie 请求仅允许可信来源。

## 8. 实现状态

用户管理路由、Pydantic 输入边界、服务端 ADMIN/RBAC、CSRF 中间件、USER_* 审计调用、`/users` 前端路由与页面已落在代码中；本文不替代运行验证，接口联调、停用/重启 Session 语义和浏览器流程的实测结果由 `docs/test-report-v1.md` 记录。其余接口的实现/验证状态同样以代码和测试报告分别核对。
## B 修复基线：草稿与审计契约

- `POST /warnings` 的 `impact_text` 去除首尾空白后必填；`PATCH /warnings/{public_id}` 只改明确提供且实际变化的字段，相同 PATCH 不增加版本或审计。旧空值草稿须由作者补全再提交。无效城市/活动阈值为 422，回放不完整为 409。
- `POST /warnings/{public_id}/cancel`：仅具备编辑角色的创建者取消 DRAFT/REJECTED，返回 CANCELLED 并保留审计和原数据。详情不再开放；查看用户看不到取消记录。驳回后原编号可编辑并直接重提为 PENDING_REVIEW。
- `publish` / `withdraw` / `cancel` 接受可选 JSON `{"reason":"…"}`，原因最多 500 字；旧无请求体调用兼容。`GET /audit-logs` 返回可空 `resource_version`（旧行可为空），变更草稿后递增内容版本。请求编号由服务端生成。

- 待审核预警的列表和详情返回不透明的 `review_token`。`POST /warnings/{public_id}/review` 必须回传审核员在屏幕上核对的 token，连同 `decision` 与 `comment` 提交；不应在点击时另取最新 token 代替所见版本。锁内核对内容版本及提交轮次，旧轮次、无 token 的有效审核请求返回 `409 REVIEW_CHANGED`，须重新加载核对，不自动重试。未改稿重新提交也生成新轮次；已驳回的详情只向创建者附带 `rejection_comment`。

<a id="trial"></a>

## 外部城市试算（C，无迁移）

`POST /api/v1/replay/trial?threshold_code=HEAVY`。需要 ANALYST 或 ADMIN 的会话及 `X-CSRF-Token`；`threshold_code` 在查询串（MODERATE / HEAVY / STORM），请求体**直接为文件内容**，不包 `dataset`、不用 multipart。`Content-Type: application/json`。

```json
{"schema_version":1,"lead_hours":24,"rows":[{"city":"南京","valid_date":"2026-10-03","models":{"ecmwf_ifs025":2.1,"gfs_global":5.2,"icon_global":3.3,"gem_global":13.0},"reference_mm":5.4,"reference_type":"ERA5_PROXY"}]}
```

- UTF-8，≤256 KiB，1–200 条；城市名不受内置九城限制，UTC 日期必须为 `YYYY-MM-DD`；同城市同日期不重复，未知列或 JSON 对象内重复字段名均整批拒绝（重复字段返回 422 TRIAL_DUPLICATE_FIELD）。四路必须齐全，数值 0–2000 mm、最多三位小数，不接受数字字符串。可省略两列参考值，或同时给出数值和 `ERA5_PROXY` / `STATION_OBS`。
- 200 返回 `threshold_mm` 和原顺序的 `rows`：城市/日期、四路 `models`、ECMWF `baseline_mm`、`fused_mm` 及两者的 `*_hit`、可空的 `reference_mm/reference_type/reference_hit`。等权均值用 Decimal 半入到三位小数后按 `>=` 判定；参考值不参与计算。响应禁止缓存。
- 未登录 401；角色或 CSRF 不合规 403；阈值不存在 404；字节数超限 413；格式或行不合法 422（`error.message` 给出行和字段）。试算不写预报、观测、数据集、预警或实验结果；成功只记录 `REPLAY_TRIAL` 元数据审计。

## C2：台风离线回放与演练草稿

- `GET /api/v1/typhoon/cases` 列出内置早期公报和参与演练的城市；`GET /api/v1/typhoon/cases/{case_id}/assessment?city_code=...` 返回 `forecast` 与独立 `verification`。登录后可读。未知案例 404，未支持的城市 422。`forecast.outcome` 为 `NEAR` / `NOT_NEAR` / `INSUFFICIENT`，不是实际台风预警等级。
- `POST /api/v1/warnings/typhoon`（分析员或管理员、现有 CSRF 策略）只接收 `case_id`、`city_code`、`title`、`area_text`、`impact_text`、`reasoning_text`。余字段拒绝。服务端重算；无数据或未达教学阈值返回 409，不创建记录。达标建立 `DRAFT`，不直接发布。
- 对台风，既有预警列表和详情中的 `fused_mm` 是 `null`，另有带单位的 `metric`。详情还返回 `typhoon_assessment`（签发时可用的输入、预报证据和判定），不返回事后核对；降水详情沿用既有 mm、四模式与标签字段。提交、审核轮次、发布、响应和审计接口沿用 B。

## C2：雷电离线回放与演练草稿

- 登录后 `GET /api/v1/lightning/cases` 列出内置档案；`GET /api/v1/lightning/cases/{case_id}/assessment` 返回 `forecast` 与可空的 `verification`。六个有效时次和 LTNG 最大值仅来自原业务预报；站点摘录缺失、损坏或不匹配时仍能读取预报。未知案例返回 404。
- `POST /api/v1/warnings/lightning` 仅分析员或管理员可调用，须带 CSRF。只接受 `case_id`、`title`、`area_text`、`impact_text`、`reasoning_text`，其他字段 422。服务器重算，缺测、未达和原发不可证分别返回 409 `PARTIAL_DATA`、`THRESHOLD_NOT_REACHED`、`SOURCE_NOT_VERIFIED`。
- 成功时为 `THUNDERSTORM` 草稿，`fused_mm` 为 `null`。详情 `lightning_assessment` 是预报快照，不含事后核验；沿用 `0008_hazard_assessment` 和 B 的审核、发布、响应、反馈、审计。`ST_LOUIS` 在 `/warning-cities`，不扩展雨量实验 `/cities`。

## C3：干旱基础预测

- `POST /api/v1/basic-forecast/drought/assessment`，登录及 CSRF。提交 `location`、`start_date`（UTC 首日 `YYYY-MM-DD`）、`antecedent_dry_days`（0–3650 的整数或 `null`）、`daily_rain_mm`（正好七个非负有限数值或 `null`）。未知字段、坏日期、错误类型返回 422。
- 返回七个 UTC 日期（含首末日）、每日日雨量与连少雨天数、第七日末 `end_dry_days`、`outcome`。日量 `< 1.00 mm` 延续；`≥ 1.00 mm` 清零。末日 `≥ 14` 天为 `REACHED`；缺测为 `INSUFFICIENT` 且不填造天数。
- 响应 `Cache-Control: no-store`；不留存请求或结果，不生成预警、预报资料及审计事件。灾种总览标 `BASIC`，和端到端 `IMPLEMENTED` 分开计数。
