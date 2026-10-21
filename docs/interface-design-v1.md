# 接口设计说明书 V1

## 1. 范围与约定

本文定义 MVP（暴雨端到端 + 七类扩展框架）的 HTTP 接口。当前后端只有 `/health` 与 `/health/db`，以下接口为待实现契约；实现时以本文和后端 OpenAPI 文档同步为准。

- Base URL：除健康检查外，其余路径均以 `/api/v1` 为前缀；健康检查仍为 `/health`、`/health/db`。
- 数据格式：`application/json`；时间统一为 UTC ISO 8601。
- 认证：服务端 Session。登录成功后返回 `HttpOnly`、`SameSite` Cookie；浏览器不读取或保存密码/令牌。
- 授权：服务端按角色检查，前端隐藏按钮不作为权限控制。
- 分页：`page`（从 1 开始）、`page_size`（默认 20，最大 100），响应包含 `items`、`total`、`page`、`page_size`。
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

- 通用错误码：`400 INVALID_ARGUMENT`、`401 UNAUTHENTICATED`、`403 FORBIDDEN`、`404 NOT_FOUND`、`409 INVALID_STATE`、`422 VALIDATION_ERROR`、`503 DEPENDENCY_UNAVAILABLE`。
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
| GET | `/cities` | VIEWER 及以上 | 返回九城代码与名称 |
| GET | `/replay` | VIEWER 及以上 | 按城市、日期、阈值查询回放 |
| GET | `/replay/{replay_id}` | VIEWER 及以上 | 返回单次回放结果与输入溯源 |

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

## 4. 实验指标

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/metrics/experiments` | VIEWER 及以上 | 列出冻结的实验版本 |
| GET | `/metrics/experiments/{version}` | VIEWER 及以上 | 返回基线/融合指标、样本量和限制说明 |

响应必须包含：测试年份、样本量、正类数、阈值、标签来源（ERA5 代理标签）、基线/融合的精确率、召回率、误报率、F1、AUC、自举区间。主结果固定为 10mm/24h 九城合并 F1 `0.7462 → 0.7900`。

## 5. 预警流转

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/warnings` | ANALYST | 基于回放结果创建草稿 |
| GET | `/warnings` | 已登录 | 列表；普通用户只返回已发布内容 |
| GET | `/warnings/{public_id}` | 已登录 | 详情与可执行动作 |
| PATCH | `/warnings/{public_id}` | ANALYST（本人草稿） | 修改未提交草稿 |
| POST | `/warnings/{public_id}/submit` | ANALYST（本人） | 提交审核，状态 `PENDING_REVIEW` |
| POST | `/warnings/{public_id}/review` | REVIEWER | 批准/驳回，必须填写意见；不能审批自己创建的预警 |
| POST | `/warnings/{public_id}/publish` | REVIEWER | 只有 `APPROVED` 可发布 |
| POST | `/warnings/{public_id}/withdraw` | REVIEWER | `PUBLISHED` 可撤回 |
| POST | `/warnings/{public_id}/feedback` | ANALYST/ADMIN | 追加响应/反馈，不修改已发布内容 |
| GET | `/warnings/{public_id}/feedback` | 已登录 | 查询反馈与响应记录 |

状态转换固定为：

```text
DRAFT -> PENDING_REVIEW -> APPROVED -> PUBLISHED -> WITHDRAWN
                        -> REJECTED -> DRAFT
```

非法状态跳转返回 `409 INVALID_STATE`；越权返回 `403 FORBIDDEN`；分析员审批自己的预警返回 `403 SELF_REVIEW_FORBIDDEN`。

草稿请求示例：

```json
{
  "replay_id": "public-id",
  "hazard_type": "RAINSTORM",
  "title": "武汉 24 小时强降水风险提示",
  "area_text": "武汉市",
  "impact_text": "低洼路段可能积水",
  "reasoning_text": "四模式融合 28.1mm，达到 25mm/24h 教学阈值"
}
```

阈值口径固定为：`MODERATE=10mm/BLUE`、`HEAVY=25mm/YELLOW`、`STORM=50mm/ORANGE`，与 `backend/app/seed.py` 一致。

## 6. 审计与健康检查

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/audit-logs` | ADMIN | 按时间、操作者、资源筛选；只读，不提供删除/修改 |
| GET | `/health` | 公开 | 进程存活 |
| GET | `/health/db` | 公开 | 数据库连通性；不可用时返回 503，不泄露 DSN |

审计记录至少覆盖登录成功/失败、登出、用户/角色变更、数据导入、融合运行、草稿创建/修改、提交、审批、发布、撤回、反馈和权限拒绝。

## 7. 前端页面映射

| 页面 | 使用接口 |
| --- | --- |
| 登录页 | `/auth/login`、`/auth/me` |
| 总览页 | `/cities`、`/warnings`、`/metrics/experiments` |
| 历史回放页 | `/replay`、`/replay/{replay_id}` |
| 指标对比页 | `/metrics/experiments/{version}` |
| 预警编辑页 | `POST /warnings`、`PATCH /warnings/{public_id}`、`/submit` |
| 审核页 | `GET /warnings/{public_id}`、`/review` |
| 发布与反馈页 | `/publish`、`/withdraw`、`/feedback` |
| 审计页 | `/audit-logs` |

上述预警路径中的 `{public_id}` 为不可猜测的公开标识，不接受数据库自增主键。浏览器通过同源反向代理或受控 API 地址访问；Cookie 请求仅允许可信来源。

## 8. 实现状态

本文件是接口契约，不代表接口已实现。实现后必须用 FastAPI OpenAPI 生成结果与本文核对，并将接口测试结果记录到 `docs/test-report-v1.md`。
