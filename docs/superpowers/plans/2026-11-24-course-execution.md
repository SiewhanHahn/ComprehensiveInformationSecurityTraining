# 信息安全综合实训：执行总计划（2026-11-24）

依据 11 月 24 日师生沟通：暴雨、台风、雪灾、雷电是重点；干旱、高温、低温、风雹也要能做基本预测。老师未要求四项均证明优于基线。名单取代旧规划，不回写历史 B 标签。

1. **口径（brainstorming / writing-plans）**：以[八灾种验收表](../../c-eight-hazard-acceptance.md)为范围合同。每个用例区分签发时输入、有效时段和事后核验；无资料先查数据，不做假演示。
2. **B 基线（using-git-worktrees / executing-plans / test-driven-development）**：在独立 `worktree-phase-b-important-fixes` 分支恢复两条测试边界，复核 9 Important、13 Minor；核对真实 MySQL 迁移及回退范围、UI 与 API 契约。不把 C 开发或未跟踪的中期材料带入 B。
3. **B 验收（requesting-code-review / verification-before-completion）**：在同一个本地候选提交的干净源码上进行复审、全量 pytest、前端测试和生产构建，按流程验证并记录候选 SHA、迁移和已知限制。在 B 候选代码的 `docs/b-closeout.md` 保存处置表。
4. **C 开发**：从已验收 B 基线接回已有暴雨工作并回归，依次完成三类重点真实案例和四类基本预测。共用输入、时段、风险解释及正式预警流程。旧 C 的 139/14 检查不作为新版本成绩。
5. **最终验收（webapp-testing / verification-before-completion / finishing-a-development-branch）**：从干净交付包启动，验八类正常、边界和缺测；在备好镜像及数据后离线演示。报告/说明使用课程 Word 模板，演示使用 PPT；结果以同一版本的新证据为准。
6. **最终推送门槛**：负责人先选 LICENSE，区分代码、数据与素材授权；排除凭据、缓存、卷；核对远端提交与交付包，未经决定不做最终推送。

B 阶段已按同一提交通过验收：[最终基线与实测证据](../../b-final-acceptance.md)。该标记不代表 C 已交付。
