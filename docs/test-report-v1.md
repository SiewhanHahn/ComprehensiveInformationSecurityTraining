# 测试报告 V1

## 1. 状态与范围

- 文档状态：**MVP 实测完成**（2026-10-20，Ubuntu 26.04 VM）。
- 测试范围：暴雨端到端 MVP、其余七类扩展框架的文档一致性、安全控制、可复现与交付物。
- 未覆盖：浏览器人工点击验收（本次以 HTTP/HTML 资源验证替代，前端构建产物可访问）；MySQL 备份恢复未执行；GHCN 独立观测未接入系统。
- 结果填写规则：每项记录实际结果和证据位置；未执行项明确标注。

## 2. 测试环境记录

| 项目 | 实测值 | 采集命令/位置 |
| --- | --- | --- |
| OS | Ubuntu 26.04 LTS x86_64 | `/etc/os-release` |
| Docker | 29.7.2（客户端/服务端一致） | `docker version` |
| Compose | 插件 v5.5.0 | `docker compose version` |
| Python | 3.14.4（Ubuntu 26.04 发行版） | 容器内 `python3 --version` |
| MySQL | 8.4.11，utf8mb4 | `SELECT VERSION(), @@character_set_server` |
| Redis | 8.10.2 | `redis-cli INFO server` |
| 提交版本 | `2026-09-30.2` 离线样本 | `data/sample/replay_sample.json` |
| 测试数据版本 | pooled.json（2026 测试年） | `data/results/pooled.json` |

服务状态：mysql/redis/api healthy，frontend 运行，发布端口 `127.0.0.1:8080`。

## 3. 功能验收（AT-01~06）

| 编号 | 测试项 | 实际结果 | 证据 |
| --- | --- | --- | --- |
| AT-01-1 | 四模式数据导入/读取 | **通过**：seed 导入 59 条预报、15 条 ERA5 代理标签 | `docker compose run --rm seed` 输出 |
| AT-01-2 | 回放展示 | **通过**：`/api/v1/replay` 返回四模式、融合值、标签、状态 | 长沙 2024-03-27：ECMWF 32.7/GFS 30.7/ICON 19.6/GEM 35.5，融合 29.625，标签 29.6 |
| AT-01-3 | 缺测处理 | **通过**：长沙 2024-02-06 缺 GEM，返回 `PARTIAL`，`risk_level=null` | HTTP 响应 |
| AT-02-1 | 指标页面 | **通过**：前端指标页接口返回基线/融合指标、样本量、年份、标签说明 | `/api/v1/metrics/experiments/10mm` |
| AT-02-2 | 主结果一致 | **通过**：n=2403，正类 406，F1 0.7462→0.7900，Δ+4.38 | 同上 |
| AT-03-1 | 草稿与提交 | **通过**：DRAFT→PENDING_REVIEW | 长沙预警 `ygw7fj3ei8buyj803i8zfgfb72` |
| AT-03-2 | 审批与发布 | **通过**：PENDING_REVIEW→APPROVED→PUBLISHED | reviewer_demo 操作记录 |
| AT-03-3 | 驳回与撤回 | **通过**：PUBLISHED→WITHDRAWN | 同上 |
| AT-03-4 | 反馈追加 | **通过**：追加 COMPLETED 反馈，不改已发布内容 | 反馈接口 200 |
| AT-04-1 | 未登录拒绝 | **通过**：`/api/v1/cities` 返回 401 | curl |
| AT-04-2 | 越权拒绝 | **通过**：分析员查询审计 403；查看者创建/查看未发布 403/404 | curl |
| AT-04-3 | 自己审批自己 | **通过**：`SELF_REVIEW_FORBIDDEN`（403） | curl |
| AT-04-4 | 审计可查 | **通过**：admin 查询到登录、反馈、撤回等记录 | `/api/v1/audit-logs` |
| AT-05-1 | 外部源断开 | **通过（离线样本）**：回放完全来自导入快照，不访问外部 API | docker 网络内无外呼 |
| AT-05-2 | 可复现 | **通过**：重复回放结果一致；单元测试覆盖 | pytest |
| AT-06-1 | 交付证据 | **通过**：测试报告已填；交付压缩包已生成并扫描确认不含 `.env`、缓存、node_modules | `/tmp/ComprehensiveInformationSecurityTraining.tar.gz`（约 252K，110 个条目） |

## 4. 安全测试

| 编号 | 测试项 | 实际结果 | 证据 |
| --- | --- | --- | --- |
| SEC-T01 | 密码哈希 | **通过**：Argon2，单元测试验证不可逆 | `test_password_roundtrip` |
| SEC-T02 | Session Cookie | **通过**：HttpOnly + SameSite(Lax)；本地演示 Secure=false | 登录响应与代码 |
| SEC-T03 | CSRF | **通过**：无 Token 的 POST 返回 403；带 Token 成功；刷新后可从 `ww_csrf` cookie 回退 | curl + 集成测试 |
| SEC-T04 | SQL 注入 | **通过（设计）**：SQLAlchemy 参数化；本次未做专项渗透 | 代码审查 |
| SEC-T05 | 审计不可篡改 | **通过**：业务 API 不提供审计删除/修改 | 路由清单 |
| SEC-T06 | 凭据保护 | **通过（检查）**：日志/响应未见密码、DSN | `docker compose logs` 抽查 |
| SEC-T07 | 端口暴露 | **通过**：MySQL/Redis 无宿主端口；仅 frontend 绑定 127.0.0.1:8080 | `docker compose ps` |

## 5. 容器与部署测试

| 编号 | 测试项 | 实际结果 | 证据 |
| --- | --- | --- | --- |
| DEP-01 | Compose 配置 | **通过** | `docker compose config --quiet` |
| DEP-02 | 一键启动 | **通过** | `docker compose up --build -d`，migrate/seed 退出码 0 |
| DEP-03 | 健康检查 | **通过**：`/health` 200、`/health/db` 200、`/health/redis` 200 | curl |
| DEP-04 | 持久化 | **通过**：重启 api/mysql 后预警数量保持 2 | 重启前后对比 |
| DEP-05 | 缓存失效 | **通过**：`FLUSHALL` 后会话 401，MySQL 预警仍为 2 条 | curl + SQL |
| DEP-06 | 故障可见 | **通过**：停止 MySQL 后 `/health/db` 503，恢复后 200 | curl |

## 6. 自动化测试

- 单元测试：**7 passed**（密码哈希、公开 ID、城市/模式数、冻结指标、样本结构、viewer 只读判定）。
- 集成测试：**3 passed**（健康检查、登录/回放/CSRF、CSRF cookie 下发与 PARTIAL `fused_mm=null`）。
- 执行命令：
  ```bash
  docker compose exec -T api python -m pytest -q -p no:cacheprovider /app/tests/test_units.py
  docker compose exec -T -e RUN_INTEGRATION=1 -e DEMO_VIEWER_PASSWORD=... api \
    python -m pytest -q -p no:cacheprovider /app/tests/test_integration.py
  ```

## 6.1 Code review 回归修复（2026-10-20）

| 问题 | 修复 | 验证 |
| --- | --- | --- |
| 刷新后 CSRF token 丢失，写操作 403 | 登录下发可读 `ww_csrf` cookie，前端回退读取 | 用 cookie 值提交/创建预警成功 |
| PARTIAL 回放 `fused_mm=0.0` 误导 | 四模式不全时返回 `null` | HTTP 响应 `fused=None` |
| viewer 用 `roles == ["VIEWER"]` 精确比较 | 改为 `_viewer_only()` | 单测覆盖多角色 |
| 未达阈值仍写阈值等级 | `risk_level` 允许 NULL，未达阈值为 null | migration `0002_risk_level_nullable` 已应用，创建草稿返回 `risk_level=None` |
| 默认弱 APP_SECRET_KEY | 非 development 环境拒绝默认值 | 配置校验 |
| 迁移镜像未包含 0002 | 重建 migrate 镜像后执行 | `alembic current = 0002_risk_level_nullable` |

## 6.2 第二轮回归/边界测试（2026-10-20）

执行脚本：`tests/manual_round2.sh`（VM 上运行，覆盖 42 项断言）

- 结果：**PASS=42 FAIL=0**
- 覆盖范围：
  - 服务健康：`/health`、`/health/db`、`/health/redis`
  - 认证：未登录 401、正确/错误密码、未知用户、`/auth/me`
  - CSRF：无 Token 403、错误 Token 403、`ww_csrf` cookie 长度 43
  - RBAC：viewer 创建 403、analyst 查审计 403、analyst 审批 403
  - 回放：COMPLETE/fused 29.625、PARTIAL/fused null、未知城市 404、未知阈值 404
  - 指标：10mm ΔF1=4.38
  - 状态机：DRAFT→PENDING→APPROVED→PUBLISHED→WITHDRAWN、DRAFT 直接发布 409、查看者撤回后 404
  - 自审：reviewer 自建自审返回 403（测试后清理临时角色与测试预警）
  - 故障：Redis 清空后会话 401、MySQL 数据保持；停 MySQL 503、恢复 200；重启 api 数据保持
  - 前端：index/SPA/asset 200、未认证代理 401
  - 审计：admin 可查，含 WARNING_PUBLISH 记录

- 本轮发现并修复：`/replay` 对不存在的 `city_code` 返回 200 PARTIAL，已改为先校验 `CITIES`，未知城市返回 404。

## 6.3 后端第二轮 code review 修复（2026-10-21）

对 `backend/app/` 全量通读后发现并修复 5 处中高危 + 8 处低危：

| 级别 | 问题 | 修复 |
| --- | --- | --- |
| 高 | 登录不校验 `is_active`，停用账号仍可登录 | `auth.py` 登录增加 `is_active` 校验，返回 401 `ACCOUNT_DISABLED` |
| 高 | `list_feedback` 缺越权校验，VIEWER 可读未发布反馈 | 增加 `_viewer_only` + 状态校验；`add_feedback` 仅允许 PUBLISHED/WITHDRAWN |
| 中 | 会话无滑动过期（`touch_session` 未调用） | `get_current_user` 成功后调用 `touch_session` |
| 中 | `_to_out` 兜底 `risk_level=""` 违反类型 | 兜底改为 `None` |
| 中 | `seed_users` 不更新既有账号密码、`role` 空会崩溃 | `role` None 守卫；seed 默认只创建缺失账号，按 `.env` 重置需显式 `--sync-demo-passwords` |
| 低 | ERA5 观测唯一约束按 `station_code` 未去重 | 迁移 `0003_observation_unique_city` 改为 `city_code` 维度 |
| 低 | 审计 `ip_address` 记 nginx 内网 IP | `client_ip()` 读取 `X-Forwarded-For` 首跳 |
| 低 | `/health/db` 泄露 MySQL 版本 | 移除响应中的 `version` |
| 低 | `request_id` 始终为 NULL | 新增请求中间件生成 `request_id` 并写入审计 |
| 低 | Redis 宕机时登录返回 500 | 全局 `RedisError` 异常处理器返回 503 |
| 低 | ADMIN 无法 create/review/publish | 业务操作 `require_roles` 加入 `ROLE_ADMIN` |
| 低 | 登录时序可枚举用户名 | 未知用户也执行等价 Argon2 校验 |
| 低 | `list_warnings` 逐条查用户名（N+1） | 改为一次批量查询用户名映射 |

验证：单元测试 7 passed、集成测试 3 passed、`tests/manual_round3.sh`（H1/H2/M1）PASS=4、`tests/manual_round4.sh`（低危项）PASS=9。

## 6.4 前端 code review 修复（2026-10-21）

对 `frontend/src/` 全量通读后发现并修复：

| 级别 | 问题 | 修复 |
| --- | --- | --- |
| 高 | 前端 RBAC 与后端不一致，ADMIN 无法走 UI 业务流 | `auth.js` 新增 `hasAnyRole(...)`；创建草稿/基于回放创建/审核/发布/撤回均改为 `ANALYST,ADMIN` 或 `REVIEWER,ADMIN` |
| 中 | 反馈表单对非 PUBLISHED/WITHDRAWN 状态恒显示 | 增加状态校验，仅 `PUBLISHED`/`WITHDRAWN` 显示 |
| 中 | 新建预警无客户端必填校验 | `title/area/reason` 空值前置拦截并提示 |
| 低 | 错误提示为英文码 | `api.js` 增加错误码中文映射表 |

验证：`docker compose build frontend` 通过；`/`、`/replay`、`/metrics`、`/warnings`、`/audit` 均 200（SPA 回退）；构建产物含 `hasAnyRole` 与中文错误文案。

已记录、本轮未改的低危项：审计页仅 `page_size=100` 无分页、各视图请求失败静默、`roles.join` 无空保护、Dashboard 硬编码基线 F1、无 404 兜底路由、城市显示原始 code 而非中文名。

## 6.5 前端 UI 改造与审计表修复（2026-10-21）

针对人工验收反馈的三类问题：审计表显示异常、界面与动效观感差、需兼顾 Python 后端性能。

| 类别 | 问题 | 修复 |
| --- | --- | --- |
| 审计表 | `resource_id` 为空时渲染出 `auth:` | 资源列改为类型徽章 + 可选短 ID，空 ID 不再拼接冒号 |
| 审计表 | 直接显示带微秒的原始 ISO 时间 | `formatDateTime` 按 UTC→北京时间输出 `YYYY-MM-DD HH:mm:ss`，原始值放入 `title` |
| 审计表 | 7 列 + 26 位 public_id 撑破卡片 | `.table-wrap` 横向滚动、`.id-link` 省略号、审计表 `min-width:1040px` |
| 审计表 | 动作/结果/角色为英文码 | `ui/labels.js` 集中中文映射；逗号角色拆分并逐个显示 |
| 审计表 | `page_size=100` 且无分页 | 每页 20 条 + 上一页/下一页，加载/空/错误三态与重试 |
| 视觉 | 全局样式简陋 | 重写 `style.css`：设计令牌（颜色/圆角/阴影/间距/动效）+ 卡片/按钮/表单/表格/徽章/统计卡/骨架/空态等组件类 |
| 动效 | 无页面过渡 | 路由过渡、卡片交错入场、数字递增、骨架屏、徽章切换、悬停/按压；`prefers-reduced-motion` 全局降级 |
| 导航 | 角色显示 `ANALYST,REVIEWER` | 中文角色标签、用户头像、移动端折叠菜单、404 兜底页 |
| 性能 | `pooled.json` 每次请求读盘解析 | `backend/app/services/metrics.py` 按文件 `mtime` 缓存解析结果 |
| 性能 | 页面切换重复请求静态数据 | `api.js` 对 `/cities`、`/metrics/experiments*` 做 60s 内存缓存 + 同 URL 并发去重；认证/预警/审计不缓存 |

验证：`npm run build` 通过（43 modules）；审计接口 `page=1` 返回 id 80/79/78、`page=2` 返回 77/76/75，空 `resource_id`/`reason` 存在且前端有兜底；SPA 路由（含未知路径）均 200；构建产物含中文映射与「未达阈值」「未认证」等文案；后端日志无异常。

## 6.6 Phase A：闭环呈现与文档对齐（2026-10-21）

按 `docs/roadmap-v1.md` 的 A 档补齐「闭环看得见、8 类边界说得清、测试有证据」。

| 类别 | 新增/修改 | 说明 |
| --- | --- | --- |
| 灾种 | `backend/app/hazards.py`、`GET /api/v1/hazards`、前端 `/hazards` | 8 类灾种注册表，1 类端到端 + 7 类扩展框架，页面明确标注 |
| 监测 | `GET /api/v1/monitor/status`、前端 `/monitor` | 数据源、数据集版本、导入时间、记录量、模型齐全度；标注「历史快照，非实时接入」 |
| 闭环 | `ClosedLoopStepper.vue` | 预警详情展示监测→预测→研判→预警→发布→响应→反馈；回放页展示前三段 |
| 审核 | `/review` 工作台 | 待审核/待发布筛选 + 快捷批准/发布，复用现有状态机接口 |
| 查询 | `GET /warnings?status=` | 服务端状态筛选；VIEWER 仍只能看到已发布；非法状态返回 400 |
| 创建 | 预警管理页回放摘要 | 从回放带入时展示融合值/等级/模式，PARTIAL 时禁止创建 |
| 文档 | `roadmap-v1.md`、`traceability-v1.md`、`AGENTS.md`、architecture/interface/database | 修正过期描述，补充需求—实现—测试对应关系 |
| 测试 | `tests/test_rbac_matrix.py`、`tests/test_state_machine.py` | 角色矩阵、完整状态机、自审拒绝、REJECTED 重提交 |

验证（2026-10-21，VM 实测）：`npm run build` 通过；`python -m py_compile` 通过；`/monitor`、`/hazards`、`/review` 路由均 200；`/api/v1/hazards` 返回 `total=8, implemented=1, framework=7`；`/api/v1/monitor/status` 返回 3 个数据源、4 个数据集、119 条预报、30 条代理标签、模型齐全度 `COMPLETE`；`/warnings?status=PENDING_REVIEW` 200、非法状态 400；viewer 访问 `/audit-logs` 403、`?status=DRAFT` 返回空；`pytest` 全量 **19 passed**（含新增 RBAC 矩阵与状态机测试）。

## 6.7 前后端 code review（2026-10-21）

分两轮通读 `backend/app/` 与 `frontend/src/`，修复确认的缺陷：

| 侧 | 级别 | 问题 | 修复 |
| --- | --- | --- | --- |
| 后端 | 高 | 直接调 API 可创建空标题/区域/研判依据的预警 | `WarningCreate` 对必填字段 strip 并校验非空、限制长度 |
| 后端 | 中 | 回放 `source.dataset_version` 误用内部自增 id | 改用 `Dataset.version` 业务版本号 |
| 后端 | 中 | 监测完整性用全局模式并集，会误报 COMPLETE | 改为按城市统计模式覆盖 |
| 后端 | 中 | 反馈返回时间戳用 `_now()` 而非库内值 | `commit` 后 `refresh` 读 `fb.created_at` |
| 后端 | 低 | logout 删 cookie 未对齐 samesite/secure；`/auth/me` 无 None 防护 | 补齐；加 401 守卫 |
| 前端 | 高 | FastAPI 422 的 detail 是数组，前端渲染成 `[object Object]` | `api.js` 识别数组 detail，映射中文「请求参数不合法」 |
| 前端 | 中 | 驳回不填意见、反馈内容为空无前置提示 | `WarningDetail.vue` 前置校验并提示 |
| 前端 | 低 | 动作后刷新失败会清空已加载数据 | 失败时保留现有数据 |

验证：后端 `pytest` 19 passed；空标题/空研判 `POST /warnings` → 422；`source.dataset_version=2026-09-30.2`；`/monitor/status` 返回 `per_city` 且 `completeness=COMPLETE`；前端 `npm run build` 通过，产物含「驳回时必须填写审核意见」「反馈内容不能为空」「请求参数不合法」中文文案，路由全 200。

## 6.8 A 档后端 code review（2026-10-23）

对 A 档后端（灾种注册表、监测接口、状态筛选、字段校验、回放版本）通读后修复：

| 级别 | 问题 | 修复 |
| --- | --- | --- |
| 高 | `WarningUpdate` 绕过创建校验，PATCH 可写入空标题/空研判；显式 `null` 触发 500 | 补 strip + 非空校验（提供时），显式 null 返回 422；补长度上限 |
| 中 | `/monitor/status` 完整性统计跨全部数据集，且未按日校验，可能误报 COMPLETE | 对齐最新 READY FORECAST 数据集；新增 `partial_days` 按城日统计缺模式天数；全齐才 COMPLETE |
| 低 | `STATUS` 与 `WARNING_STATUSES` 重复定义 | 删除死常量，统一 `WARNING_STATUSES` |
| 低 | 反馈内容纯空格可通过 `min_length=1` | 增加 strip 后非空校验；审核意见同样 strip |

验证（VM 实测）：
- `pytest` **19 passed**。
- `PATCH` 空标题 → **422**；`PATCH` 显式 `null` → **422**；合法标题 → **200**；空反馈 → **422**。
- `/monitor/status` 返回 `partial_days=1`、`completeness=PARTIAL`。核对数据库确认是真实缺测：**长沙 2024-02-06 缺 GEM**（与 AT-01-3 一致），旧逻辑因跨数据集去重而误报 COMPLETE，新逻辑已纠正。

已知遗留（未改）：`ReviewOut.created_at` 用应用时间；CSRF 拒绝响应无 `X-Request-ID`；锁定账号的既有会话仍有效。

## 6.9 A 档前端 code review（2026-10-23）

对 A 档前端（监测页、总览、指标、审核工作台、闭环 Stepper 等）通读后修复：

| 级别 | 问题 | 修复 |
| --- | --- | --- |
| 高 | 监测页完整性变 PARTIAL 后无解释 | 展示缺测城日数与数据集版本，说明不影响其余样本 |
| 高 | 总览融合 F1 由硬编码基线 0.7462 反推 | 改用 `/metrics/experiments/10mm` 详情端点的 `fusion.f1` |
| 中 | 指标页 ΔF1 硬编码「+」前缀，负值会显示 `+-x` | 按正负条件加前缀 |
| 中 | 监测「已接入模式」用全库去重、与回放口径不一致 | 后端 `coverage.models` 改为仅统计最新数据集 |

验证：`pytest` 19 passed；`/monitor/status` 返回 `models` 为最新数据集四模式、`partial_days=1`、`dataset_version=2026-09-30.2`、`completeness=PARTIAL`；`/metrics/experiments/10mm` 的 `fusion.f1=0.79`；前端构建通过。

已记录未改：审核工作台批准硬编码意见、总览冻结指标表硬编码、GET 缓存全局不区分用户（仅缓存与用户无关的参考数据）、404 页 public。

## 6.10 FR-02 隔离环境浏览器验证（2026-10-28）

验证环境为独立 Compose 项目 `fr02`（MySQL/Redis/API），不修改原演示部署；API 挂载的 `routers/users.py` SHA256 与本地一致。本机 Vite 通过 SSH 转发访问隔离 API，Playwright 使用本机 Chrome 驱动真实页面。

| 操作 / 探针 | 实际观察 |
| --- | --- |
| 管理员登录并进入用户管理 | 登录 200，列表正常显示 |
| 空表单、重复用户名 | 中文校验；重复创建 409，显示中文错误 |
| 页面创建账号 | 201；显示名称去首尾空白，密码输入清空，响应不含密码哈希 |
| 页面授予/撤销角色 | 200；目标账号已有会话下一次 `/auth/me` 返回新角色 |
| 页面停用、重新启用 | 200；停用后已有会话下一请求 401，启用后未过期会话可恢复 |
| 页面重置密码 | 204；新密码可通过登录页面登录，原会话仍有效，输入清空 |
| VIEWER 直接访问 `/users` | 前端重定向总览，用户接口返回 403 |
| 缺失 CSRF、自停用、自撤 ADMIN | 分别返回 403、409、409 |
| 审计接口与页面 | 测试账号具有四类 USER_* 成功事件，审计页面显示记录 |
| 页面运行错误 | 捕获 pageerror 为 0 |

浏览器发现并修复：空字符串 `busy` 直接绑定布尔属性会使创建/重置按钮初始禁用，改为显式布尔值；写操作期间禁用切换账号、关闭、刷新和分页，避免异步编辑对象错位。修复后重新执行上述完整流程通过。

本地证据截图：`C:\Users\siewhan\AppData\Local\Temp\fr02-users-verified.png`；临时驱动脚本 `fr02-browser-verify.cjs` 同目录（不包含密码，运行时仅读取独立测试配置）。本次为开发服务器页面验证，不等同于生产 Nginx 新版本部署验收；API 重启和依赖服务故障尚未验证。历史测试数量不计入本次结果。

后续自动化验证（独立 MySQL/Redis）：`RUN_INTEGRATION=1` 运行 `/app/tests/test_user_management.py`，**11 passed**。覆盖 schema、用户管理流程、实时会话/角色、CSRF、自保护，以及新增的两类并发和事务故障场景：

- 两个临时管理员同时停用对方、同时撤销对方 ADMIN：通过 Barrier 确认双方已完成入口鉴权后同时进入管理锁，各场景返回一个 200、一个 403，最终恰有一个临时账号保持活动 ADMIN。原 demo 管理员未被修改。
- 状态/角色变更已执行 `flush` 后，注入审计异常：请求失败，独立数据库会话确认业务状态和角色均恢复原值，成功审计数量未增加。

全套测试首轮为 **24 passed、2 failed**；两项失败均因独立测试容器未包含 `data/results/pooled.json`，指标读取为空。用户手动上传后，将文件放入隔离宿主机 `data/results/`（容器为只读挂载），核对本地、上传文件及容器内 SHA256 均为 `712b0e0ad95e0d42e51181b94f7c14777cf6b24889385a5079dd9754bf911876`。补齐数据并增加四项并发/回滚用例后，设置 `RUN_INTEGRATION=1` 和四个 `DEMO_*_PASSWORD`，执行 `python -m pytest -q -p no:cacheprovider /app/tests`，最终 **30 passed、2 warnings，耗时 4.95 秒**。两条依赖弃用警告为 Python asyncio policy、Starlette/httpx，不影响断言；未操作原演示部署。

## 6.11 代码审查修复复验（2026-10-28）

审查确认两项问题并已修复：

| 问题 | 修复 |
| --- | --- |
| 创建账号/更新角色时，`roles` 参考表缺少所请求的角色会被静默忽略，仍返回 201/200 | 查询结果必须覆盖全部请求角色，否则返回 `503 DEPENDENCY_UNAVAILABLE` 并整体回滚 |
| 错误响应为 FastAPI 默认 `{"detail": ...}`/422 数组，不符合 §1 统一错误结构 | `main.py` 增加全局 HTTP/校验异常处理，所有接口输出 `{"error": {"code", "message", "request_id"}}` |

自动化验证：同步修改到隔离 `fr02` 环境（本地与 VM 文件 SHA256 一致），设置 `RUN_INTEGRATION=1` 和四个 `DEMO_*_PASSWORD`，执行 `python -m pytest -q -p no:cacheprovider /app/tests`，结果为 **34 passed、2 warnings，耗时 4.91 秒**。新增 4 项：参考角色缺失时的创建与改角色（业务数据和审计均无写入）、`_roles` 校验，以及错误结构（404/422/400 与未匹配路由）。原 `test_state_machine.py` 中对 `detail` 的断言已改为 `error.code`。

浏览器复查（本机 Vite → SSH 转发隔离 API，Chrome headless）：登录失败显示"用户名或密码错误"；重复用户名 409 显示"用户名已存在"；自停用返回 409 `SELF_DISABLE_FORBIDDEN`；非法请求体 422 映射为"请求参数不合法（请检查输入）"；预警非法筛选 400 映射为"请求参数不合法"；VIEWER 直达 `/users` 重定向并返回 403；pageerror 为 0。截图：`C:\Users\siewhan\AppData\Local\Temp\fr02-error-envelope-verified.png`。

本次未在原演示部署上验证，生产 Nginx 镜像未重建。

## 6.12 阶段 2 验证（2026-10-30，FR-01/03/04 + 前端两项）

在隔离 `fr02` 环境（未触碰演示部署）验证阶段 2：

- **迁移**：`docker compose -p fr02 run --rm migrate` 由 `0003_observation_unique_city` 升级到 `0004_dataset_issues`，成功创建 `dataset_issues` 表。
- **后端全量**：同步 `backend/` 与 `tests/`，设置 `RUN_INTEGRATION=1` 和四个 `DEMO_*_PASSWORD`，执行 `python -m pytest -q -p no:cacheprovider /app/tests`，结果 **43 passed、2 warnings，耗时 7.80 秒**。新增 `tests/test_fusion.py`（详情返回四模式输入/基线/代理标签/数据集版本；PARTIAL 日禁止创建）。
- **测试自身修正**（两处此前"已写未跑"的断言）：`test_ingest` 期望 `row_count` 由 7 改为 6（缺 GEM + 负值各少一条）；`test_login` 改为只比较 `error.code`/`error.message`，不再比较含 `request_id` 的整个对象。
- **前端**：审核工作台改为逐行填写审核意见（驳回时客户端强制非空），预警详情新增「融合追溯」卡片展示四模式输入、基线、代理标签与数据集版本；`npm run build` 通过。
- **浏览器复查**：本机 Vite → SSH 转发隔离 API，Chrome headless 驱动。分析师建单并提交 → 详情页显示 4 模式与基线/代理标签；审核员工作台空意见驳回被拦截，填入意见后批准成功；仅有的控制台错误为登录前 `/auth/me` 的 401 与 favicon 404，属预期资源请求。

## 6.13 阶段 B 第一刀验证（2026-11-03，FR-13/FR-14）

在隔离 `fr02` 环境验证订阅、站内通知与定时扫描（未触碰演示部署；演示 VM 仍是 A 档版本）。

- **迁移**：`docker compose -p fr02 run --rm migrate` 由 `0004_dataset_issues` 升级到 `0005_subscriptions_notifications`，创建 `warning_subscriptions`、`notifications`、`response_tasks` 三张表。`response_tasks` 本阶段只建表，B 档第二刀才开始读写。
- **后端全量**：同步 `backend/` 与 `tests/` 后执行 `python -m pytest -q -p no:cacheprovider /app/tests`，结果 **54 passed、2 warnings**（首次 11.68 秒；修正下述两处测试隔离后连续两次运行均为 54 passed，13.17 / 13.86 秒）。本轮之前同一环境的基线是 45 项（§6.12 记录的 43 项之后又新增 2 项），本轮 +9 项：
  - `tests/test_notifications.py`（7 项）：发布投递给匹配订阅者、范围不匹配不投递、撤回投递、重复订阅 409 `SUBSCRIPTION_EXISTS`、非法灾种/城市 422、通知按用户隔离且不能标记他人通知（404）、已读与未读数与全部已读。
  - `tests/test_scheduler.py`（1 项）：先发布后订阅 → `run_scan` 补投 1 条 → 再跑补投 0 条 → 留下 `NOTIFICATION_BACKFILL` 审计且 `actor_id` 为空、`actor_role = SYSTEM`。
  - `tests/test_units.py`（+1 项）：`subscriptions.matches()` 四维匹配（不限/精确 × 命中/未命中）。
  - `tests/test_rbac_matrix.py`：`/notifications`、`/notifications/unread-count`、`/subscriptions` 加入四角色可读矩阵与匿名 401 矩阵。
- **测试隔离修正**（首次全绿后连续复跑暴露的两个既有脆弱点）：
  - 通知类测试原先用 `viewer_demo` 订阅。演示账号上只要残留一条订阅（例如浏览器验收留下的），建订阅就变成 409，「不应投递」的断言也会因历史通知失真。改为每个测试用 `subscriber` 夹具创建临时 VIEWER 账号，账号删除时订阅与通知随之清理。
  - `test_login.py::test_ip_rate_limit_blocks_after_threshold` 依赖 Redis 中该合成 IP 的计数器为空；60 秒窗口内连续跑第二遍会直接命中 429。改为测试开始时先删除 `login:fail:<ip>` 键。
- **定时扫描容器**：在隔离环境以 `NOTIFICATION_SCAN_INTERVAL_SECONDS=5` 实跑 `python -m backend.app.scheduler` 12 秒，`timeout -s TERM` 触发退出。日志显示「定时扫描启动，间隔 5 秒」→「收到信号 15，停止扫描」→「定时扫描已停止」，无异常栈；本轮无待补投内容，因此未写审计（符合「只在实际补投时写审计」的设计）。
- **前端**：`npm run build` 通过，新增 `Notifications` 懒加载分块（7.69 kB，gzip 3.29 kB）。
- **浏览器复查**（本机 Vite → SSH 转发隔离 API，Chrome headless）：查看者经真实登录页登录 → 进入 `/notifications` → 选「暴雨 / 全部城市」添加订阅成功（订阅标签出现）→ 分析员经接口建单并提交、审核员批准并发布 → 查看者刷新后收到 1 条未读通知（标题「预警发布：浏览器验收-订阅通知」，正文「长沙 2024-03-27 暴雨；四模式融合 29.6mm」），顶栏铃铛角标显示 1 → 点击「标记已读」后角标归零。pageerror 为 0；控制台仅有登录前 `/auth/me` 的 401 与 favicon 404。截图：`C:\Users\siewhan\AppData\Local\Temp\phase-b-notifications.png`。
- **回归**：`GET /warnings`、`GET /warnings/{public_id}` 响应结构未变（`WarningOut` / `WarningDetailOut` 未改动）；`test_state_machine.py`、`test_rbac_matrix.py`、`test_user_management.py` 全部通过，`conftest.py` 清理逻辑已覆盖新表的外键。

## 6.14 阶段 B 第一刀 code review 收口（2026-11-03）

对 `main..phase-b`（40 文件 / +1763 行）做了多角度评审（逐行、删除行为、跨文件、语言陷阱、封装层、复用、简化、效率、层次、仓库规范）。共 15 条确认问题，全部修复后复测。

**安全与可见缺陷**

- **会话空闲超时被轮询续命**：顶栏未读数原本每 60 秒轮询一次，而 `/notifications/unread-count` 走 `get_current_user` → `touch_session`，会重置 Redis 空闲 TTL。只要标签页开着，SEC-01 承诺的「空闲 1 小时失效」就不再成立，只能靠 8 小时绝对 TTL 收回。改为只在挂载、路由切换、标签页重新可见这三种「用户真实操作」时刷新，去掉定时器。
- **未定义的设计变量**：角标背景与订阅删除按钮的 hover 色写成 `--color-danger`，而设计系统里是 `--danger`，两处都解析失败退化成透明，角标只剩一圈描边。改为 `--danger`。

**行为修正**

- 重复订阅的预检查与唯一索引之间存在并发窗口，撞索引会返回 500；补上 `IntegrityError` 1062 → `409 SUBSCRIPTION_EXISTS`，与 `routers/users.py` 的既有写法一致。
- 补投原按「当前状态 = 已发布」取数，导致两次扫描之间被撤回的预警永远补不到「发布」通知，订阅者只收到一条自己没见过的「撤回」。改为按 `published_at` 取窗口，窗口内已撤回的按「发布 → 撤回」两条顺序补齐。
- 已撤回预警对「仅查看者」是 404，前端原本仍然渲染「查看预警」链接；改为只对 `WARNING_PUBLISHED` 或分析/审核/管理角色渲染。
- `warning_subscriptions.is_active` 是从未写入的死列（取消订阅是物理删除），从模型与迁移 `0005` 中删除。
- 未读数刷新失败时把计数清成 0、且并发请求可乱序覆盖；`loadNotifications` 增加请求序号丢弃过期响应，未读筛选下标记已读改为重新取当前页（本地删行会让 `total` 与后端偏移错开）。
- 订阅与城市列表的加载失败原本被吞成空数组，后端出错时页面看起来像「还没订阅过」；改为走统一错误提示。
- 标题按整串 `[:200]` 截断会吃掉结尾字符，改为先按剩余长度截预警标题再拼前缀。
- 停用账号仍会持续收到通知；订阅者查询改为只取启用账号。

**部署、索引与测试**

- `NOTIFICATION_BACKFILL_HOURS` 写进了 `.env.example` 与 `config.py`，但 compose 的 `scheduler` 服务只转发了 `SCAN_INTERVAL`，设了不生效；补上转发。
- `warnings` 表原本没有任何索引，扫描每轮全表扫；迁移 `0005` 补 `idx_warnings_published_at`。
- `mark_all_read` 改为单条批量 `UPDATE`。
- 测试隔离：`_notifications_for(analyst, ...) == []` 仍假设演示账号没有订阅，改用第二个临时账号 `bystander`；`test_mark_read_and_unread_count` 不再断言绝对未读数，改为断言「这一条」在未读集合中的归属；`test_scheduler` 的审计断言只认本次扫描之后新增的行；`conftest` 清理补上 `response_tasks`。
- `test_login.py` 清空 IP 计数器后丢失了「计数器带过期时间」与「成功登录清计数」的覆盖，补上 TTL 断言并新增 `test_successful_login_clears_ip_failures`。

**迁移回环**

`downgrade()` 原先逐条 `drop_index`，在 `idx_response_tasks_assignee` 上撞 MySQL 1553——该索引被 `assignee_id` 的外键借用，外键在就不能删。改为直接 `drop_table`（MySQL 会连同索引与约束一起删），并在隔离环境实跑 `0004 → 0005 → 0004` 回环验证。

**复测**

- 隔离 `fr02` 环境：`alembic downgrade 0004` → `upgrade head` 成功，`warning_subscriptions` 已无 `is_active`、`warnings` 上有 `idx_warnings_published_at`。
- 全量 pytest **55 passed**（新增 `test_successful_login_clears_ip_failures`），连续两次运行结果一致。
- `npm run build` 通过；浏览器复查仍为：订阅 → 发布 → 铃铛角标 1（红色实心）→ 标记已读后归零。

## 6.15 阶段 B 第二刀验证（2026-11-03，FR-15/FR-16）

在隔离 `fr02` 环境验证响应任务、处置时限与超时升级（未触碰演示部署）。本刀**没有新迁移**，`response_tasks` 沿用 `0005` 建好的表。

- **后端全量**：同步 `backend/` 与 `tests/` 后执行 `python -m pytest -q -p no:cacheprovider /app/tests`，结果 **62 passed、2 warnings**（此前 55 项，本轮 +7：新增 `tests/test_tasks.py` 6 项与 `test_rbac_matrix.py` 的查看者 403 断言），连续两次运行一致（14.94 / 15.08 秒）。
- **新增用例**：发布自动派发任务（负责人为创建者、时限与配置口径相差 <1 分钟）、指派通知、他人任务不可见（业务角色 404、查看者 403、管理员可代接）、状态机（未接单不能完成、重复接单 409）、完成落库与处置说明、逾期任务升级一次且重复扫描不再升级、未到期任务不升级。
- **定时扫描容器**：在隔离环境插入一条 `due_at` 已过 5 分钟、`status=PENDING`、`escalated_at IS NULL` 的任务，以 `NOTIFICATION_SCAN_INTERVAL_SECONDS=5` 实跑 `python -m backend.app.scheduler` 14 秒。日志出现 `响应任务超时升级 escalated=1`，SIGTERM 后正常退出；数据库确认该任务 `escalation_level=1`、`escalated_at` 非空、**`status` 仍为 `PENDING`**（超时不改流转状态），并生成 `TASK_OVERDUE`（负责人）与 `TASK_ESCALATED`（管理员）两条通知。验证用的任务与通知已清理。
- **前端**：`npm run build` 通过，新增 `Tasks` 懒加载分块。
- **浏览器复查**（本机 Vite → SSH 转发隔离 API，Chrome headless）：分析员建单 → 审核员批准发布 → 分析员在 `/tasks` 看到 1 条「待处置」任务（负责人 `analyst_demo`、时限按配置）→ 点「接单」进入「处置中」→ 填处置说明并完成，出现在「已完成」标签页；预警详情页显示「响应任务」卡，闭环 Stepper 的「响应」阶段变为已完成，标注「负责人 analyst_demo / 已完成处置」。pageerror 为 0，控制台仅有登录前 `/api/v1/auth/me` 的 401。截图：`C:\Users\siewhan\AppData\Local\Temp\phase-b2-tasks.png`、`phase-b2-detail.png`。
- **回归**：`GET /warnings`、`GET /warnings/{public_id}` 响应结构未变（任务通过 `GET /response-tasks?warning=` 单独取，`WarningDetailOut` 未扩展）；订阅、通知与既有状态机测试全部通过。

## 6.16 阶段 B 第二刀 code review 收口（2026-11-04）

对 `phase-b` vs `main` 的全量 diff 跑了 8 个角度的 code review（逐行、删除行为、跨文件、复用、简化、效率、站位、约定），
去重后 25 个候选逐条验证，**10 项确认成立、2 项证伪**（`Tasks.vue` 与 `WarningDetail.vue` 的 `canAct` 两处实现实际等价；`run_scan` 的两趟结构没有具体代价）。修复全部在隔离 `fr02` 验证，演示部署未动，无新迁移。

- **处置时限配置到不了容器**（`compose.yaml`）：`RESPONSE_TASK_DUE_MINUTES` 只写在 `.env.example` 与 `config.py`，api 服务没转发，Docker 部署下用户指南 §4.3 的「设成 2 分钟演示超时」不生效。已补 `RESPONSE_TASK_DUE_MINUTES: ${RESPONSE_TASK_DUE_MINUTES:-1440}`。证据：`docker compose config` 未设置时解析为 `"1440"`，`.env` 设 2 时解析为 `"2"`。
- **升级与完成竞态**（`services/tasks.py::escalate_overdue`）：原来是「读出对象再逐字段赋值」，UPDATE 的 `WHERE` 只有 id，扫描读出候选之后并发提交的完成会被覆盖成「已升级」并误报管理员。改成带 `status`/`due_at`/`escalated_at` 条件的单行 UPDATE，用 `rowcount` 判定。一次性探针复现真实交错（会话 A 读候选 → 会话 B 完成并提交 → 会话 A 执行同一条 UPDATE）：`rowcount=0`，任务仍为 `COMPLETED`、`escalated_at` 为空、`escalation_level` 为 0。
- **指派给已停用账号**（`services/tasks.py::create_for_published`）：创建者在提交草稿后被停用时，任务原先仍挂给该账号，任务永远没人能推进。现在改派给发布人，并在 `RESPONSE_TASK_CREATE` 审计的 `reason` 里写明原因。
- **审核员看不到任务**（`services/tasks.py::list_tasks`）：任务只派给创建者，而列表对非管理员强制按 `assignee` 过滤，审核员打开别人的已发布预警永远显示「尚未派发任务」。现在**带 `warning` 过滤时**业务角色可读该预警的任务，接单与完成仍只允许负责人或管理员；看板列表（不带过滤）行为不变。
- **辅助请求失败清空整页**（`WarningDetail.vue`）：任务请求原来与预警主体共用 try/catch，任务接口抖动会把已经取到的预警丢掉并显示「无法加载预警」。现已拆分，任务失败只在卡片内提示；预警与反馈改为 `Promise.all` 并行。
- **页签竞态**（`Tasks.vue`）：`load()` 在 `await` 之后才读 `activeTab` 且无序号保护，快速切页签会把旧请求结果按新页签解释。已按通知中心的写法加 `loadSeq`，并在发起请求时固定页签。
- **空状态文案**（`Tasks.vue`）：`emptyTitle` 内联了第二份页签文案，且已与 `tabs` 不一致（「逾期」vs「已逾期」），改为从 `tabs` 派生。
- **撤回后的死链**（`Notifications.vue`）：`WARNING_PUBLISHED` 通知无条件渲染「查看预警」，预警随后被撤回时仅查看者点进去必然 404。现在按列表里出现的 `WARNING_WITHDRAWN` 收集 `resource_id` 抑制链接；只覆盖已加载的那一页，彻底解决需要后端在通知里带上预警当前状态。
- **页面内「刷新」不刷未读数**（`Notifications.vue`）：刷新只重拉列表与订阅，页头角标与「全部标记已读」按钮停在旧值。已把 `refreshUnread()` 并入 `refresh()`。
- **测试残留**（`tests/conftest.py`）：清理只删 `resource_type='warning'` 的通知，发布时产生的 `TASK_ASSIGNED`/`TASK_OVERDUE`/`TASK_ESCALATED` 会以孤儿身份留在库里。现在先按任务 id 删通知、再删任务。
- **文档口径**：`docs/interface-design-v1.md` 两处与 `frontend/src/style.css` 注释仍写「顶栏铃铛轮询未读数」，与已定决策（不轮询，否则会话空闲 TTL 被续命）相反，已改正。

验证：

- **后端全量**：**64 passed、2 warnings**（62 + 新增 2 项），连续两次运行一致（16.66 / 16.79 秒）；`tests/test_tasks.py` 8 项全过（新增「完成后不再被升级」「创建者停用改派发布人」，并把「审核员看不到他人任务」改为「可读不可操作」）。
- **前端**：`npm run build` 通过。
- **浏览器复查**（本机 Vite → SSH 转发隔离 API，Chrome headless）**12/12 项通过**：审核员在分析员创建的已发布预警详情页看到负责人与时限（不再显示「尚未派发任务」，Stepper 的「响应」标注 `负责人 analyst_demo`）；分析员在详情页接单 → 完成，Stepper 显示「已完成处置」；任务看板「已完成」能看到该任务、「已逾期」空状态为「已逾期任务为空」；通知中心点「刷新」后未读数正常渲染；`viewer_demo` 订阅后收到发布与撤回两条通知，且被撤回预警的「查看预警」链接不再渲染。截图：`review-fix-reviewer.png`、`review-fix-detail.png`、`review-fix-notifications.png`。
- **未纳入本轮**（按严重度排在 10 名之后，留待后续）：`refreshUnread` 的无序竞态（可自愈）、`/tasks` 与既有「审核」同样不按角色收敛导航、`subscriptions`/`users` 两处 1062 处理重复、`to_out_list(db, [task])[0]`、任务通知标题绕过 `NOTIFICATION_TITLES`、`GET /response-tasks` 无分页、`backfill_published` 每轮重扫 24 小时窗口。

## 6.17 backend 全量代码审查与收口（2026-11-04）

对 `backend/` 整个目录（不按 diff）做了一轮审查，覆盖认证/会话/RBAC、预警与回放、响应任务/通知/扫描、
模型/迁移/导入器、离线研究管道五个方向。完整清单与对前端的契约见 `docs/backend-review-v1.md`。
**19 项确认成立**（P0 ×1、P1 ×4、P2 ×7、P3 ×7），另有 3 项被证伪或下调，记录在该文档第 7 节。

- **P0（已修）**：`seed.py` 用了 `Decimal` 却从未导入，`python -m backend.app.seed` 在导入期抛 `NameError`。
  `compose.yaml` 里 api 依赖 `seed` 成功退出，所以**任何新建或重建的部署都起不来**。演示 VM 仍可用只是因为
  它的 seed 容器建于 2026-10-20、此后从未重跑。证据：修复前在容器内执行 `python -c "import backend.app.seed"`
  得到 `NameError: name 'Decimal' is not defined`；修复后 `docker compose -p fr02 run --rm seed` 退出码 0 并输出
  `[seed] 完成`。
- **P1**：`ack`/`complete` 改为带期望状态的条件 UPDATE（`rowcount` 判定），迟到的 ack 不再能把 `COMPLETED` 写回 `ACKED`；
  登录失败计数改为原子自增；成功登录不再清空 per-IP 失败计数；超时通知不再投给已停用的负责人。
- **P2**：监测页的完整性统计补齐 `lead_hours == 24`、四个默认模式、值非空与 `is_complete` 四项条件，与回放口径一致；
  回放不再把 NULL 值计入融合（否则 `sum()` 抛 `TypeError`）；离线采集的分块边界不再互相重叠；导入器对
  `models: null`、超长城市名、整天缺一个模式分别记账而不是崩溃或静默放过；`fusion.py` 的最优规则改为**按训练年选择**。
- **P3**：补全局 500 处理器（`INTERNAL_ERROR`，含 `X-Request-ID`）；CSRF 比较改为按字节（非 ASCII 头不再 500）；
  非开发环境强制 `COOKIE_SECURE=true` 且拒绝 `CORS_ORIGINS='*'`；新增 `TRUST_PROXY_HEADERS`（compose 的 api 设为 true）；
  被拒绝的管理操作写入 `USER_MANAGE_DENIED` 审计；创建者被降级到只剩 VIEWER 时任务也改派发布人。

验证：

- **后端全量**：**75 passed、2 warnings**（此前 64），连续两次一致（17.84 / 18.27 秒）。新增 11 项：
  seed 导入看门狗、`csrf_matches` 非 ASCII、停用负责人不收超时通知、降级创建者改派发布人、
  NULL 值日判 PARTIAL 不 500、监测与回放提前量口径一致、`models: null`、超长城市名截断、整天缺模式记账、
  未捕获异常的 500 信封、被拒管理操作的审计。
- **部署冒烟**：`docker compose -p fr02 run --rm seed` 退出 0；api 重启后 `/health` 正常。
- **前端**：`npm run build` 通过（仅新增 `INTERNAL_ERROR` 与 5 个 `USER_*` 审计动作的中文标签）。
- **口径变化（需知会前端）**：监测页某些城日可能由 `COMPLETE` 变为 `PARTIAL`（这是与回放对齐后的修正）；
  同一 IP 在一分钟内失败 20 次后，该 IP 的登录会被挡到窗口结束，**成功登录不再重置这个计数**——
  这正是为了堵住「持有一个有效账号就能反复续额度」的绕过，测试套件因此改为在每个集成用例前自行清空计数。
- **未改动**：演示 VM 仍未部署；对外成功响应结构不变。

## 6.18 backend 第二轮审查：修复的回归与契约文档纠错（2026-11-04）

第二轮针对上一轮的**修复本身**和**它产出的契约文档**再查一遍（修复回归、事务与锁、输入与滥用面、
文档是否属实）。**13 项确认成立**，其中 2 项是上一轮修复没改干净、1 项是上一轮改动引入的回归。

- **契约文档（最高价值）**：`docs/backend-review-v1.md` §4 原稿**整份没写 CSRF**——除 `GET/HEAD/OPTIONS`
  与 `/auth/login` 外所有请求都要带 `X-CSRF-Token`。照那份文档重构前端，每个写操作都会拿到 `403 CSRF`，
  而界面提示是「无权限」，排查方向会完全错。同节还写错了 403/404/409 的分工、漏了 201/204、
  关键字段名、`page_size ≤ 100`、以及把微秒精度写成「毫秒」。全部重写。
- **上一轮的缺口**：`services/replay.py` 的 `baseline_mm` 没走非空判定（ECMWF 值为 NULL 时仍 500）；
  `auth.py` 的锁定判断用 `db.refresh`，在 REPEATABLE READ 下是快照读，并发失败请求仍可能都不触发锁定。
- **上一轮引入的回归**：`services/ingest.py` 把非 list 的 `days` 静默换成空列表，会导入一个 **0 行却 READY**
  的数据集；它 `imported_at` 最新又不是 FAILED，`latest_dataset` 会选中它，把真实数据整体遮蔽。
- **其余**：`notify_users` 的「先查后插」在并发下撞唯一索引会把调用方事务（含发布）一起回滚；
  `scheduler` 两趟扫描共用一个事务，第二趟失败会把第一趟的补投一起撤销；`config.py` 的 Cookie 校验放在
  `Settings()` 构造期会连带把 alembic/seed/scheduler 一起拦死；`_deny` 把 actor_role 硬写成 ADMIN；
  `login:fail:<ip>` 旧的无 TTL 键不会自愈；`reasoning_text` 没有 `max_length`（超长到 flush 才 1406）。

修复与验证：

- **后端全量**：**80 passed、2 warnings**（此前 75），连续两次一致（19.03 / 18.85 秒）。新增 5 项：
  NULL 基线不 500、并发投递同一条通知不抛异常且只留一条、一趟扫描失败不回滚另一趟、坏样本标 FAILED、
  无 TTL 的 IP 计数键自愈。
- **部署冒烟**：`docker compose -p fr02 run --rm seed` 退出 0。
- 演示 VM 仍然不动；对外成功响应结构、错误码集合均均未变化（本轮只改实现与文档）。

## 6.19 第三轮加固与演示 VM B 档部署验收（2026-11-15）

第三轮继续收口撤回联动、数据集版本配对、样本重导幂等与认证边界，并将 `phase-b` 正式部署到演示 VM（`192.168.100.128`）完成端到端验收：

- **预警撤回自动关闭任务**：`withdraw_warning` 在同一事务内调用 `tasks.close_for_withdrawn`（`SELECT ... FOR UPDATE`），将该预警下未完成的响应任务置为 `COMPLETED` 并写入 `RESPONSE_TASK_CLOSE`（`actor_role = SYSTEM`）审计；`escalate_overdue` 同步排除已撤回预警，前端 `ui/labels.js` 补齐中文标签。
- **数据集版本配对与精度一致**：`replay.py` 与 `monitor.py` 的观测数据集查询均限定与当前 `FORECAST` 数据集同 `version`，避免跨版本混配；融合阈值判定改用与展示一致的 `round(fused, 3)`。
- **导入器与 seed 幂等保护**：`services/ingest.py` 改为按文件 SHA-256 `checksum` 判幂等；同版本若已被 `fusion_inputs` 引用则拒绝覆盖（`blocked = dataset_in_use`）；非法 JSON / 非对象顶层 / 非字符串 `city_code` / 0 可用行均安全落为 `FAILED` 并记录 `dataset_issues`；全坏条目不占用 `(city, date)` 去重键。`seed.py` 默认仅创建缺失演示账号，显式传 `--sync-demo-passwords` 才按 `.env` 重置密码与启用状态。
- **认证与 CSRF 边界**：无会话 Cookie 的写请求放行至认证依赖返回 `401 UNAUTHENTICATED`；有 Cookie 但 Redis 会话已过期同样返回 `401 UNAUTHENTICATED`（前端 `api.js` 收到非登录 401 自动 `auth.clear()`），不再误报 `403 CSRF`；登录成功分支对 `locked_until`/`is_active` 改用 `FOR UPDATE` 当前读，429 分支补 `EXPIRE NX` 自愈。
- **测试修正**：`test_fusion.py` 中三条直接修改 `ForecastRecord` 的用例补齐 `ForecastRecord.dataset_id == latest_dataset(db, "FORECAST").id` 过滤，避免在含历史数据集的库上改到旧版本行；`test_ingest.py` 补齐 `Dataset` 导入。

验证：

- **演示 VM 部署**：`docker compose build`、`docker compose run --rm migrate`（升级至 `0005_subscriptions_notifications`）、`docker compose run --rm seed` 均退出码 0；`api`、`frontend`、`scheduler`、`mysql`、`redis` 五服务运行正常，`/health`、`/health/db`、`/health/redis` 全部返回 `ok`。
- **后端全量测试**：在演示 VM 的 `api` 容器内执行全量套件，**91 passed、2 warnings**（18.27 秒）。
- **B 档端到端闭环验收**：静态资源（HTML/JS/CSS）、未认证 401 vs 缺头 403 CSRF 信封、监测与回放版本对齐（`2026-09-30.2`）、订阅 $\rightarrow$ 建单 $\rightarrow$ 提交 $\rightarrow$ 审核 $\rightarrow$ 发布 $\rightarrow$ 站内通知与未读计数、响应任务权限隔离（审核员详情页可读但 `ack` 返回 404、查看者 403、分析员 `ACKED -> COMPLETED`）与反馈、撤回自动关单与 `RESPONSE_TASK_CLOSE` 审计全部验证通过，验收后已清理临时测试数据。

## 6.20 `v0.3.0-phase-b` 分层审查 P0~P4 分批修复与回归（2026-11-15）

基于 `main`（`v0.3.0-phase-b`）切出 `fix/phase-b-review` 分支，按严格 TDD 节奏分五批完成全部 Verified Critical/Important/Minor 修复：

- **P0（`06ad82a`）**：`WarningDetail.vue` 补齐 `taskError` 空任务兜底分支；`warnings.py` 多角色成员不再被误判 `is_viewer_only`；`schemas.py`/`auth.py` 限制登录入参长度并通过 Redis Lua `login:inflight:{ip}` 原子限并发；`replay.py` 缺失预测数据集返回空记录；`ingest.py` 预校验避免脏样本污染既有可用数据集，并校验 `FORECAST`+`ERA5_LABEL` 双摘要幂等。
- **P1（`963b223`）**：`session.py`/`main.py` 校验会话字典与时区、区分过期会话返回 `401 UNAUTHENTICATED`、调整 CORS 洋葱圈外层顺序并收紧方法/请求头白名单；`auth.py` 严格 `_parse_ip`、整型 `user_id` 与先 `db.commit()` 后写 Redis 会话、锁定且密码正确同步计入 IP 失败；`audit.py` 分页上限 `page <= 10000` 并增 `AuditContext._clip`；`replay.py` `ReplaySource.cached_at` 与 `Decimal` `ROUND_HALF_UP` 精确阈值判定；`subscriptions.py` 原子删除与 `begin_nested()` 保存点；`tasks.py`/`warnings.py` 统一 `Warning -> ResponseTask` 加锁顺序、发布改派资格检查及撤回先关单后通知。
- **P2（`857cb5d`）**：`Notifications.vue` 撤回链接对业务角色放行并对查看用户隐藏任务入口；`App.vue`/`router.js`/`Login.vue` 会话失效跳转与安全 `redirect` 校验；`Replay.vue`/`Warnings.vue` 无风险等级隐藏建单与失效预览防竞态；`ui/labels.js` 补齐 `SYSTEM` 角色与 `USER` 资源标签；`Tasks.vue` 共显逾期与升级徽章；`ingest.py`/`seed.py` 拆分独立日期集合、`OSError` 容错、`--sync-demo-passwords` 清零锁定及先建用户后导样本；`subscriptions.py` 补全审计参数。
- **P3（`c95bef8`）**：`main.py` 启动 `lifespan` 预热 `_dummy_password_hash` 并收紧 CSRF 登录豁免至精确 `POST /api/v1/auth/login`；`deps.py` 拦截空会话 Cookie 并在 403 时落 `PERMISSION_DENIED` 审计；`auth.py` 原子 Lua `_RECORD_IP_FAILURE_LUA`、重登撤销旧会话、去重查询；`users.py` 缺失管理员角色返回 `503 DEPENDENCY_UNAVAILABLE` 并按实际操作者最高角色写审计；`audit.py` 修复空串动作筛选；`schemas.py`/`config.py` `Literal` 枚举校验与 `SameSite=None` 强制 HTTPS Gate；`warnings.py`/`subscriptions.py`/`notifications.py`/`tasks.py`/`scheduler.py` 加锁读刷新、模型排序对齐、无改动更新跳过审计、预加载活跃订阅及异常先记日志再回滚。
- **P4（本轮收口）**：`App.vue` 导航下拉按角色过滤 `/review` 与 `/tasks`；`WarningDetail.vue` 提交审核限 `ANALYST/ADMIN`、详情与 `Review.vue` 隐藏自审按钮（展示「不可自审」）、闭环 Stepper 区分撤回关闭任务（「已随撤回关闭」）；`api.js` `ERROR_ZH` 补全 `LOGIN_RATE_LIMITED`、`METHOD_NOT_ALLOWED`、`HTTP_ERROR`；`Monitor.vue` 为 `FAILED` 数据集显示 `badge--danger`；`Users.vue` 复用 `roleLabel` 统一「查看用户」；`models.py` 与迁移 `0006_idx_users_active` 补建 `users(is_active)` 索引并对齐 `docs/database-design-v1.md` 与 `CLAUDE.md`。

验证：

- **前端单测与构建**：`node --test tests/test_frontend_review.mjs` **12 passed, 0 failed**；`cd frontend && npm run build` 生产构建通过。
- **迁移往返验证**：演示 VM 容器内执行 `0005_subscriptions_notifications -> 0006_idx_users_active -> 0005_subscriptions_notifications -> 0006_idx_users_active (head)` 往返通过，五服务健康检查（`/health`、`/health/db`、`/health/redis`、首页 `HTTP 200`）正常。
- **后端全量测试**：演示 VM `api` 容器内单元测试 `test_units.py` **23 passed**（2 warnings）；含集成全量测试（`RUN_INTEGRATION=1`）**122 passed**（3 warnings，0 failed，0 skipped）。

## 7. 未完成项与限制

- 浏览器端逐页截图验收未执行；已通过 HTTP 验证前端 HTML/CSS/JS 和 API 代理可达。
- MySQL 逻辑备份/恢复未实测。
- 25mm 结果为探索性（自举区间跨 0，召回下降），系统按文档标注，不作为主结论。
- 其余七类灾种仅为复用框架的扩展设计，未接入数据、未独立验证。
- 演示账号密码由本地 `.env` 提供，不进入仓库或交付包。
- `GET /warnings` 仍为全量返回、无分页/上限；当前演示数据量小暂未改接口，数据增长后需补 `limit/offset`。
- 本轮 UI 改版的浏览器逐页视觉与动效验收由用户人工执行（构建、路由、接口与中文映射已自动验证）。
- 管理员用户管理已实现，隔离环境浏览器核心流程通过（§6.10）；审查修复后全套 34 项测试通过（§6.11，含并发撤权/停用、审计异常回滚、缺失参考角色回滚和统一错误结构）；API 重启与依赖故障未验证。
- 七类扩展灾种仅登记数据源与判定指标，未接入数据、未做量化验证。
- 监测页展示的是已导入快照，不含实时拉取；定时调度目前只用于通知补投（`scheduler` 服务），不参与数据接入。发布不含短信/邮件等外部渠道。
- 响应任务、处置时限与超时升级已实现（§6.15）；任务派发给预警创建者，创建者已停用时改派发布人（§6.16），但暂不支持人工改派或多人协同；升级只做一次（`escalated_at` 写入后不再参与扫描），不做逐级上报。
