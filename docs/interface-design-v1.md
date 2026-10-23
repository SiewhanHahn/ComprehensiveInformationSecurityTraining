# 接口设计说明书 V1

## 1. 范围与约定

本文定义 MVP（暴雨端到端 + 七类扩展框架）的 HTTP 接口。以下接口均已实现并通过实测；如与运行中的 OpenAPI 文档不一致，以实测行为并回写本文为准。

- Base URL：除健康检查外，其余路径均以 `/api/v1` 为前缀；健康检查为 `/health`、`/health/db`、`/health/redis`。
- 数据格式：`application/json`；业务时间按 UTC 存储，前端按北京时间展示。
- 认证：服务端 Session。登录成功后返回 `HttpOnly`、`SameSite` Cookie 与可读的 `ww_csrf` Cookie；浏览器不读取或保存密码。
- 授权：服务端按角色检查，前端隐藏按钮不作为权限控制。
- 分页：审计接口支持 `page`（从 1 开始）、`page_size`（默认 20，最大 100），返回当前页数组；当前未做总数统计，前端只提供上一页/下一页。
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

- 通用错误码：`400 INVALID_PARAMETER`、`401 UNAUTHENTICATED`、`403 FORBIDDEN`、`404 NOT_FOUND`、`409 INVALID_STATE`、`422 VALIDATION_ERROR`、`503 DEPENDENCY_UNAVAILABLE`。
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

登录失败统一返回 `401 INVALID_CREDENTIALS`，不区分用户名不存在或密码错误。连续失败应限速或临时锁定。

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
| GET | `/warnings/{public_id}` | 已登录 | 详情与可执行动作 |
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

创建时后端会重新执行同一回放计算并落库，不直接信任前端传入的融合值；`PARTIAL` 数据返回 `409 PARTIAL_DATA`。

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

审计记录至少覆盖登录成功/失败、登出、用户/角色变更、数据导入、融合运行、草稿创建/修改、提交、审批、发布、撤回、反馈和权限拒绝。

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

上述预警路径中的 `{public_id}` 为不可猜测的公开标识，不接受数据库自增主键。浏览器通过同源反向代理或受控 API 地址访问；Cookie 请求仅允许可信来源。

## 8. 实现状态

本文所述接口均已实现并通过自动化或手工测试，测试命令与结果见 `docs/test-report-v1.md` §6。运行中的 OpenAPI 文档可作为最终契约核对依据。
