# B 最终基线验收记录 · 2026-11-24

- **已实测的源码提交**：`be079a3a8aa07a39a8058286bf9c33ce5bb4ff36`。本地只读定位标签：`baseline/b-final-2026-11-24`（未推送，不是远程发布版本）。历史 `v0.3.0-phase-b` 仍为 `7181b93`；未合并 `main`。
- **范围**：B 的 9 个 Important、13 个 Minor 的处理见该提交中的 `docs/b-closeout.md`。C 原有外部文件试算及新八灾种功能不在此验收内。可用 `git show baseline/b-final-2026-11-24:docs/b-closeout.md` 查看清单。
- **审查过程**：第一候选 `65fbb69` 虽通过其测试，但独立复审指出旧审核轮次未隔离等四项。最终提交修复了审核行锁内的版本/轮次匹配、创建者的驳回意见、指标页迟到响应和跨会话未读角标，并重新复审。结论：上述四项已处理，复核范围内未发现阻断。

| 同一提交的验证 | 结果 |
|---|---|
| `git archive be079a3` 干净解包，VM 独立 Compose 项目（不是原 B 或 C 数据卷） | API、MySQL、Redis、Nginx、scheduler 正常。数据库迁移 head 为 `0007_warning_lifecycle_audit`。 |
| API 容器 `RUN_INTEGRATION=1`，注入隔离 QA 环境的四个 `DEMO_*_PASSWORD`，`python -m pytest -q -p no:cacheprovider /app/tests` | **252 passed，0 skipped，30 warnings**（依赖/旧用法弃用提示）。恢复的生命周期和未登录用例已独立收集、运行；包括修改/不修改内容重提两种审核轮次回归。 |
| 干净前端归档执行 `npm ci`、两个 Node 测试文件及 Vite 生产构建 | **38/38 通过**，构建成功；保留已有大 bundle 提示。 |
| 两个独立空 MySQL 库，各执行 `tests/manual_b_migration.py` | `0006 → 0007 → 0006 → 0007`，旧记录保留，列和外键核对通过；分别用仅审计版本、仅取消记录证明拒绝有损降级。没有在原 B/C 库降级。 |
| Edge/Playwright 通过回环转发访问 VM 上的 Nginx；分析员、审核员、管理员各有独立会话 | 创建→提交→驳回→作者看到原因→原编号修改为 v2 并重提→独立批准发布→接单完成→反馈→撤回；审计页核对发布、撤回原因及 v2。 |

复查源码：`git show --stat baseline/b-final-2026-11-24`。测试入口：`tests/test_b_closeout.py`、`tests/test_state_machine.py`、`tests/test_rbac_matrix.py`、`tests/test_frontend_review.mjs`、`tests/test_session_refresh_frontend.mjs`、`tests/manual_b_migration.py`、`tests/browser_b_acceptance.py`。在专用 QA 环境运行，勿向演示或真实实例直接跑写入测试。

## 转入 C 的约束

从上面的本地标签建立 C 的集成分支，不覆盖现有暴雨演示工作树。除新增文件外，尤其要手工核对错误映射、接口文档、前端中文标签和前端测试：不要用旧 C 版本覆盖本轮修复。接回暴雨功能后先回归九城指标、长沙回放和南京试算，再按[八灾种验收表](c-eight-hazard-acceptance.md)推进新能力。首次部署/构建、实时预报、物理断网或生产容灾不属于本次 B 验收结论。
