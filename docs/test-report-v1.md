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
| 中 | `seed_users` 不更新既有账号密码、`role` 空会崩溃 | 同步密码哈希/启用状态 + `role` None 守卫 |
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

## 7. 未完成项与限制

- 浏览器端逐页截图验收未执行；已通过 HTTP 验证前端 HTML/CSS/JS 和 API 代理可达。
- MySQL 逻辑备份/恢复未实测。
- 25mm 结果为探索性（自举区间跨 0，召回下降），系统按文档标注，不作为主结论。
- 其余七类灾种仅为复用框架的扩展设计，未接入数据、未独立验证。
- 演示账号密码由本地 `.env` 提供，不进入仓库或交付包。
- `GET /warnings` 仍为全量返回、无分页/上限；当前演示数据量小暂未改接口，数据增长后需补 `limit/offset`。
- 本轮 UI 改版的浏览器逐页视觉与动效验收由用户人工执行（构建、路由、接口与中文映射已自动验证）。
- 管理员用户管理 API（创建/停用/重置用户）尚未实现；演示账号由 seed 创建。详见 `traceability-v1.md` §4。
- 七类扩展灾种仅登记数据源与判定指标，未接入数据、未做量化验证。
- 监测页展示的是已导入快照，不含实时拉取与定时调度；发布不含短信/邮件等外部渠道。
