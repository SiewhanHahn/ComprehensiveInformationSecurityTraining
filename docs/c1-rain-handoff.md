# C1 暴雨集成：验收入口

C1 是 B 最终基线 `be079a3` 上的暴雨集成里程碑，不是八灾种终版。本地标签 **`checkpoint/c1-rain`** 在独立审查、干净归档、后端/前端和浏览器验收通过后才创建；标签不存在时，本页不能作为通过证明。

```bash
git rev-parse 'checkpoint/c1-rain^{commit}'
git notes --ref=c1-acceptance show 'checkpoint/c1-rain^{commit}'
```

注记保存实际验收的 SHA、命令、计数、QA 项目与端口。用 `git archive` 导出时 `frontend/public/build-revision.txt` 自动展开为源码 SHA；从普通工作树直接构建出现未展开占位符时，不可作为指定版本的证据。

- **演示**：按[用户指南](user-guide-v1.md#defense)启动，C1 演示端口默认 18280；历史暴雨 18080 不变。并排打开不同版本时使用独立浏览器配置文件。
- **写入测试只限可丢弃 QA**：从相同 SHA 导出到另一目录，选择全新 Compose 项目名、独立 `.env`、Redis/MySQL 卷和单独端口（本次 18281）。先核对 `docker compose port frontend 80` 和 `/build-revision.txt` 中的 SHA。测试会模拟登录、创建预警和写入审计、清理 QA 的登录计数，不得连接演示库。
- **回归顺序**：API 容器以 `RUN_INTEGRATION=1` 和四个 QA `DEMO_*_PASSWORD` 运行 `python -m pytest -q /app/tests`；前端 `npm ci`、两套 `node --test` 和 `npm run build`。以 `tests/browser_defense.py --url <QA地址> --expect-revision <完整SHA>` 验年份、两档指标、长沙算式、南京下载上传和无外网请求；在同一 QA 用 `tests/browser_b_acceptance.py` 验正式审批和审计（需要显式设置 `BCHECK_ALLOW_WRITE=1`）。
- **不变量**：九城冻结结果与长沙源样本不得改写；南京只试算不发布；待审核预警的内容版本和轮次不受试算影响。维持 B 的 `0007`，无新迁移。台风、雪灾、雷电及四类基本预测另行验收。
