# C2 雷电历史回放实施计划

> **执行技能：** `executing-plans`、`test-driven-development`。按下列门槛核验，不用前一检查点替代本项成绩。

**目标**：按圣路易斯 KSTL 附近格点的真实 HRRR 档案，重算两个 6 小时窗口；达标且原发可证的案例可进入 B 的预警流程。

**架构**：FastAPI 仅处理注册样本；预报和站点摘要分开存储、分开返回。演练草稿只接受案例 ID 和文字，服务器重算并把预报快照写入既有 `0008`。Vue 回放页显示六个有效时次，预警详情只复用预报证据卡。

**依据**：[八灾种验收表](../../c-eight-hazard-acceptance.md)、[原始来源预核对](../../c2-lightning-source-preflight.md)。

**口径**：以 UTC 起报后 `+6 h` 为窗口起点，`(start, end]` 取 `f07–f12`。六值齐全时，最大 `LTNG ≥ 0.05` 判教学达标；列出达标的离散时次。该界线只用于演练，不是校准阈值、概率、次数、落点或连续实况。缺任一有效值为无法判断。站点 METAR/SPECI 不回填预报，`TSE06` 只表示上一轮雷暴结束。C1 指标不动。

- [x] **规则**：先在 `tests/test_lightning.py` 锁定两窗固定值、UTC 边界、正好达标、缺测、单位和站点隔离；实现 `services/lightning.py`、`assessment_schemas.py` 和最小离线摘录。用锁定 Python 环境重跑该文件。
- [ ] **接口**：先测读写权限、时间证据、未知与未达标拒绝、无站点时仍可起草。实现 `GET /lightning/cases`、`GET /lightning/cases/{id}/assessment`、`POST /warnings/lightning`，在详情返回 `lightning_assessment`。保留 `fused_mm=null`，不改迁移或暴雨站点表。运行后端全量集成测试。
- [ ] **网页**：先测切窗时清空旧结果、忽略过时响应、缺测/对照不可制单、正式详情不显示事后报告。增加菜单、灾种链接和证据卡；沿用分析员、独立审核员及管理员流程。跑 Node 两套测试和生产构建。
- [ ] **验收**：至少一次独立复审。使用同一候选 SHA 的干净归档和新建隔离 Compose 项目，在浏览器写入前核对 `/build-revision.txt`。演示六时次、两窗对照、缺测与共用闭环，回归 B/C1/台风/雪灾及 MySQL 独立迁移。写证据后用 `checkpoint/c2-lightning` 标记受验提交，按总计划推送并核对远端。
