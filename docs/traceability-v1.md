# 需求—实现—测试追溯矩阵 V1

> 用途：答辩时逐条说明「要求 → 落在哪个接口/文件 → 用什么证据证明」。
> 关联：`requirements-v1.md`、`architecture-v1.md`、`interface-design-v1.md`、`test-report-v1.md`。

## 1. 功能需求

| 编号 | 需求摘要 | 实现落点 | 测试/证据 | 状态 |
| --- | --- | --- | --- | --- |
| FR-01 | 登录、密码哈希、会话失效 | `routers/auth.py`、`deps.py`、`session.py`、`security.py` | `tests/test_login.py`：统一失败提示、按 IP 限速、锁定语义、登出失效；`test-report-v1.md` §6 | 已实现，已实测 |
| FR-02 | 管理员创建/停用/重置用户与角色 | `routers/users.py`、`schemas.py`、`models.py`（User/UserRole/is_active）、`frontend/src/views/Users.vue`、`frontend/src/router.js` | `test-report-v1.md` §6.10/§6.11：真实浏览器核心流程通过；审查修复后全套 34 项测试通过，含并发撤权/停用、审计异常回滚、缺失参考角色回滚、统一错误结构 | 已实现，核心流程已验证 |
| FR-03 | 数据源、数据集、元数据与导入校验 | `models.py`（DataSource/Dataset/DatasetIssue）、`services/ingest.py`、`seed.py`、`/monitor/status`、迁移 `0004` | `tests/test_ingest.py`：问题记入 `dataset_issues`、数据集标 `PARTIAL`、导入幂等 | 已实现，已实测 |
| FR-04 | 四模式等权融合与可追溯 | `services/replay.py`、`services/warnings.py`（写 `fusion_inputs`）、`schemas.WarningDetailOut`、`backend/fusion.py`、`pooled.py` | `tests/test_fusion.py`：详情返回四模式输入/基线/代理标签/数据集版本 | 已实现，已实测 |
| FR-05 | 10/25/50mm 阈值与教学风险等级 | `seed.py`（WarningThreshold）、`services/replay.py` | `/replay` 三阈值实测 | 已实现 |
| FR-06 | 历史回放（城市/日期/阈值） | `routers/replay.py`、`views/Replay.vue` | AT-01、`manual_round2.sh` | 已实现 |
| FR-07 | 草稿、修改、提交审核 | `POST/PATCH /warnings`、`/submit`、`views/Warnings.vue` | `test_state_machine.py` | 已实现 |
| FR-08 | 批准/驳回/发布/撤回 | `/review`、`/publish`、`/withdraw`、`views/Review.vue` | `test_state_machine.py`、`manual_round2.sh` | 已实现 |
| FR-09 | 响应与反馈（追加式） | `/feedback`、`WarningFeedback`、`views/WarningDetail.vue` | `test_state_machine.py`、AT-03 | 已实现 |
| FR-10 | 冻结指标展示 | `services/metrics.py`、`routers/metrics.py`、`views/Metrics.vue` | `pooled.json`、`manual_round2.sh` | 已实现 |
| FR-11 | 审计日志（追加、不可改删） | `services/audit.py`、`routers/audit.py`、`views/Audit.vue` | `manual_round2/3/4.sh`、AT-04 | 已实现 |
| FR-12 | 七类扩展灾种登记 | `app/hazards.py`、`/hazards`、`views/Hazards.vue` | `test_rbac_matrix.py`（8 类、1+7） | 框架已登记，未接入数据 |

## 2. 安全需求

| 编号 | 需求摘要 | 实现落点 | 测试/证据 | 状态 |
| --- | --- | --- | --- | --- |
| SEC-01 | 认证、Argon2、登录限速/锁定 | `security.py`、`auth.py`、`session.py` | `test_units.py`、`tests/test_login.py`（按 IP 限速 429、锁定统一提示）、`manual_round2.sh` | 已实现，已实测 |
| SEC-02 | 服务端 RBAC、自审禁止、查看者只读 | `deps.py`、`warnings.py`、`router.js` | `test_rbac_matrix.py`、`test_state_machine.py` | 已实现 |
| SEC-03 | 数据完整性与审计可追溯 | `add_audit` 与业务写同事务、迁移 `0003`/`0004`、`dataset_issues` | `manual_round4.sh`、AT-04、`tests/test_ingest.py` | 已实现，已实测 |
| SEC-04 | 输入校验、参数化查询、错误不外泄 | Pydantic 模型、SQLAlchemy、异常处理器 | `test_rbac_matrix.py`（非法状态 400） | 已实现 |
| SEC-05 | 密钥与隐私 | `.env`、`config.py`、日志抽查 | `test-report-v1.md` SEC-T06 | 已实现 |

## 3. 验收项

| 编号 | 验收项 | 证据位置 | 状态 |
| --- | --- | --- | --- |
| AT-01 | 四模式输入、融合值、PARTIAL 处理 | `test-report-v1.md` §3、`test_integration.py` | 已实测 |
| AT-02 | 基线 vs 融合指标（F1 0.7462→0.7900） | `pooled.json`、`/metrics` 页面 | 已实测 |
| AT-03 | 草稿→提交→批准→发布→反馈→撤回 | `test_state_machine.py`、`manual_round2.sh` | 已实测 |
| AT-04 | 未登录/越权/自审/审计 | `test_rbac_matrix.py`、`test_state_machine.py` | 已实测 |
| AT-05 | 断外网回放、重复一致、故障可见 | `manual_round2.sh`、`/health/*` | 已实测（离线样本） |
| AT-06 | 交付证据与压缩包 | `test-report-v1.md`、交付包扫描 | 进行中 |

## 4. 已知缺口（答辩时主动说明）

1. **用户管理验证范围**：FR-02 已实现，独立环境的真实浏览器核心流程及权限、CSRF、审计验证见测试报告 §6.10；专项 pytest、并发保护和审计异常回滚已验证；API 重启与依赖服务故障尚未验证。重置密码不注销已有会话，重新启用后未过期会话可恢复。
2. **七类灾种**：仅登记数据源与判定指标，未接入数据、未做量化验证；不得表述为已实现。
3. **监测实时性**：`/monitor/status` 展示的是已导入快照，不是实时拉取；无定时调度。
4. **发布渠道**：发布仅改变系统内状态并供查看，不调用短信/邮件/政务平台。
5. **响应闭环**：反馈是追加记录，没有响应任务、处置时限或超时升级（B 阶段规划）。
6. **备份恢复**：MySQL 逻辑备份/恢复尚未实测。
7. **浏览器 E2E**：自动化覆盖接口与构建，逐页截图需人工验收。

## 5. 后续阶段对应

| 阶段 | 补齐内容 | 文档 |
| --- | --- | --- |
| A | 监测页、灾种矩阵、闭环 Stepper、审核工作台、文档对齐、RBAC/状态机测试 | 本文件 + `roadmap-v1.md` |
| B | 订阅、站内通知、响应任务、处置时限、超时升级 | `roadmap-v1.md` |
| C | 高温、大雾真实数据接入与量化对比 | `roadmap-v1.md` |
