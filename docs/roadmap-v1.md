# 版本路线与取用说明 V1

> 文档状态：随开发推进更新
> 适用对象：课程设计开发者、答辩演示者、评审老师
> 关联文档：`requirements-v1.md`、`architecture-v1.md`、`test-report-v1.md`

## 1. 为什么分档

课程要求是「监测-预测-研判-预警-发布-响应-反馈」闭环、8 类灾种、可运行系统与量化提升。当前版本已经满足**最核心的量化提升**（F1 0.7462→0.7900，+4.38 点），但外围完整度分为四档，按投入产出比递进。

四档**可以层层递进**：

- A → B：纯增量，不返工。
- B → C：需要把降水硬编码抽成灾种注册表；A 阶段已预埋灾种注册表，返工有限。
- 每一档都能独立部署、独立测试、独立答辩。

## 2. 版本路线总览

| 档位 | 名称 | 目标 | 工作量 | 主要风险 |
| --- | --- | --- | --- | --- |
| A | 稳妥线 | 让闭环、8 类边界、审核发布流程「看得见」，文档自洽，测试有证据 | 2-3 天 | 7 类灾种仍只是框架 |
| B | A + 发布响应 | 站内通知、订阅、响应任务、处置时限、超时升级 | 4-5 天 | 新表/迁移/定时任务调试量上升 |
| C | B + 真实多灾种 | 高温、大雾真实数据接入与量化对比 | 6-9 天 | 外部数据依赖；新灾种可能没有提升 |
| D | 只出评估报告 | 书面差距分析、答辩口径、最小补强清单 | 半天 | 不改变系统 |

## 3. 各档交付物与验收

### A. 稳妥线

交付物：

- 页面：`/monitor` 监测、`/hazards` 灾种矩阵、`/review` 审核工作台。
- 组件：7 段闭环 Stepper，接入预警详情与回放页。
- 接口：`GET /hazards`、`GET /monitor/status`、`GET /warnings?status=`。
- 文档：修正过期描述，新增 `traceability-v1.md`。
- 测试：RBAC 矩阵、状态机全路径、完整写流程集成测试。

验收：8 类灾种矩阵齐全且标注实现状态；监测页显示数据源/版本/时间/完整性；预警详情 7 段流程随状态点亮；审核员可在工作台完成批准/发布。

### B. A + 发布响应

交付物：订阅表、站内通知、响应任务、处置时限、超时升级、通知中心、定时扫描。

验收：一条预警从发布到通知、响应、超时升级、反馈，全程可在浏览器演示。

### C. B + 真实多灾种

交付物：高温（最高气温）、大雾（能见度）的 Open-Meteo 历史预报 + ERA5 标签接入；灾种注册表驱动阈值/回放/指标；前端灾种选择器。

验收：3 类灾种均有可复现的基线 vs 融合对比；不提升的灾种如实标注。

### D. 只出评估报告

交付物：`docs/gap-analysis.md`（要求 vs 现状、答辩口径、最小补强清单）。不改代码。

## 4. 版本选择决策表

| 你的场景 | 应该取用 |
| --- | --- |
| 时间紧，只要一个稳定可答辩的版本 | `main` 或 `v0.2.0-phase-a` |
| 需要现场演示「发布→响应→反馈」 | `v0.3.0-phase-b` |
| 老师要求 8 类中多类能真实演示 | `v0.4.0-phase-c` |
| 想回退到今天已验证的可用快照 | `v0.1.0-mvp` |
| 继续开发下一档 | `phase-a` / `phase-b` / `phase-c` 分支 |

> `main` 只存放已验证版本。任何未验收的开发都在 `phase-*` 分支上，不影响 `main`。

## 5. Git 分支与标签规范

| 名称 | 用途 | 规则 |
| --- | --- | --- |
| `main` | 稳定版本 | 只接受 `phase-*` 合并；合并前必须构建与测试通过 |
| `phase-a` | A 阶段开发 | 从 `main` 切出 |
| `phase-b` | B 阶段开发 | A 验收并合并后，从 `main` 切出 |
| `phase-c` | C 阶段开发 | B 验收并合并后，从 `main` 切出 |
| `v0.1.0-mvp` | 已验证可运行快照 | 当前 `main` 基线 |
| `v0.2.0-phase-a` | A 验收版本 | 合并 `phase-a` 后打标签 |
| `v0.3.0-phase-b` | B 验收版本 | 合并 `phase-b` 后打标签 |
| `v0.4.0-phase-c` | C 验收版本 | 合并 `phase-c` 后打标签 |

标签说明必须写明：包含的页面/接口、量化结果、数据库迁移版本（A 无迁移，B 为 `0004`，C 预计无新迁移）。

## 6. 常用命令

```bash
# 查看所有版本
git fetch --tags
git tag -l

# 查看某个已验证版本（只读，不建分支）
git switch --detach v0.2.0-phase-a

# 回到最新稳定版
git switch main

# 从稳定版开始下一档
git switch -c phase-b

# 阶段验收后合并并打标签
git switch main
git merge --no-ff phase-b
git tag -a v0.3.0-phase-b -m "Phase B: publish-response loop with notifications and response tasks"
git push origin main --tags
```

## 7. 数据库迁移注意事项

| 版本 | 迁移 | 说明 |
| --- | --- | --- |
| v0.1.0-mvp | `0001`~`0003` | 当前线上库已应用 |
| v0.2.0-phase-a | 无新迁移 | 只读接口与前端页面 |
| v0.3.0-phase-b | 新增 `0004` | 订阅、通知、响应任务 |
| v0.4.0-phase-c | 预计无新迁移 | 主要是数据接入与代码泛化 |

- **旧代码 + 新库**：通常安全（多余表被忽略）。
- **新代码 + 旧库**：必须先执行迁移，否则接口会报表不存在。
  ```bash
  docker compose run --rm migrate
  ```
- 切换版本后都要重建对应镜像：`docker compose build api frontend && docker compose up -d api frontend`。

## 8. 交付包导出

按标签导出，避免把工作区分支状态打进压缩包：

```bash
git archive --format=tar.gz --prefix=ComprehensiveInformationSecurityTraining/ \
  -o ComprehensiveInformationSecurityTraining-v0.2.0-phase-a.tar.gz v0.2.0-phase-a
```

压缩包仍不得包含 `.env`、真实密码、`node_modules/`、`data/cache/` 与容器卷数据；`.gitignore` 已排除这些路径。

## 9. 当前状态

| 项目 | 状态 |
| --- | --- |
| `main` | `v0.1.0-mvp`，UI 改造后的可运行版本 |
| `phase-a` | A 档开发完成，自动化测试 19 passed，待浏览器人工验收 |
| A 验收 | 待用户验收；通过后合并 `main` 并打 `v0.2.0-phase-a` |
| B / C | 未开始，等待 A 验收后再决定 |
