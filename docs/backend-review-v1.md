# 后端代码审查 V1

> 审查对象：`backend/` 整个目录（按 `phase-b` 当前状态，不按 diff）
> 审查时间：2026-11-04
> 用途：本轮修复的清单，以及**前端重构时可以直接引用的后端契约**

## 1. 范围与方法

五个方向各读一遍代码，逐条回读验证后才记为发现：

| 方向 | 覆盖文件 |
| --- | --- |
| 认证 / 会话 / RBAC / 用户管理 | `routers/auth.py`、`session.py`、`deps.py`、`security.py`、`config.py`、`routers/users.py` |
| 预警生命周期 / 回放 / 监测 | `services/warnings.py`、`services/replay.py`、`routers/{warnings,replay,monitor,hazards}.py` |
| 任务 / 通知 / 扫描 / 审计 | `services/{tasks,notifications,subscriptions,audit}.py`、`scheduler.py`、`routers/{tasks,notifications,audit}.py` |
| 模型 / 迁移 / 导入器 | `models.py`、`schemas.py`、`main.py`、`seed.py`、`services/ingest.py`、`migrations/versions/0001~0005` |
| 离线研究管道 | `backend/{fusion,evaluate,pooled,dataset,ingest,skill_probe,summarize,coverage_report,make_sample,ghcn_daily,observation_eval}.py` |

验证方式：能构造执行路径的都实际跑过（例如在容器里 `import backend.app.seed`），不能跑的回读到具体代码行为为止。
**被验证证伪或因文档已明确记录而撤销的项列在第 7 节。**

## 2. 结论摘要

- **19 项确认成立**：P0 ×1、P1 ×4、P2 ×7、P3 ×7。
- 唯一 P0 不是隐患而是**已经坏掉的**：`seed.py` 导入即 `NameError`，任何重建的部署都起不来。
  演示 VM 仍可用，是因为它的 seed 容器建于 2026-10-20（退出码 0），此后只重建了 api/frontend/scheduler。
- 量化结论本身站得住：九城主对比在 `pooled.py` 里固定用 `fusion:mean`，没有在测试年上择优。
  但 `fusion.py` 的**单站**最优规则是测试年选出来的，引用时须注明是探索性统计（见 P2-12）。
- 对外成功响应结构本轮不改动；只新增一个错误码 `INTERNAL_ERROR`。

## 3. 发现清单

### P0 · 部署阻断

| # | 位置 | 问题 | 失败场景 |
| --- | --- | --- | --- |
| 1 | `backend/app/seed.py:53` | 使用 `Decimal` 但模块从未导入它 | `python -m backend.app.seed` 导入期抛 `NameError: name 'Decimal' is not defined`；`compose.yaml:76-77` 的 api 依赖 `seed` 成功退出，于是新部署的 API 永远不启动 |

### P1 · 状态机与认证

| # | 位置 | 问题 | 失败场景 |
| --- | --- | --- | --- |
| 2 | `services/tasks.py` `ack_task`/`complete_task` | 先读状态再逐字段写，UPDATE 只带主键 | 迟到的 `ack` 能把已 `COMPLETED` 的任务写回 `ACKED`，而 `completed_at` 仍非空，状态机出现自相矛盾的记录 |
| 3 | `routers/auth.py:108` | `user.failed_login_count += 1` 是读改写 | 并发错误密码请求互相覆盖计数，`max_login_attempts=5` 的账号锁定被并发绕过 |
| 4 | `routers/auth.py:96/129` | 每 IP 限速先读后 `INCR`；成功登录调用 `_clear_ip_rate` | 并发突发可集体越过阈值；持任意有效账号者可反复清零 IP 计数，绕过 `429 LOGIN_RATE_LIMITED` |
| 5 | `services/tasks.py` 超时升级 | `TASK_OVERDUE` 直接投给 `assignee_id`，未判 `is_active` | 负责人被停用后仍持续收到超时通知，与「收件人必须是启用账号」的口径冲突（管理员收件人那条已过滤） |

### P2 · 口径一致性、离线管道、导入健壮性

| # | 位置 | 问题 | 失败场景 |
| --- | --- | --- | --- |
| 6 | `routers/monitor.py:43-67` | 完整性统计未按 `lead_hours == LEAD_HOURS` 过滤，且用 `count(distinct model_code) == 4` 代替校验 `DEFAULT_MODELS` | 某城日只有 48 小时提前量的四条记录时，监测页判 `COMPLETE`，同一日回放判 `PARTIAL`、创建预警 409 `PARTIAL_DATA` |
| 7 | `services/replay.py:59-68` | `present` 只判记录存在，不判 `precipitation_mm` 非空与 `is_complete` | 值为 NULL 的记录会进入 `sum()` 抛 `TypeError`（500），同时把不完整日判成 `COMPLETE`。当前导入器不写 NULL，属潜在路径 |
| 8 | `ingest.py:81-91` | `_month_chunks` 相邻分块共享边界日，`merged` 用 `extend` 合并 | 边界日变成 48 小时，`len(vals) != 24` 的完整性过滤把整天丢弃 |
| 9 | `services/ingest.py:123` | `day.get("models", {})` 在键存在但值为 `null` 时返回 `None` | `None.items()` 抛 `AttributeError`，整个导入中断而不是记为 `INVALID_VALUE` |
| 10 | `services/ingest.py:104` | 未知城市/模型的原始串未截断就写入 `dataset_issues` 的 `VARCHAR(32)` | 超长值触发 MySQL 1406，同事务内已写入的预报记录全部回滚 |
| 11 | `services/ingest.py:127` | 整天缺一个默认模式时循环遍历不到该键 | 既不记 `MISSING_MODEL` 也不标 `PARTIAL`，数据集仍为 `READY`，而回放判 `PARTIAL` |
| 12 | `fusion.py:151-155` | `best_single`/`best_fusion` 按 **2026 测试年** F1 选择 | 与 `docs/data-and-method.md`「测试年只评估一次、对比协议固定」冲突，`delta_vs_best_single_f1_points` 偏乐观 |

### P3 · 错误结构、配置校验、审计

| # | 位置 | 问题 | 失败场景 |
| --- | --- | --- | --- |
| 13 | `main.py` | 只注册了 `StarletteHTTPException`/`RequestValidationError`/`RedisError` 三个处理器 | 未捕获异常返回纯文本 500，前端拿不到 `error.code` 与 `request_id`，也无法进审计 |
| 14 | `main.py:67` | `secrets.compare_digest` 遇到非 ASCII 头值抛 `TypeError` | 带非 ASCII `X-CSRF-Token` 的请求得到 500 而不是 403 `CSRF` |
| 15 | `config.py:16` | 非开发环境只校验密钥，不强制 `cookie_secure` | `APP_ENV=production` 忘设 `COOKIE_SECURE=true` 时，会话 Cookie 无 Secure 标志 |
| 16 | `main.py:36-43` | `CORS_ORIGINS='*'` 与 `allow_credentials=True` 可共存 | 任意来源带凭据读取接口响应 |
| 17 | `deps.py:32` | 无条件信任 `X-Real-IP` | 部署拓扑下由 Nginx 覆写，安全；但本地直连 API 时可伪造限速键与审计 IP |
| 18 | `routers/users.py` | `_lock_admin` 的 403 与 `SELF_DISABLE`/`SELF_ADMIN_REMOVAL`/`LAST_ADMIN` 的 409 不写审计 | 失败的越权尝试无痕迹 |
| 19 | `services/tasks.py:46` | 只判创建者 `is_active`，不判其是否仍有业务角色 | 被降级成 `VIEWER` 的创建者收到一个自己打开就 403 的任务，且没有改派接口 |

## 4. 前端重构需要遵守的后端契约

### 4.1 错误结构

失败一律是这个信封（`main.py` 的处理器统一生成）：

```json
{"error": {"code": "UPPER_SNAKE_CODE", "message": "中文说明", "request_id": "..."}}
```

- `code` 由 `backend/app/errors.py` 的 `MESSAGES` 定义，是**权威**中文文案来源；前端 `ERROR_ZH` 只作兜底。
- `422` 有两个来源：请求体校验失败是 `VALIDATION_ERROR`；**业务上的 422 目前只有一个**——
  驳回时不填审核意见是 `REJECT_REQUIRES_COMMENT`。所以「422 一定是表单格式错」这个假设不成立。
- `429` → `LOGIN_RATE_LIMITED`；依赖故障 `503` → `DEPENDENCY_UNAVAILABLE`；未捕获异常 `500 INTERNAL_ERROR`。
- `request_id` 与响应头 `X-Request-ID` 始终一致（含 500）。

### 4.1 请求约定（写操作必读）

**CSRF**：除 `GET` / `HEAD` / `OPTIONS` 与 `POST /auth/login` 之外，**每个请求都必须带
`X-CSRF-Token` 头**，其值等于登录响应体的 `csrf_token`（同一值也写在非 HttpOnly 的 `ww_csrf` Cookie 里）。
缺失或不匹配返回 `403 CSRF`。若请求没有会话 Cookie，或 Cookie 对应的 Redis 会话已过期/已登出，
中间件放行到认证依赖并返回 `401 UNAUTHENTICATED`——这表示需要重新登录，不是 CSRF 错误。

```js
fetch('/api/v1/response-tasks/12/ack', {
  method: 'POST',
  credentials: 'include',                     // 会话是 HttpOnly Cookie
  headers: { 'X-CSRF-Token': csrf }           // 少了这个就是 403 CSRF，不是权限问题
})
```

注意 `GET /notifications/unread-count` 虽然是 GET（不需要 CSRF 头），但它会刷新会话空闲 TTL——
这就是前端不对它做定时轮询的原因。

**写操作的返回码不统一**：

| 情形 | 返回 |
| --- | --- |
| 常规写操作（发布、接单、标记已读等） | `200` + 资源 JSON |
| `POST /users`（创建用户） | **`201`** + 用户 JSON |
| `POST /users/{id}/reset-password`、`DELETE /subscriptions/{id}` | **`204`，无响应体** |

统一的请求层不能对 204 调 `resp.json()`，也不能只把 200 当成功。

### 4.2 权限矩阵

**状态码的三种含义**，前端要分开处理：

| 状态码 | 含义 | 典型场景 |
| --- | --- | --- |
| `403` + `FORBIDDEN` | 角色不足（路由级依赖拦下） | 查看者调 `/response-tasks`、非管理员调 `/users*` |
| `403` + 其他码 | 资源级拒绝，与角色无关 | `SELF_REVIEW_FORBIDDEN`（审核自己创建的预警）、编辑他人草稿 |
| `404` + `NOT_FOUND` | 该资源对你不可见，表现为不存在 | 他人的预警详情、他人的任务动作接口 |
| `409` + `INVALID_STATE` | 状态机不允许 | 未接单直接完成、对非 `APPROVED` 的预警发布 |
| `400` + `INVALID_PARAMETER` | 过滤参数的取值不合法 | `status=NOT_A_STATUS`、`status=OVERDUE` |

| 端点 | 允许角色 | 说明 |
| --- | --- | --- |
| `POST /auth/login` | 公开 | 失败统一 `INVALID_CREDENTIALS`；停用账号密码正确才返回 `ACCOUNT_DISABLED` |
| `GET /auth/me`、`POST /auth/logout` | 已登录 | |
| `GET /cities`、`GET /replay`、`GET /hazards`、`GET /monitor/status`、`GET /metrics/*` | 已登录 | 只读 |
| `GET /warnings`、`GET /warnings/{id}`、`GET /warnings/{id}/feedback` | 已登录 | 仅 `VIEWER` 的用户：列表只返回 `PUBLISHED`（`?status=` 传其他状态则是 **200 + 空数组**，不是 404）；**详情与反馈列表**对非 `PUBLISHED` 才返回 404 |
| `POST /warnings`、`PATCH /warnings/{id}`、`POST .../submit`、`POST .../feedback` | `ANALYST`/`ADMIN` | 反馈只追加；编辑非本人草稿是 `403 FORBIDDEN` |
| `POST .../review`、`.../publish`、`.../withdraw` | `REVIEWER`/`ADMIN` | 除角色外还校验状态（不符是 `409 INVALID_STATE`）；**禁止自审**（`403 SELF_REVIEW_FORBIDDEN`） |
| `GET/POST /notifications*`、`/subscriptions*` | 已登录 | 全部按当前用户收敛；`unread-count` 返回 `{"count":n}`，单条已读返回 `{"read":true}`，全部已读返回 `{"updated":n}` |
| `GET /response-tasks`、`POST .../ack`、`.../complete` | `ANALYST`/`REVIEWER`/`ADMIN` | `VIEWER` 整体 `403 FORBIDDEN`；详见 4.3 |
| `GET /audit-logs` | `ADMIN` | 只读 |
| `/users*` | `ADMIN` | 见第 5 节 |

### 4.3 任务：可见 ≠ 可操作

这是本轮修完后的最终口径，前端不要再用一套判断同时管两件事：

| 场景 | 可见性 | 可操作性（`ack`/`complete`） |
| --- | --- | --- |
| 看板列表（不带 `warning` 过滤） | 非管理员只看到指派给自己的 | — |
| `?warning=<public_id>`（详情页） | 能打开该预警的业务角色都能读到它的全部任务 | 仍只允许负责人或 `ADMIN`；**其他业务角色**调动作接口得 `404 NOT_FOUND`，`VIEWER` 则是路由级 `403` |

所以详情页的任务卡对审核员是**只读展示**：有数据、无按钮。按钮显隐请按「本人或 `ADMIN`」判断，不要按「有没有数据」判断。

### 4.4 分页、结果集与字段

| 端点 | 分页 | 返回形状 |
| --- | --- | --- |
| `GET /notifications` | `page`/`page_size`/`unread_only` | `{items,total,page,page_size}` |
| `GET /users` | `page`/`page_size` | `{items,...}` 带总数 |
| `GET /audit-logs` | `page`/`page_size`/`action` | **裸数组，没有 total** —— 前端做不出可靠总页数，只能「下一页/上一页」 |
| `GET /warnings`、`GET /response-tasks`、`GET /warnings/{id}/feedback` | **没有分页** | 裸数组；数据量增长后需补，前端别假设一定有上限 |

`page_size` 三个分页接口都是 **`1 ≤ page_size ≤ 100`**，超上限是 `422 VALIDATION_ERROR`（不是自动截断）。

字段名与语义（按这些名字写，别按常见 REST 习惯猜）：

| 对象 | 字段 | 语义 |
| --- | --- | --- |
| `WarningOut` | `public_id` | 26 字符不可猜标识，路由里用它 |
| | `created_by` | **用户名**，不是用户 ID |
| | `valid_date` | 纯日期 `YYYY-MM-DD`，无时间、无时区 |
| | `fused_mm` | 数值，单位为 mm |
| `ResponseTaskOut` | `id` | 自增整数 |
| | `warning_public_id` / `warning_title` | 直接可用的预警引用与标题 |
| | `assignee` | **用户名**，不是用户 ID |
| | `due_at` / `acked_at` / `completed_at` / `escalated_at` / `created_at` | 时间，可能为 `null` |
| | `escalation_level` | 升级次数，当前只会是 0 或 1 |
| | `overdue` | **服务端算好的派生布尔**，前端不要自己拿 `due_at` 再判断一次 |

### 4.5 时间与标识

- 时间一律**朴素 UTC**（模型是 `DATETIME(6)`）。JSON 里是 ISO 8601、**微秒精度**：整秒时小数部分会被整个省略
  （`2026-11-04T09:49:34`），否则是 6 位（`...34.123456`）。**不要写死 3 位毫秒**，也不要假设一定有小数。
  前端按本地时区显示前先当 UTC 解析（`Date.parse` 对无时区后缀的字符串会当本地时间，需要手动补 `Z`）。
- 对外的预警标识是 `public_id`（26 字符、不可猜）；任务用自增 `id`（仅业务角色可达）。
- 任务状态只有 `PENDING/ACKED/COMPLETED`；**「已逾期」是派生状态**（`overdue` 字段），不是 `status` 的取值。
  任何把 `status=OVERDUE` 传给后端的写法都会得到 `400 INVALID_PARAMETER`。

## 5. 已知限制（前端需自行兜底）

- **未读数不轮询**：只在挂载、切页、标签页回到前台时刷新。这是有意的（该接口会刷新会话空闲 TTL）。
- `GET /warnings` 全量返回、无分页；任务看板与预警的反馈列表同样无分页。
- 通知里不携带预警当前状态，前端只能按已加载列表推断「是否已撤回」。
- 管理员密码重置**不会**让已有会话失效（有意为之，文档已写明）。
- 监测页的 `coverage.partial_days` 只统计「有可用记录」的城日；某城某日**一条记录都没有**时不会被计入
  （`/replay` 对这一天仍判 PARTIAL）。要精确判断某一天，请用 `/replay`，不要只看监测页的计数。
- 监测页的完整性口径本轮会与回放对齐；此前两页可能给出相反结论。

## 6. 本轮修复会改变的前端可观测量

| 修复 | 前端会看到的变化 |
| --- | --- |
| P2-6 监测口径 | 某些城日的 `completeness` 可能从 `COMPLETE` 变成 `PARTIAL`——这是修正，不是回归 |
| P1-4 限速 | 成功登录不再清零 IP 失败计数；同 IP 频繁失败后更早出现 `429` |
| P3-13 兜底 500 | 未捕获异常从纯文本变成标准错误信封，`api.js` 的 `ERROR_ZH` 多一个 `INTERNAL_ERROR` |
| P3-17 `trust_proxy_headers` | 本地直连不再信任 `X-Real-IP`；compose 部署保持原行为（显式开启） |

## 7. 撤销或明确不修的项

| 项 | 结论 |
| --- | --- |
| 「重置密码不失效旧会话」 | `CLAUDE.md` 与 `docs/user-guide-v1.md` 明确写为有意行为，不按缺陷修 |
| 「`errors.MESSAGES` 缺错误码」 | 误报：审查脚本把 `main.py` 注释里的占位符 `UPPER_SNAKE_CODE` 当成了真实错误码；实际所有抛出的码都在表里 |
| 「`X-Real-IP` 可伪造」 | 降级为 P3：部署拓扑里 API 只经 Nginx 暴露且由 Nginx 覆写，只在本地直连时成立 |
| `GET /warnings`、`/response-tasks` 无分页 | 记为已知限制（第 5 节），不在本轮改接口形状 |
| `backfill_published` 每轮重扫 24h 窗口 | 演示规模下成本可忽略，记为已知限制 |

## 8. 修复落地状态（2026-11-04）

19 项全部修复，验证证据见 `docs/test-report-v1.md` §6.17（75 passed ×2、`docker compose run --rm seed` 退出 0）。
三处实现与本文档最初的建议不同，记录在此以免口径漂移：

| 项 | 落地方式 | 原因 |
| --- | --- | --- |
| P1-4 per-IP 限速 | 保持**按失败计数**，只去掉「成功登录清零」；计数改为 `SET NX EX` + `INCR`（固定窗口） | 改成「每次尝试都计数」会让集成套件（一分钟内几十次登录）与同一 NAT 下的演示撞 429；而并发突发已被 P1-3 的原子账号锁定兜住 |
| P2-6 监测口径 | 在四条统计查询上一并加 `lead_hours`、默认模式、值非空、`is_complete` 四个条件 | 只加 lead 过滤不足以保证与回放一致——回放同样不认 NULL 与占位行 |
| P3-17 可信代理 | 新增 `TRUST_PROXY_HEADERS`（默认 false），compose 的 api 服务显式设为 true | compose 部署下 API 只经 Nginx 暴露，关掉该开关会让所有请求共用 Nginx 的 IP，限速形同虚设 |

另有两处顺带改动：`fusion.py` 输出新增 `selection_basis: "train_year"` 字段；前端 `ui/labels.js` 补齐
`USER_*` 与 `USER_MANAGE_DENIED` 审计动作的中文标签（此前审计页对这些动作显示原始代码）。

## 9. 第二轮修正（2026-11-04）

第一轮修完之后又对**修复本身**和**这份文档**复查了一遍，13 项成立，其中与前端直接相关的是 §4 的重写：
补上 CSRF 契约、状态码语义表、201/204、字段名、`page_size` 上限与时间精度。代码侧的补充修复见
`docs/test-report-v1.md` §6.18。§5 新增一条：监测页的 `partial_days` 只统计**有可用记录**的城日。
